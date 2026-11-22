import cmath
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import calibracion as c
from calculos import calcular
from configuracion import Configuracion, leer_rg
from falsos import IDENTIDAD, lectura_compleja, perfil_simulado
from modelos import Lectura


class CalculosTests(unittest.TestCase):
    def test_r_l_c_sin_inversion_y_con_distintas_rs(self):
        for rs in (10, 47.2, 100):
            config = Configuracion(rs)
            for f in (1000, 5000, 10000):
                for z in (
                    100 + 0j,
                    complex(2.41, 2 * math.pi * f * 0.00291),
                    complex(3, -1 / (2 * math.pi * f * 1e-6)),
                ):
                    m = calcular(lectura_compleja(config.ganancia * rs / z, f), config)
                    self.assertAlmostEqual(m.z.real, z.real, places=8)
                    self.assertAlmostEqual(m.z.imag, z.imag, places=8)
                    if z.imag > 0:
                        self.assertEqual(m.tipo, 'INDUCTOR')
                        self.assertAlmostEqual(m.valor, 0.00291)
                        self.assertAlmostEqual(m.factor, z.imag / z.real)
                    elif z.imag < 0:
                        self.assertEqual(m.tipo, 'CAPACITOR')
                        self.assertAlmostEqual(m.valor, 1e-6)
                        self.assertAlmostEqual(m.factor, z.real / abs(z.imag))
                    else:
                        self.assertEqual(m.tipo, 'RESISTENCIA')

    def test_rg_y_valores_no_finitos_sin_ocultar_esr_negativa(self):
        self.assertEqual(Configuracion(rg_ohm=leer_rg('12500,0')).ganancia, 5)
        self.assertEqual(Configuracion(rg_ohm=leer_rg('abierto')).ganancia, 1)
        for x in (0, -1, float('nan'), float('inf'), True):
            with self.subTest(x=x), self.assertRaises(ValueError):
                Configuracion(x)
        for x in ('', '0', '-1', 'nan', 'inf'):
            with self.assertRaises(ValueError):
                leer_rg(x)
        with self.assertRaisesRegex(ValueError, 'ESR negativa'):
            calcular(Lectura(0.5, 1, 5000, 120), Configuracion())
        for datos in [(0, 1, 1000, 0), (0.5, float('nan'), 1000, 0), (0.5, 1, 1000, 1e30)]:
            with self.assertRaises(ValueError):
                Lectura(*datos)


class CalibracionTests(unittest.TestCase):
    def ajuste(self, perfil, f=1500, config=None, usar=True, identidad=None, metodo='senoidal_v1'):
        return c.seleccionar(
            perfil, config or Configuracion(), f, identidad or IDENTIDAD, metodo, usar
        )

    def test_interpolacion_y_compensacion_recuperan_z_con_y_sin_abierto(self):
        for abierto in (False, True):
            p = perfil_simulado(abierto)
            a = self.ajuste(p)
            self.assertTrue(a.aplicada)
            self.assertAlmostEqual(a.ganancia, 4.7, delta=0.001)
            for z in (
                complex(100, 0),
                complex(2.41, 2 * math.pi * 1500 * 0.00291),
                complex(3, -100),
            ):
                transferencia = a.transferencia or a.ganancia * 10 * cmath.exp(
                    -1j * math.radians(a.fase)
                )
                lectura = lectura_compleja(transferencia / z + a.residual, 1500)
                m = calcular(lectura, Configuracion(), a)
                self.assertAlmostEqual(m.z.real, z.real, places=8)
                self.assertAlmostEqual(m.z.imag, z.imag, places=8)

    def test_fuera_del_rango_u_otra_rs_usa_todo_el_modelo_nominal(self):
        for abierto in (False, True):
            p = perfil_simulado(abierto)
            for f, config in [
                (500, Configuracion()),
                (3000, Configuracion()),
                (1500, Configuracion(47.2)),
                (1500, Configuracion(rg_ohm=10000)),
            ]:
                a = self.ajuste(p, f, config)
                self.assertFalse(a.aplicada)
                self.assertEqual(
                    (a.ganancia, a.fase, a.residual, a.transferencia),
                    (config.ganancia, 0, 0j, None),
                )
                z = complex(2.41, 2 * math.pi * f * 0.00291)
                m = calcular(lectura_compleja(config.ganancia * config.rs / z, f), config, a)
                self.assertAlmostEqual(m.z.real, 2.41, places=8)
                self.assertAlmostEqual(m.valor, 0.00291, places=8)
                self.assertIn('nominales', a.motivo)

    def test_checkbox_desactivado_y_equipo_distinto_no_aplican_perfil(self):
        p = perfil_simulado(True)
        for opciones in [
            dict(usar=False),
            dict(identidad=dict(IDENTIDAD, serie='OTRA')),
            dict(metodo='scpi_v1'),
        ]:
            a = self.ajuste(p, **opciones)
            self.assertFalse(a.aplicada)
            self.assertIsNone(a.transferencia)
        self.assertFalse(self.ajuste(None).aplicada)

    def test_tolerancia_de_reloj_en_extremos_sin_extrapolacion(self):
        p = perfil_simulado()
        self.assertTrue(self.ajuste(p, 999.8).aplicada)
        self.assertTrue(self.ajuste(p, 2000.2).aplicada)
        self.assertFalse(self.ajuste(p, 998).aplicada)
        self.assertFalse(self.ajuste(p, 2003).aplicada)
        self.assertFalse(
            c.seleccionar(
                p, Configuracion(), 2000.2, IDENTIDAD, 'senoidal_v1', objetivo=2000.2
            ).aplicada
        )
        self.assertTrue(
            c.seleccionar(
                p, Configuracion(), 2000.2, IDENTIDAD, 'senoidal_v1', objetivo=2000
            ).aplicada
        )

    def test_inconsistencias_y_polaridad_rechazadas(self):
        p = perfil_simulado(True)
        for campo in ('transferencia_real', 'residual_imag', 'ganancia', 'correccion_fase'):
            mala = deepcopy(p)
            mala['puntos'][0][campo] += 0.1
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                c.validar(mala)
        mala = deepcopy(p)
        mala['circuito']['id'] = 'otro'
        with self.assertRaises(ValueError):
            c.validar(mala)
        with self.assertRaises(ValueError):
            c.crear_punto(Lectura(0.5, 1, 1000, 180), 1000, Configuracion(), 100)
        a = self.ajuste(p, 1000)
        with self.assertRaisesRegex(ValueError, 'no se distingue'):
            calcular(lectura_compleja(a.residual, 1000), Configuracion(), a)

    def test_guardado_atomico_y_carga_compatible(self):
        for abierto in (False, True):
            p = perfil_simulado(abierto)
            with tempfile.TemporaryDirectory() as d:
                ruta = Path(d) / 'cal.json'
                c.guardar(p, ruta)
                self.assertEqual(c.cargar(ruta), p)
                previo = ruta.read_bytes()
                mala = deepcopy(p)
                mala['puntos'][0]['ganancia'] = float('nan')
                with self.assertRaises(ValueError):
                    c.guardar(mala, ruta)
                self.assertEqual(ruta.read_bytes(), previo)


if __name__ == '__main__':
    unittest.main()
