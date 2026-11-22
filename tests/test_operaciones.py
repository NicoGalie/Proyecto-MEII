import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import operaciones as o
from cancelacion import Cancelacion
from configuracion import Configuracion
from falsos import IDENTIDAD, lectura_compleja, perfil_simulado
from modelos import Lectura


class SesionFalsa:
    def __init__(self, control, lecturas):
        self.control, self.lecturas = control, iter(lecturas)
        self.identidad, self.metodo = IDENTIDAD.copy(), 'senoidal_v1'
        self.osc = SimpleNamespace(circuito_abierto=False)
        self.programadas, self.promedios = [], []
        self.cerrada = False

    def preparar(self, f):
        self.control.comprobar()
        self.programadas.append(f)

    def validar_promedio(self, segundos):
        pass

    def leer(self, promedio=None, progreso=None):
        self.promedios.append(promedio)
        valor = next(self.lecturas)
        if isinstance(valor, Exception):
            raise valor
        return valor, {} if promedio is None else dict(tiempo_promedio_s=promedio)

    @contextmanager
    def conectar(self, control):
        try:
            control.comprobar()
            yield self
        finally:
            self.cerrada = True


class OperacionesTests(unittest.TestCase):
    def sesion(self, lecturas, control=None):
        control = control or Cancelacion()
        s = SesionFalsa(control, lecturas)
        return control, s, patch.object(o, 'conectar', side_effect=s.conectar)

    def test_simple_programa_frecuencia_y_calcula_con_la_medida(self):
        control, s, p = self.sesion([Lectura(0.5, 1, 5001, 45)])
        with p:
            m = o.medir(5000, Configuracion(), control=control)
        self.assertEqual(s.programadas, [5000])
        self.assertEqual(m.objetivo, 5000)
        self.assertEqual(m.lectura.frecuencia, 5001)
        self.assertTrue(s.cerrada)

    def test_simple_con_promedio_y_reintentos(self):
        control, s, p = self.sesion([ValueError('temporal')] * 3 + [Lectura(0.5, 1, 5000, 45)])
        with p:
            m = o.medir(5000, Configuracion(), promedio=2, control=control)
        self.assertEqual(m.intentos, 4)
        self.assertEqual(s.programadas, [5000] * 4)
        self.assertEqual(s.promedios, [2] * 4)
        self.assertEqual(m.promedio['tiempo_promedio_s'], 2)

    def test_frecuencia_anterior_reintenta_y_no_fabrica_resultados(self):
        control, s, p = self.sesion([Lectura(0.5, 1, 1000, 0)] * 4 + [Lectura(0.5, 1, 3000, 0)])
        with p:
            r = o.barrer(2000, 3000, 2, Configuracion(), control=control)
        self.assertEqual([f.estado for f in r.filas], ['ERROR', 'OK'])
        self.assertIsNone(r.filas[0].medicion)
        self.assertEqual(r.filas[0].intentos, 4)
        self.assertEqual(s.programadas, [2000] * 4 + [3000])

    def test_barrido_mezcla_calibracion_y_nominal_segun_frecuencia(self):
        control, s, p = self.sesion(
            [Lectura(0.48, 1, 1000, 2), Lectura(0.46, 1, 2000, 4), Lectura(0.5, 1, 3000, 0)]
        )
        with p:
            r = o.barrer(1000, 3000, 3, Configuracion(), perfil_simulado(), True, control)
        self.assertEqual([f.medicion.ajuste.aplicada for f in r.filas], [True, True, False])
        for fila in r.filas:
            self.assertAlmostEqual(fila.medicion.z.real, 100)

    def test_cancelar_entre_puntos_conserva_resultado_y_no_programa_siguiente(self):
        control, s, p = self.sesion([Lectura(0.5, 1, 1000, 0)])

        def progreso(evento):
            if evento['tipo'] == 'punto':
                control.cancelar()

        with p:
            r = o.barrer(1000, 3000, 3, Configuracion(), control=control, progreso=progreso)
        self.assertTrue(r.cancelado)
        self.assertEqual(len(r.filas), 1)
        self.assertEqual(r.filas[0].estado, 'OK')
        self.assertEqual(s.programadas, [1000])
        self.assertTrue(s.cerrada)

    def test_cancelar_durante_reintento_no_repite_y_marca_frecuencia_interrumpida(self):
        control, s, p = self.sesion([ValueError('ruido')])

        def progreso(evento):
            if 'Reintento' in evento.get('texto', ''):
                control.cancelar()

        with p:
            r = o.barrer(1000, 3000, 3, Configuracion(), control=control, progreso=progreso)
        self.assertTrue(r.cancelado)
        self.assertEqual([f.estado for f in r.filas], ['CANCELADO'])
        self.assertIsNone(r.filas[0].medicion)
        self.assertEqual(s.programadas, [1000])
        self.assertTrue(s.cerrada)

    def test_cancelado_antes_de_iniciar_no_programa_ni_mide(self):
        control, s, p = self.sesion([])
        control.cancelar()
        with p:
            r = o.barrer(1000, 2000, 2, Configuracion(), control=control)
        self.assertTrue(r.cancelado)
        self.assertEqual(r.filas, [])
        self.assertEqual(s.programadas, [])

    def test_calibracion_completa_y_cancelada_no_crea_perfil_parcial(self):
        datos = [Lectura(0.48, 1, 1000, 2), Lectura(0.46, 1, 2000, 4)]
        control, s, p = self.sesion(datos)
        with p:
            r = o.calibrar(1000, 2000, 2, Configuracion(), 100, control=control)
        self.assertIsNotNone(r.perfil)
        self.assertEqual(r.perfil['version'], 1)
        self.assertEqual([p['ganancia'] for p in r.puntos], [4.8, 4.6])
        control, s, p = self.sesion(datos)

        def progreso(evento):
            if evento['tipo'] == 'calibracion':
                control.cancelar()

        with p:
            r = o.calibrar(1000, 2000, 2, Configuracion(), 100, control=control, progreso=progreso)
        self.assertTrue(r.cancelado)
        self.assertIsNone(r.perfil)
        self.assertEqual(len(r.puntos), 1)
        self.assertTrue(s.cerrada)

    def test_abierto_y_resistencia_completan_calibracion_compleja(self):
        import cmath
        import math

        import calibracion

        lecturas = []
        for f in (1000, 2000):
            lecturas.extend([lectura_compleja(complex(0.001, f * 0.000001), f)] * 3)
        control, s, p = self.sesion(lecturas)
        with p:
            abierto = o.medir_abierto(1000, 2000, 2, Configuracion(), control=control)
        self.assertTrue(s.osc.circuito_abierto)
        self.assertTrue(s.cerrada)
        lecturas = []
        for punto, g, corr in zip(abierto['puntos'], (4.8, 4.6), (2, 4)):
            a = g * 10 * cmath.exp(-1j * math.radians(corr))
            lecturas.append(
                lectura_compleja(
                    a / 100 + calibracion.complejo(punto, 'residual'), punto['frecuencia']
                )
            )
        control, s, p = self.sesion(lecturas)
        with p:
            r = o.calibrar(1000, 2000, 2, Configuracion(), 100, abierto, control)
        self.assertFalse(r.error, r.error)
        self.assertEqual(r.perfil['version'], 2)
        calibracion.validar(r.perfil)

    def test_parametros_invalidos_no_conectan_usb(self):
        with patch.object(o, 'conectar') as conectar:
            for f in (0, float('nan'), -1):
                with self.assertRaises(ValueError):
                    o.medir(f, Configuracion())
            with self.assertRaises(ValueError):
                o.barrer(1000, 500, 2, Configuracion())
            with self.assertRaises(ValueError):
                o.calibrar(1000, 2000, 2, Configuracion(), 0)
        conectar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
