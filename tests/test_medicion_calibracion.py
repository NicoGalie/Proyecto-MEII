from copy import deepcopy
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
import calibracion as ajustes
import medidor_backend as b


def punto(f, ganancia, fase, r_ref=1800, rs=100):
    return {'frecuencia': f, 'frecuencia_objetivo': f, 'ganancia': ganancia,
            'fase_cruda': fase, 'correccion_fase': ajustes.normalizar_fase(fase - 180),
            'v_rms': 1.0, 'v_i_out': rs * ganancia / r_ref}


def perfil(fase_a=170, fase_b=160):
    return {'version':1, 'fecha':'2026-10-06T00:00:00+00:00', 'r_sensora':100,
            'r_referencia':1800, 'puntos':[punto(1000,4,fase_a),punto(2000,3,fase_b)]}


class MatematicaTests(unittest.TestCase):
    def test_capacitor_e_inductor_ideales(self):
        for x, tipo, valor in [(-1/(2*math.pi*1000*1e-6),'CAPACITOR',1e-6), (2*math.pi*1000*0.01,'INDUCTOR',0.01)]:
            fase = math.degrees(math.atan2(x,10))
            resultado = b._procesar_matematica(0.05,math.hypot(10,x)*0.001,1000,ajustes.normalizar_fase(fase+180),10)
            self.assertEqual(resultado['tipo'], tipo)
            self.assertAlmostEqual(resultado['valor_num'], valor)
            self.assertAlmostEqual(resultado['esr_num'],10)

    def test_rechaza_cero_negativos_nan_e_inf(self):
        for posicion in (0,1,2):
            for invalido in (0,-1,float('nan'),float('inf'),-float('inf')):
                datos = [0.05,0.1,1000,135]
                datos[posicion] = invalido
                with self.subTest(posicion=posicion,valor=invalido), self.assertRaises(ValueError):
                    b._procesar_matematica(*datos,10)
        for fase in (float('nan'),float('inf'),1e30):
            with self.assertRaises(ValueError):
                b._procesar_matematica(0.05,0.1,1000,fase,10)

    def test_esr_negativa_es_error(self):
        with self.assertRaisesRegex(ValueError,'ESR negativa'):
            b._procesar_matematica(0.05,0.1,1000,-60,10)

    def test_signo_de_fase_sin_margen_de_dos_grados(self):
        for fase,tipo in [(-1,'CAPACITOR'),(0,'RESISTENCIA'),(1,'INDUCTOR')]:
            resultado = b._procesar_matematica(0.05,0.1,1000,ajustes.normalizar_fase(fase+180),10)
            self.assertEqual(resultado['tipo'],tipo)

    def test_medicion_invalida_no_es_exitosa_y_cierra_conexiones(self):
        rm,osc=MagicMock(),MagicMock()
        adaptador=b.Osciloscopio(osc,'UNI-T,UTD2102,SERIAL,1','uni_t')
        with patch.object(b,'_conectar_instrumentos',return_value=(rm,adaptador,None)), patch.object(b,'_leer_seguro',side_effect=[0,0.1,1000,135]), patch.object(b.time,'sleep'):
            resultado=b.medicion_simple(10)
        self.assertFalse(resultado['exito'])
        osc.close.assert_called_once()
        rm.close.assert_called_once()

    def test_lector_reintenta_nan_y_rechaza_codigos_negativos(self):
        osc=MagicMock()
        osc.query.side_effect=['nan','1.25']
        with patch.object(b.time,'sleep'):
            self.assertEqual(b._leer_seguro(osc,'VRMS?'),1.25)
        osc.query.side_effect=None
        osc.query.return_value='-1e37'
        with patch.object(b.time,'sleep'), self.assertRaises(ValueError):
            b._leer_seguro(osc,'VRMS?')

    def test_barrido_guarda_tipo_y_unidades_por_punto(self):
        rm,osc,gen=MagicMock(),MagicMock(),MagicMock()
        with patch.object(b,'_conectar_instrumentos',return_value=(rm,osc,gen)), patch.object(b,'_leer_medicion',side_effect=[(0.05,0.1,1000,135),(0.05,0.1,2000,-135)]), patch.object(b.time,'sleep'):
            resultado=b.barrido_automatico(1000,2000,2,10)
        self.assertTrue(resultado['exito'])
        self.assertEqual(resultado['tipo'],'MIXTO')
        self.assertEqual([p['tipo'] for p in resultado['puntos']],['CAPACITOR','INDUCTOR'])
        self.assertEqual(len(resultado['por_tipo']['CAPACITOR']),1)
        self.assertEqual(len(resultado['por_tipo']['INDUCTOR']),1)


class CalibracionTests(unittest.TestCase):
    def test_calibracion_obtiene_ganancia_y_fase_sin_usar_perfil_anterior(self):
        rm,osc,gen=MagicMock(),MagicMock(),MagicMock()
        progreso=[]
        with patch.object(b,'_conectar_instrumentos',return_value=(rm,osc,gen)), patch.object(b,'_leer_medicion',side_effect=[(4*100/1800,1,1000,170),(3*100/1800,1,2000,160)]), patch.object(b.time,'sleep'):
            resultado=b.calibrar_barrido(1000,2000,2,100,1800,progreso.append)
        self.assertTrue(resultado['exito'])
        puntos=resultado['calibracion']['puntos']
        self.assertEqual([p['ganancia'] for p in puntos],[4,3])
        self.assertEqual([p['correccion_fase'] for p in puntos],[-10,-20])
        self.assertEqual(len(progreso),2)
        rm.close.assert_called_once()
        osc.close.assert_called_once()
        gen.close.assert_called_once()

    def test_valor_conocido_editable_cambia_ganancia(self):
        for r_ref in (1800,2200):
            with patch.object(b,'_conectar_instrumentos',return_value=(MagicMock(),MagicMock(),MagicMock())), patch.object(b,'_leer_medicion',side_effect=[(0.1,1,1000,170),(0.1,1,2000,160)]), patch.object(b.time,'sleep'):
                resultado=b.calibrar_barrido(1000,2000,2,100,r_ref)
            self.assertTrue(resultado['exito'])
            self.assertAlmostEqual(resultado['calibracion']['puntos'][0]['ganancia'],0.1*r_ref/100)

    def test_interpolacion_de_ganancia_y_fase(self):
        ganancia,correccion=ajustes.correcciones(perfil(),1500,100)
        self.assertEqual(ganancia,3.5)
        self.assertEqual(correccion,-15)

    def test_interpolacion_respeta_salto_circular(self):
        ganancia,correccion=ajustes.correcciones(perfil(170,-170),1500,100)
        self.assertEqual(correccion,0)

    def test_rechaza_perfil_con_fases_de_resistencia_incoherentes(self):
        for fases in ((170, -11.62), (170, 9.74), (170, -1.42), (170, 110)):
            with self.subTest(fases=fases), self.assertRaises(ValueError):
                ajustes.validar_perfil(perfil(*fases))

    def test_rechaza_perfil_tek_del_metodo_anterior(self):
        p = perfil()
        p['osciloscopio'] = {'fabricante': 'TEKTRONIX', 'modelo': 'TBS2102B', 'serie': 'C022681'}
        with self.assertRaisesRegex(ValueError, 'anterior debe repetirse'):
            ajustes.validar_perfil(p)
        p['metodo_medicion'] = 'senoidal_v1'
        ajustes.validar_perfil(p)

    def test_captura_senoidal_tolere_desvio_pequeno_de_reloj_en_extremos(self):
        p = perfil()
        p['metodo_medicion'] = 'senoidal_v1'
        self.assertEqual(ajustes.correcciones(p, 999.8, 100), (4, -10))
        self.assertEqual(ajustes.correcciones(p, 2000.2, 100), (3, -20))
        for f in (998, 2003):
            with self.assertRaises(ValueError):
                ajustes.correcciones(p, f, 100)

    def test_referencia_recupera_resistencia_y_fase_cero(self):
        d=b._procesar_matematica(100*4/1800,1,1000,170,100,perfil())
        self.assertEqual(d['tipo'],'RESISTENCIA')
        self.assertAlmostEqual(d['z_num'],1800)
        self.assertEqual(d['fase_num'],0)

    def test_correccion_recupera_capacitor_a_frecuencia_intermedia(self):
        f,g,corr=1500,3.5,-15
        x=-1/(2*math.pi*f*1e-6)
        phi=math.degrees(math.atan2(x,10))
        d=b._procesar_matematica(0.001*100*g,0.001*math.hypot(10,x),f,ajustes.normalizar_fase(phi+180+corr),100,perfil())
        self.assertEqual(d['tipo'],'CAPACITOR')
        self.assertAlmostEqual(d['valor_num'],1e-6)
        self.assertAlmostEqual(d['esr_num'],10)

    def test_rechaza_otra_r1_y_no_extrapola(self):
        for f,rs in [(1500,10),(999,100),(2001,100)]:
            with self.subTest(f=f,rs=rs),self.assertRaises(ValueError):
                ajustes.correcciones(perfil(),f,rs)

    def test_calibracion_parcial_no_devuelve_perfil_aplicable(self):
        with patch.object(b,'_conectar_instrumentos',return_value=(MagicMock(),MagicMock(),MagicMock())),patch.object(b,'_leer_medicion',side_effect=[(0.1,1,1000,170)]+[ValueError('sin señal')]*4),patch.object(b.time,'sleep'):
            resultado=b.calibrar_barrido(1000,2000,2,100,1800)
        self.assertFalse(resultado['exito'])
        self.assertNotIn('calibracion',resultado)
        self.assertEqual(len(resultado['puntos']),1)

    def test_guardado_y_carga_y_perfil_corrupto(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'calibracion.json'
            ajustes.guardar(perfil(),ruta)
            self.assertEqual(ajustes.cargar(ruta),perfil())
            anterior=ruta.read_text()
            invalido=deepcopy(perfil())
            invalido['puntos'][0]['ganancia']=float('nan')
            with self.assertRaises(ValueError):
                ajustes.guardar(invalido,ruta)
            self.assertEqual(ruta.read_text(),anterior)
            ruta.write_text('{invalid')
            with self.assertRaises(ValueError):
                ajustes.cargar(ruta)

    def test_rechaza_frecuencias_repetidas_y_metadata_incompleta(self):
        for cambiar in ('repetida','campo'):
            invalido=deepcopy(perfil())
            if cambiar=='repetida':
                invalido['puntos'][1]['frecuencia']=1000
            else:
                del invalido['puntos'][0]['v_i_out']
            with self.assertRaises(ValueError):
                ajustes.validar_perfil(invalido)


if __name__=='__main__':
    unittest.main()
