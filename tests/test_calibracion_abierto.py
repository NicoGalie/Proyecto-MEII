from copy import deepcopy
from pathlib import Path
import cmath
import math
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
import calibracion as c
import medidor_backend as b
from analisis_senoidal import analizar


def lectura(m, f, vr=1.7):
    return abs(m)*vr, vr, f, c.normalizar_fase(-math.degrees(cmath.phase(m)))


def abierto_simulado(rs=10):
    puntos=[]
    for f in (1000,2000):
        h=complex(-.001, -.000001*f)
        captura=dict(zip(('v_i_out','v_rms','frecuencia','fase_cruda'),lectura(h,f)))
        puntos.append(dict(frecuencia=f,frecuencia_objetivo=f,residual_real=h.real,
                           residual_imag=h.imag,lecturas=[captura.copy() for _ in range(3)]))
    return dict(r_sensora=rs,puntos=puntos)


def perfil_simulado():
    abierto=abierto_simulado()
    puntos=[]
    for pa in abierto['puntos']:
        f=pa['frecuencia']
        a=complex(-50, -.0001*f)
        h=c.complejo(pa,'residual')
        puntos.append(b._procesar_punto_calibracion(lectura(a/1800+h,f),f,10,1800,abierto=pa))
    return dict(version=2,r_sensora=10,r_referencia=1800,puntos=puntos,abierto=abierto)


class CompensacionTests(unittest.TestCase):
    def test_recupera_impedancias_fuera_de_la_resistencia_de_referencia(self):
        p=perfil_simulado()
        for f in (1000,1500,2000):
            a,h=c.coeficientes(p,f,10)
            for z in (complex(2.41,2*math.pi*f*.00291),complex(5,-1/(2*math.pi*f*1e-6)),complex(1800,0)):
                datos=b._procesar_matematica(*lectura(a/z+h,f),10,p)
                self.assertAlmostEqual(datos['esr_num'],z.real,places=8)
                self.assertAlmostEqual(datos['xs_num'],z.imag,places=8)

    def test_esr_negativa_y_corriente_indistinguible_no_se_ocultan(self):
        p=perfil_simulado();a,h=c.coeficientes(p,1000,10)
        with self.assertRaisesRegex(ValueError,'ESR negativa'):
            b._procesar_matematica(*lectura(a/complex(-2,90)+h,1000),10,p)
        with self.assertRaisesRegex(ValueError,'no se distingue'):
            b._procesar_matematica(*lectura(h,1000),10,p)

    def test_rechaza_coeficientes_alterados_y_abierto_de_otro_barrido(self):
        p=perfil_simulado()
        for campo in ('transferencia_real','residual_imag','ganancia','correccion_fase'):
            mala=deepcopy(p);mala['puntos'][0][campo]+=.1
            with self.subTest(campo=campo),self.assertRaises(ValueError):c.validar_perfil(mala)
        for frecs,rs in (([1000,3000],10),([1000,2000],100)):
            with self.assertRaises(ValueError):b.validar_abierto(p['abierto'],frecs,rs)

    def test_abierto_requiere_tres_capturas_coherentes(self):
        lecturas=[lectura(complex(-.001,-.001),1000)]*3
        with patch.object(b,'_leer_medicion',side_effect=lecturas[1:]):
            punto=b._procesar_abierto(MagicMock(),1000,lecturas[0])
        self.assertAlmostEqual(punto['residual_real'],-.001)
        with patch.object(b,'_leer_medicion',side_effect=[lecturas[0],lectura(complex(-.003,-.001),1000)]):
            with self.assertRaisesRegex(ValueError,'no es estable'):
                b._procesar_abierto(MagicMock(),1000,lecturas[0])

    def test_barrido_abierto_completo_y_calibracion_v2(self):
        datos=abierto_simulado();rm,osc,gen=MagicMock(),MagicMock(),MagicMock()
        lecturas=[tuple(p['lecturas'][0][k] for k in ('v_i_out','v_rms','frecuencia','fase_cruda'))
                  for p in datos['puntos'] for _ in range(3)]
        with patch.object(b,'_conectar_instrumentos',return_value=(rm,osc,gen)),patch.object(b,'_preparar_frecuencia'),patch.object(b,'_leer_medicion',side_effect=lecturas):
            res=b.medir_abierto(1000,2000,2,10)
        self.assertTrue(res['exito'],res)
        for inst in (rm,osc,gen):inst.close.assert_called_once()
        ref=[lectura(complex(-50,0)/1800+c.complejo(p,'residual'),p['frecuencia']) for p in datos['puntos']]
        with patch.object(b,'_conectar_instrumentos',return_value=(MagicMock(),MagicMock(),MagicMock())),patch.object(b,'_preparar_frecuencia'),patch.object(b,'_leer_medicion',side_effect=ref):
            res=b.calibrar_barrido(1000,2000,2,10,1800,abierto=datos)
        self.assertTrue(res['exito'],res)
        self.assertEqual(res['calibracion']['version'],2)
        self.assertAlmostEqual(res['puntos'][0]['ganancia'],5)

    def test_calibracion_incompatible_no_programa_generador(self):
        osc,gen=MagicMock(),MagicMock()
        with patch.object(b,'_conectar_instrumentos',return_value=(MagicMock(),osc,gen)):
            res=b.calibrar_barrido(1000,3000,2,10,1800,abierto=abierto_simulado())
        self.assertFalse(res['exito']);gen.write.assert_not_called()

    def test_abierto_debil_se_mide_solo_con_ruido_absoluto_acotado(self):
        t=np.arange(20000)*.02/20000;ang=2*np.pi*1000*t
        ch2=np.sqrt(2)*np.sin(ang)
        ch1=.002*np.sqrt(2)*np.sin(ang+.8)+.0005*np.sin(3*ang)
        with self.assertRaises(ValueError):analizar(t,ch1,ch2,1000)
        vi,vr,f,fase=analizar(t,ch1,ch2,1000,circuito_abierto=True)
        self.assertAlmostEqual(vi,.002,places=6)
        with self.assertRaisesRegex(ValueError,'ruido residual'):
            analizar(t,ch1+.01*np.sin(7*ang),ch2,1000,circuito_abierto=True)


if __name__=='__main__':unittest.main()
