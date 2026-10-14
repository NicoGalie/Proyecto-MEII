from pathlib import Path
import math
import random
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
import medidor_backend as b
import modo_original as original
from osciloscopios import Osciloscopio


class ModoOriginalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Oráculo independiente: el backend publicado, sin tocar el checkout
        # ni abrir instrumentos. No ejecuta ninguna función de adquisición.
        raiz = Path(__file__).resolve().parents[1]
        fuente = subprocess.run(['git', 'show', '03d21e8:Codigo/medidor_backend.py'],
                                cwd=raiz, check=True, capture_output=True, text=True).stdout
        cls.publicado = {}
        exec(compile(fuente, 'git:03d21e8:Codigo/medidor_backend.py', 'exec'), cls.publicado)

    def test_calculos_coinciden_con_el_commit_original(self):
        rng = random.Random(21)
        casos = [(rng.uniform(.001, 2), rng.uniform(.001, 3), rng.uniform(1, 1e5),
                  rng.uniform(-360, 360), rng.choice([10, 100, 1000])) for _ in range(100)]
        casos += [(.05, .1, 1000, 180+fase, 10) for fase in (-2.001, -2, -.1, 0, .1, 2, 2.001, 95)]
        casos += [(0, .1, 1000, 135, 10), (.05, .1, 0, 135, 10), (.05, .1, 1000, 135, 0)]
        for caso in casos:
            esperado = self.publicado['_procesar_matematica'](*caso)
            recibido = original._procesar_matematica(*caso)
            with self.subTest(caso=caso):
                self.assertEqual(recibido.keys(), esperado.keys())
                for k, valor in esperado.items():
                    if isinstance(valor, float) and math.isnan(valor):
                        self.assertTrue(math.isnan(recibido[k]))
                    else:
                        self.assertEqual(recibido[k], valor)

    def test_series_y_tipo_final_coinciden_con_el_barrido_publicado(self):
        valores = [str(x) for x in (.05, .1, 135, .05, 9.9e37, 135, .05, .1, -135, .05, .1, 180)]
        recurso, gen = MagicMock(), MagicMock()
        recurso.query.side_effect = valores
        publicado = self.publicado
        with patch.dict(publicado, {'_conectar_instrumentos': lambda **kw: (recurso, gen)}), \
             patch.object(original.time, 'sleep'), patch('builtins.print'):
            esperado = publicado['barrido_automatico'](1000, 4000, 4, 10)
        recurso = MagicMock()
        recurso.query.side_effect = valores
        osc = Osciloscopio(recurso, 'UNI-T,UTD2102,SERIAL,1', 'uni_t')
        with patch.object(b, '_conectar_instrumentos', return_value=(MagicMock(), osc, MagicMock())), \
             patch.object(original.time, 'sleep'):
            recibido = b.barrido_automatico(1000, 4000, 4, 10, modo='Original')
        self.assertTrue(esperado['exito'], esperado)
        self.assertTrue(recibido['exito'], recibido)
        for campo in ('exito', 'frec_medida', 'esr', 'cap_ind', 'q_d', 'tipo'):
            self.assertEqual(recibido[campo], esperado[campo])
        self.assertEqual(len(recibido['errores_log']), len(esperado['errores_log']))
        self.assertEqual(recibido['tipo'], 'RESISTENCIA')

    def test_agotar_respuestas_textuales_conserva_las_cinco_pausas(self):
        s = MagicMock()
        s.query.return_value = 'NULL'
        with patch.object(original.time, 'sleep') as pausa, self.assertRaisesRegex(ValueError, "'NULL'"):
            original._leer_seguro(s, 'RMS?')
        self.assertEqual(s.query.call_count, 5)
        self.assertEqual(pausa.call_args_list, [call(1.0)] * 5)

    def test_umbral_original_y_esr_negativa_a_cero(self):
        for fase in (-2, -.5, 0, .5, 2):
            datos = original._procesar_matematica(.05, .1, 1000, fase + 180, 10)
            self.assertEqual(datos['tipo'], 'RESISTENCIA')
            self.assertEqual(datos['valor_num'], 0)
        datos = original._procesar_matematica(.05, .1, 1000, -85, 10)
        self.assertEqual(datos['tipo'], 'INDUCTOR')
        self.assertEqual(datos['esr_num'], 0)
        self.assertTrue(math.isinf(datos['factor_num']))
        with self.assertRaisesRegex(ValueError, 'ESR negativa'):
            b._procesar_matematica(.05, .1, 1000, -85, 10)

    def test_capacitor_inductor_y_ganancia_nominal(self):
        for xs, tipo, valor in ((-1 / (2 * math.pi * 1000 * 1e-6), 'CAPACITOR', 1e-6),
                                (2 * math.pi * 1000 * .01, 'INDUCTOR', .01)):
            z = math.hypot(10, xs)
            fase = math.degrees(math.atan2(xs, 10))
            datos = original._procesar_matematica(.05, z * .001, 1000, fase + 180, 10)
            self.assertEqual(datos['tipo'], tipo)
            self.assertAlmostEqual(datos['esr_num'], 10)
            self.assertAlmostEqual(datos['valor_num'], valor)

    def test_simple_ignora_calibracion_no_autoset_no_ajuste_no_reintento_completo(self):
        rm, osc = MagicMock(), MagicMock()
        osc.leer_original.return_value = (.05, .1, 1000, 135)
        with patch.object(b, '_conectar_instrumentos', return_value=(rm, osc, None)), \
             patch.object(b, 'validar_calibracion', side_effect=AssertionError('calibración aplicada')), \
             patch.object(b, '_leer_medicion', side_effect=AssertionError('ajuste aplicado')):
            res = b.medicion_simple(10, {'perfil': 'incompatible'}, modo='Original')
        self.assertTrue(res['exito'], res)
        self.assertEqual(res['datos']['modo'], 'Original')
        self.assertFalse(res['datos']['calibrada'])
        self.assertEqual(res['datos']['ganancia_num'], 5)
        osc.autoset.assert_not_called()
        osc.autoset_original.assert_not_called()
        osc.leer_original.assert_called_once_with(original._leer_seguro, None)
        osc.close.assert_called_once()
        rm.close.assert_called_once()
        osc.reset_mock()
        osc.leer_original.side_effect = TimeoutError('sin señal')
        with patch.object(b, '_conectar_instrumentos', return_value=(rm, osc, None)):
            res = b.medicion_simple(10, modo='Original')
        self.assertFalse(res['exito'])
        self.assertEqual(osc.leer_original.call_count, 1)

    def test_barrido_usa_frecuencia_programada_omite_fallo_y_conserva_tipo_final(self):
        rm, osc, gen = MagicMock(), MagicMock(), MagicMock()
        # Una falla se omite directamente: no hay nuevos intentos de ese punto.
        osc.leer_original.side_effect = [(0.05, .1, 1000, 135), TimeoutError('fallo'),
                                         (.05, .1, 3000, -135)]
        eventos = []
        with patch.object(b, '_conectar_instrumentos', return_value=(rm, osc, gen)), \
             patch.object(original.time, 'sleep') as pausa, \
             patch.object(b, 'validar_calibracion', side_effect=AssertionError('calibración aplicada')):
            res = b.barrido_automatico(1000, 3000, 3, 10, {'invalido': True},
                                      progreso=eventos.append, modo='Original')
        self.assertTrue(res['exito'], res)
        self.assertEqual(res['frec_medida'], [1000, 3000])
        self.assertEqual(res['tipo'], 'INDUCTOR')
        self.assertEqual(len(res['cap_ind']), 2)
        self.assertEqual(len(res['errores_log']), 1)
        self.assertEqual(osc.leer_original.call_args_list,
                         [call(original._leer_seguro, f) for f in (1000, 2000, 3000)])
        self.assertEqual(gen.write.call_args_list,
                         [call(f':CHANnel1:BASE:FREQuency {float(f)}') for f in (1000, 2000, 3000)])
        self.assertEqual(osc.autoset_original.call_count, 3)
        self.assertEqual(pausa.call_args_list, [call(.5), call(3.0)] * 3)
        self.assertFalse(any('reintento' in e for e in eventos))
        for inst in (rm, osc, gen):
            inst.close.assert_called_once()

    def test_reintentos_textuales_y_codigo_numerico_del_original(self):
        recurso = MagicMock()
        recurso.query.side_effect = ['NULL'] * 4 + ['.05']
        with patch.object(original.time, 'sleep'):
            self.assertEqual(original._leer_seguro(recurso, 'RMS?'), .05)
        self.assertEqual(recurso.query.call_count, 5)
        osc = MagicMock()
        osc.leer_original.return_value = (.05, 9.9e37, 1000, 135)
        with self.assertRaisesRegex(ValueError, 'código de error numérico'):
            original._leer(osc)


class TekOriginalTests(unittest.TestCase):
    def recurso(self):
        s = MagicMock()
        originales = {'MEASUrement:IMMed:TYPe?': 'MEAN', 'MEASUrement:IMMed:SOUrce1?': 'CH1',
                      'MEASUrement:IMMed:SOUrce2?': 'CH2', 'MEASUrement:GATing?': 'CURSOR'}
        s.query.side_effect = lambda comando: originales[comando]
        return s, Osciloscopio(s, 'TEKTRONIX,TBS2102B,C022681,1', 'tektronix_tbs2000b')

    def test_rms_frecuencia_fase_automaticos_orden_canales_y_restauracion(self):
        s, osc = self.recurso()
        leer = MagicMock(side_effect=[.05, .1, 1000, 135])
        with patch.object(original.time, 'sleep'):
            self.assertEqual(osc.leer_original(leer), (.05, .1, 1000, 135))
        s.query_binary_values.assert_not_called()
        s.write.assert_has_calls([
            call('MEASUrement:GATing OFF'),
            call('MEASUrement:IMMed:SOUrce1 CH1'), call('MEASUrement:IMMed:TYPe RMS'),
            call('MEASUrement:IMMed:SOUrce1 CH2'), call('MEASUrement:IMMed:TYPe RMS'),
            call('MEASUrement:IMMed:SOUrce1 CH2'), call('MEASUrement:IMMed:TYPe FREQuency'),
            call('MEASUrement:IMMed:SOUrce1 CH2'), call('MEASUrement:IMMed:SOUrce2 CH1'),
            call('MEASUrement:IMMed:TYPe PHAse'),
            call('MEASUrement:IMMed:TYPe MEAN'), call('MEASUrement:IMMed:SOUrce1 CH1'),
            call('MEASUrement:IMMed:SOUrce2 CH2'), call('MEASUrement:GATing CURSOR')])
        self.assertEqual(leer.call_count, 4)
        self.assertFalse(any('ACQuire:' in c.args[0] or 'SCAle' in c.args[0]
                             for c in s.write.call_args_list))

    def test_barrido_no_consulta_frecuencia_y_fallo_restaura_ajustes(self):
        s, osc = self.recurso()
        with patch.object(original.time, 'sleep'):
            res = osc.leer_original(MagicMock(side_effect=[.05, .1, 135]), 4321)
        self.assertEqual(res, (.05, .1, 4321, 135))
        self.assertNotIn(call('MEASUrement:IMMed:TYPe FREQuency'), s.write.call_args_list)
        s.reset_mock()
        with patch.object(original.time, 'sleep'), self.assertRaises(TimeoutError):
            osc.leer_original(MagicMock(side_effect=TimeoutError('USB')))
        self.assertEqual(s.write.call_args_list[-4:], [call('MEASUrement:IMMed:TYPe MEAN'),
            call('MEASUrement:IMMed:SOUrce1 CH1'), call('MEASUrement:IMMed:SOUrce2 CH2'),
            call('MEASUrement:GATing CURSOR')])
        s.reset_mock()
        osc.autoset_original()
        s.write.assert_called_once_with('AUTOSet EXECute')

    def test_convencion_target_reference_con_adelanto_y_atraso(self):
        # Fórmula publicada por Tektronix: (t_ref - t_target) / T * 360.
        # Simula medidas automáticas; no descarga ni ajusta muestras.
        for fase_ch2 in (135, -135):
            s, osc = self.recurso()
            estado = {'CH1': 0, 'CH2': -fase_ch2 / 360 / 1000}
            fuente = {'tipo': 'MEAN', 'uno': 'CH1', 'dos': 'CH2'}
            def escribir(cmd):
                clave, valor = cmd.split(' ', 1)
                if clave.endswith(':SOUrce1'): fuente['uno'] = valor
                elif clave.endswith(':SOUrce2'): fuente['dos'] = valor
                elif clave.endswith(':TYPe'): fuente['tipo'] = valor
            def consultar(cmd):
                if cmd != 'MEASUrement:IMMed:VALue?':
                    return {'MEASUrement:IMMed:TYPe?': 'MEAN', 'MEASUrement:IMMed:SOUrce1?': 'CH1',
                            'MEASUrement:IMMed:SOUrce2?': 'CH2', 'MEASUrement:GATing?': 'OFF'}[cmd]
                if fuente['tipo'] == 'RMS': return '.05' if fuente['uno'] == 'CH1' else '.1'
                if fuente['tipo'] == 'FREQuency': return '1000'
                return str((estado[fuente['dos']] - estado[fuente['uno']]) * 1000 * 360)
            s.write.side_effect = escribir
            s.query.side_effect = consultar
            with patch.object(original.time, 'sleep'):
                lecturas = osc.leer_original(original._leer_seguro)
            self.assertAlmostEqual(lecturas[3], fase_ch2)
            resultado = original._procesar_matematica(*lecturas, 10)
            self.assertEqual(resultado['tipo'], 'CAPACITOR' if fase_ch2 == 135 else 'INDUCTOR')
            s.query_binary_values.assert_not_called()


if __name__ == '__main__':
    unittest.main()
