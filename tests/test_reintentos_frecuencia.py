from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
import medidor_backend as b


class ReintentosFrecuenciaTests(unittest.TestCase):
    def test_medicion_simple_repite_adquisicion_y_calculo_hasta_tres_veces(self):
        rm,osc=MagicMock(),MagicMock()
        with patch.object(b,'_conectar_instrumentos',return_value=(rm,osc,None)),patch.object(b.time,'sleep'),patch.object(b,'_leer_medicion',side_effect=[ValueError('temporal')]*3+[(.05,.1,1000,135)]) as leer:
            res=b.medicion_simple(10)
        self.assertTrue(res['exito'],res)
        self.assertEqual(res['datos']['intentos'],4)
        self.assertEqual(leer.call_count,4)
        self.assertEqual(osc.autoset.call_count,4)
        osc.close.assert_called_once();rm.close.assert_called_once()

    def ejecutar(self, lecturas, calibrar=False):
        eventos = []
        instrumentos = (MagicMock(), MagicMock(), MagicMock())
        with patch.object(b, '_conectar_instrumentos', return_value=instrumentos), patch.object(b, '_leer_medicion', side_effect=lecturas) as leer, patch.object(b, '_preparar_frecuencia') as preparar:
            if calibrar:
                resultado = b.calibrar_barrido(1000, 2000, 2, 100, 1800, progreso=eventos.append)
            else:
                resultado = b.barrido_automatico(1000, 2000, 2, 10, progreso=eventos.append)
        frecuencias = [llamada.args[2] for llamada in preparar.call_args_list]
        for instrumento in instrumentos:
            instrumento.close.assert_called_once()
        return resultado, eventos, frecuencias, leer.call_count

    def test_barrido_recupera_lectura_tras_tres_reintentos_sin_duplicar_punto(self):
        resultado, eventos, frecuencias, cantidad = self.ejecutar(
            [TimeoutError('temporal')] * 3 + [(0.05, 0.1, 1000, 135), (0.05, 0.1, 2000, 135)])
        self.assertTrue(resultado['exito'])
        self.assertEqual(frecuencias, [1000, 1000, 1000, 1000, 2000])
        self.assertEqual(cantidad, 5)
        self.assertEqual(len(resultado['puntos']), 2)
        self.assertEqual(resultado['puntos'][0]['intentos'], 4)
        self.assertEqual(resultado['puntos'][1]['intentos'], 1)
        self.assertEqual(resultado['errores_log'], [])
        self.assertEqual([e['reintento'] for e in eventos if 'reintento' in e], [1, 2, 3])

    def test_error_de_calculo_tambien_repite_adquisicion_completa(self):
        resultado, _, frecuencias, _ = self.ejecutar(
            [(0.05, 0.1, 1000, -60), (0.05, 0.1, 1000, 135), (0.05, 0.1, 2000, 135)])
        self.assertTrue(resultado['exito'])
        self.assertEqual(frecuencias, [1000, 1000, 2000])
        self.assertEqual(resultado['puntos'][0]['intentos'], 2)

    def test_barrido_agota_intentos_y_continua_en_proxima_frecuencia(self):
        resultado, _, frecuencias, cantidad = self.ejecutar(
            [ValueError('lectura inválida')] * 4 + [(0.05, 0.1, 2000, 135)])
        self.assertTrue(resultado['exito'])
        self.assertEqual(frecuencias, [1000, 1000, 1000, 1000, 2000])
        self.assertEqual(cantidad, 5)
        self.assertEqual(resultado['frec_medida'], [2000])
        self.assertEqual(len(resultado['errores_log']), 1)
        self.assertIn('4 intentos', resultado['errores_log'][0])

    def test_calibracion_recupera_lectura_y_guarda_un_solo_punto(self):
        resultado, _, frecuencias, _ = self.ejecutar(
            [ValueError('sin señal')] * 3 + [(0.1, 1, 1000, 170), (0.1, 1, 2000, 160)], calibrar=True)
        self.assertTrue(resultado['exito'])
        self.assertEqual(frecuencias, [1000, 1000, 1000, 1000, 2000])
        self.assertEqual(len(resultado['calibracion']['puntos']), 2)
        self.assertEqual(resultado['calibracion']['puntos'][0]['intentos'], 4)

    def test_calibracion_reintenta_valores_invalidos_antes_de_calcular_ganancia(self):
        resultado, _, frecuencias, _ = self.ejecutar(
            [(0.1, float('nan'), 1000, 170), (0.1, 1, 1000, 170), (0.1, 1, 2000, 160)], calibrar=True)
        self.assertTrue(resultado['exito'])
        self.assertEqual(frecuencias, [1000, 1000, 2000])
        self.assertAlmostEqual(resultado['calibracion']['puntos'][0]['ganancia'], 1.8)

    def test_calibracion_agota_intentos_y_no_ofrece_perfil_incompleto(self):
        resultado, _, frecuencias, _ = self.ejecutar(
            [ValueError('sin señal')] * 4 + [(0.1, 1, 2000, 160)], calibrar=True)
        self.assertFalse(resultado['exito'])
        self.assertNotIn('calibracion', resultado)
        self.assertEqual(frecuencias, [1000, 1000, 1000, 1000, 2000])
        self.assertIn('4 intentos', resultado['error'])

    def test_calibracion_repite_fase_incoherente_y_no_la_guarda(self):
        resultado, eventos, frecuencias, _ = self.ejecutar([
            (0.1, 1, 1000, -11.62), (0.1, 1, 1000, 170),
            (0.1, 1, 2000, 110), (0.1, 1, 2000, 165)], calibrar=True)
        self.assertTrue(resultado['exito'], resultado)
        self.assertEqual(frecuencias, [1000, 1000, 2000, 2000])
        self.assertEqual([p['fase_cruda'] for p in resultado['puntos']], [170, 165])
        self.assertEqual(len([e for e in eventos if 'reintento' in e]), 2)

    def test_calibracion_agota_tres_reintentos_por_fase_incoherente(self):
        resultado, _, frecuencias, _ = self.ejecutar(
            [(0.1, 1, 1000, 170)] + [(0.1, 1, 2000, -1.4)] * 4, calibrar=True)
        self.assertFalse(resultado['exito'])
        self.assertNotIn('calibracion', resultado)
        self.assertEqual(frecuencias, [1000, 2000, 2000, 2000, 2000])

    def test_barrido_repite_captura_de_frecuencia_anterior(self):
        resultado, _, frecuencias, _ = self.ejecutar([
            (0.05, 0.1, 1000, 135), (0.05, 0.1, 1000, 135), (0.05, 0.1, 2000, 135)])
        self.assertTrue(resultado['exito'])
        self.assertEqual(frecuencias, [1000, 2000, 2000])


if __name__ == '__main__':
    unittest.main()
