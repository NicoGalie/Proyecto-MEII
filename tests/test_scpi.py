import unittest
from unittest.mock import MagicMock, patch

import osciloscopios as o
from cancelacion import Cancelacion, Cancelado
from falsos import GEN, TEK, UNIT, ControlReloj, Reloj, TekPromedio, TekSimulado
from instrumentos import Sesion, conectar, leer_numero


class SCPITests(unittest.TestCase):
    def medir(self, recurso, reloj, promedio=None, control=None):
        control = control or ControlReloj(reloj)
        osc = o.Osciloscopio(recurso, TEK, 'tektronix_tbs2000b', control)

        def leer(s, c, max_reintentos=5):
            return leer_numero(s, c, control, max_reintentos)

        with patch.object(o.time, 'monotonic', reloj.monotonic):
            return osc.leer(leer) if promedio is None else osc.leer_promediado(leer, promedio)

    def restaurado(self, recurso):
        for nombre, valor in recurso.originales.items():
            self.assertEqual(recurso.valores[nombre], valor, nombre)
        self.assertEqual((recurso.timeout, recurso.chunk_size), (4000, 20480))

    def test_captura_comun_y_fase_del_ina_y_restauracion(self):
        r = TekSimulado(fase=45)
        l = self.medir(r, Reloj())
        self.assertAlmostEqual(l[0], 0.05, delta=0.0001)
        self.assertAlmostEqual(l[1], 1, delta=0.001)
        self.assertAlmostEqual(l[2], 1000, delta=0.1)
        self.assertAlmostEqual(l[3], 45, delta=0.05)
        self.assertEqual(r.descargas, [('CH1', '0'), ('CH2', '0')])
        self.restaurado(r)

    def test_recorte_transferencia_y_timeout_no_dejan_configuracion_intermedia(self):
        for opciones in ({'recortar': True}, {'truncar': True}, {'fallo_opc': True}):
            r = TekSimulado(**opciones)
            with self.subTest(opciones=opciones), self.assertRaises((ValueError, TimeoutError)):
                self.medir(r, Reloj())
            self.restaurado(r)

    def test_promedio_ajustable_y_reduccion_de_ruido(self):
        for segundos in (0.5, 4, 12):
            reloj = Reloj()
            r = TekPromedio(reloj, fase=45)
            l, m = self.medir(r, reloj, segundos)
            self.assertEqual(m['tiempo_promedio_s'], segundos)
            self.assertGreaterEqual(m['adquisiciones_promedio'], 2)
            self.assertIn('ACQuire:NUMAVg 512', r.comandos)
            self.restaurado(r)
        reloj = Reloj()
        r = TekPromedio(reloj, ruido=True, fase=45)
        with self.assertRaises(ValueError):
            self.medir(r, reloj)
        reloj = Reloj()
        r = TekPromedio(reloj, ruido=True, fase=45)
        l, m = self.medir(r, reloj, 4)
        self.assertAlmostEqual(l[3], 45, delta=0.2)
        self.restaurado(r)

    def test_cancelacion_durante_promedio_restaura_y_no_descarga_datos(self):
        reloj = Reloj()
        r = TekPromedio(reloj, fase=45)
        control = ControlReloj(reloj, cancelar_en=2)
        with self.assertRaises(Cancelado):
            self.medir(r, reloj, 4, control)
        self.assertEqual(r.descargas, [])
        self.restaurado(r)

    def test_promedio_sin_capturas_nuevas_es_error(self):
        reloj = Reloj()
        r = TekPromedio(reloj, sin_capturas=True)
        with self.assertRaisesRegex(ValueError, 'dos adquisiciones nuevas'):
            self.medir(r, reloj, 2)
        self.restaurado(r)

    def test_unit_mantiene_consultas_y_orden_de_fase(self):
        r = MagicMock()
        r.query.side_effect = ['.05', '1', '1000', '45']
        control = Cancelacion()
        osc = o.Osciloscopio(r, UNIT, 'uni_t', control)
        lector = lambda s, c: leer_numero(s, c, control)
        self.assertEqual(osc.leer(lector), (0.05, 1, 1000, 45))
        self.assertEqual(r.query.call_args_list[-1].args, (':MEASure:PHASe? CHANnel2,CHANnel1',))
        with self.assertRaises(ValueError):
            osc.leer_promediado(lector, 2)

    def test_sesion_programa_generador_y_espera_antes_de_leer(self):
        reloj = Reloj()
        control = ControlReloj(reloj)
        osc, gen = MagicMock(), MagicMock()
        sesion = Sesion(osc, gen, control)
        sesion.preparar(5000.5)
        gen.write.assert_called_once_with(':CHANnel1:BASE:FREQuency 5000.5')
        osc.autoset.assert_called_once()
        self.assertEqual(osc.frecuencia_objetivo, 5000.5)
        self.assertEqual(reloj.actual, 3.5)
        control.cancelar()
        with self.assertRaises(Cancelado):
            sesion.preparar(6000)
        self.assertEqual(gen.write.call_count, 1)

    def test_identificacion_y_cierre_de_todos_los_recursos(self):
        rm, tek, gen = MagicMock(), MagicMock(), MagicMock()
        rm.list_resources.return_value = ['USB::TEK', 'USB::GEN']
        rm.open_resource.side_effect = [tek, gen]
        tek.query.return_value = TEK
        gen.query.return_value = GEN
        with patch('instrumentos.pyvisa.ResourceManager', return_value=rm):
            with self.assertRaises(RuntimeError):
                with conectar(Cancelacion()) as s:
                    self.assertEqual(s.identidad['modelo'], 'TBS2102B')
                    raise RuntimeError('simulado')
        tek.close.assert_called_once()
        gen.close.assert_called_once()
        rm.close.assert_called_once()
        rm.list_resources.assert_called_once_with('USB?*::INSTR')

    def test_no_hay_generador_o_hay_dos_osciloscopios_no_programa_frecuencia(self):
        for identidades in ([TEK], [TEK, TEK, GEN]):
            rm = MagicMock()
            recursos = [MagicMock() for _ in identidades]
            for r, idn in zip(recursos, identidades):
                r.query.return_value = idn
            rm.list_resources.return_value = [f'USB::{i}' for i in range(len(recursos))]
            rm.open_resource.side_effect = recursos
            with (
                patch('instrumentos.pyvisa.ResourceManager', return_value=rm),
                self.assertRaises(ValueError),
            ):
                with conectar(Cancelacion()):
                    pass
            for r in recursos:
                r.close.assert_called_once()
                r.write.assert_not_called()

    def test_cancelacion_interrumpe_esperas_y_respuestas_invalidas(self):
        control = Cancelacion()
        control.cancelar()
        with self.assertRaises(Cancelado):
            control.esperar(30)
        r = MagicMock()
        with self.assertRaises(Cancelado):
            leer_numero(r, 'VRMS?', control)
        r.query.assert_not_called()
        r.query.side_effect = ['nan', '1.25']
        control = ControlReloj(Reloj())
        self.assertEqual(leer_numero(r, 'VRMS?', control), 1.25)


if __name__ == '__main__':
    unittest.main()
