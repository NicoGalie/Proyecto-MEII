"""Prueba los callbacks reales del selector sin requerir un servidor gráfico."""
import ast
import math
from pathlib import Path
import sys
import runpy
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import MagicMock, patch

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / 'Codigo'))
import medidor_backend as b
import calibracion as ajustes
from test_medicion_calibracion import perfil


class SelectorOriginalTests(unittest.TestCase):
    def setUp(self):
        source = (PROYECTO / 'Codigo/Interfaz.py').read_text()
        funciones = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)]
        self.ui = {'math': math, 'medidor_backend': b, 'messagebox': MagicMock(),
                   '_tarea_en_curso': False, '_calibracion': None, '_equipos_usb': []}
        widgets = ('btn_medir btn_barrido btn_actualizar_equipos btn_calibrar btn_abierto '
                   'btn_curvas_cal chk_calibracion combo_r combo_modo ent_r_cal ent_cal_ini '
                   'ent_cal_fin ent_cal_pasos btn_permisos lbl_calibracion_uso lbl_v_i '
                   'lbl_v_rms lbl_frec lbl_fase lbl_i_rms lbl_z lbl_esr lbl_xs lbl_ganancia '
                   'lbl_tipo_final lbl_valor_final lbl_factor_final lbl_estado ent_f_ini '
                   'ent_f_fin ent_pasos modo_medicion usar_calibracion').split()
        self.ui.update({name: MagicMock() for name in widgets})
        self.ui['modo_medicion'].get.return_value = 'Actual'
        self.ui['usar_calibracion'].get.return_value = False
        self.ui['combo_r'].get.return_value = '10 Ω'
        for nombre, valor in (('ent_f_ini', '1000'), ('ent_f_fin', '10000'), ('ent_pasos', '10')):
            self.ui[nombre].get.return_value = valor
        exec(compile(ast.Module(body=funciones, type_ignores=[]), str(PROYECTO / 'Codigo/Interfaz.py'), 'exec'), self.ui)

    def seleccionar(self, modo):
        self.ui['modo_medicion'].get.return_value = modo
        self.ui['cambiar_modo']()

    def estado(self, nombre):
        return self.ui[nombre].config.call_args.kwargs['state']

    def test_selector_perfil_preservado_y_controles_se_restauran(self):
        guardado = perfil()
        self.ui['_calibracion'] = guardado
        self.ui['usar_calibracion'].get.return_value = True
        self.seleccionar('Original')
        self.assertIsNone(self.ui['_perfil_seleccionado']())
        self.ui['lbl_z'].config.assert_called_with(text='---')
        self.assertIn('Original', self.ui['lbl_calibracion_uso'].config.call_args.kwargs['text'])
        for nombre in ('chk_calibracion', 'btn_abierto', 'btn_calibrar'):
            self.assertEqual(self.estado(nombre), 'disabled')
        self.seleccionar('Actual')
        self.assertIs(self.ui['_perfil_seleccionado'](), guardado)
        self.ui['usar_calibracion'].set.assert_not_called()
        for nombre in ('chk_calibracion', 'btn_abierto', 'btn_calibrar'):
            self.assertEqual(self.estado(nombre), 'normal')

    def test_selector_bloqueado_durante_medicion(self):
        self.ui['_tarea_en_curso'] = True
        self.ui['_actualizar_botones']()
        self.assertEqual(self.estado('combo_modo'), 'disabled')
        self.ui['_tarea_en_curso'] = False
        self.ui['_actualizar_botones']()
        self.assertEqual(self.estado('combo_modo'), 'readonly')

    def test_simple_y_barrido_envian_modo_original_sin_perfil(self):
        self.ui['_calibracion'] = perfil()
        self.ui['usar_calibracion'].get.return_value = True
        self.seleccionar('Original')
        with patch.object(b, 'medicion_simple') as medir, \
             patch.dict(self.ui, {'_iniciar_tarea': lambda op, fin: op()}):
            self.ui['ejecutar_medicion']()
        medir.assert_called_once_with(10, modo='Original')
        reporte = lambda evento: None
        with patch.object(b, 'barrido_automatico') as barrer, \
             patch.dict(self.ui, {'_iniciar_tarea': lambda op, fin, progreso: op(reporte)}):
            self.ui['ejecutar_barrido']()
        barrer.assert_called_once_with(1000, 10000, 10, 10, progreso=reporte, modo='Original')
        with patch.object(b, 'medir_abierto') as abierto, patch.object(b, 'calibrar_barrido') as calibrar:
            self.ui['ejecutar_abierto']()
            self.ui['ejecutar_calibracion']()
        abierto.assert_not_called()
        calibrar.assert_not_called()

    def test_actual_conserva_llamada_y_perfil(self):
        guardado = perfil()
        self.ui['_calibracion'] = guardado
        self.ui['usar_calibracion'].get.return_value = True
        with patch.object(b, 'medicion_simple') as medir, \
             patch.dict(self.ui, {'_iniciar_tarea': lambda op, fin: op()}):
            self.ui['ejecutar_medicion']()
        medir.assert_called_once_with(10, guardado)

    def test_graficos_originales_usan_frecuencias_y_tipo_final(self):
        plt = MagicMock()
        graficar = MagicMock()
        res = {'exito': True, 'modo': 'Original', 'frec_medida': [1000, 2000],
               'esr': [1, 2], 'cap_ind': [1e-6, .002], 'q_d': [.1, 20],
               'tipo': 'INDUCTOR', 'errores_log': []}
        with patch.dict(self.ui, {'plt': plt, '_graficar': graficar}):
            self.ui['mostrar_barrido'](res)
        self.assertEqual(graficar.call_count, 3)
        reactiva = graficar.call_args_list[-1].args
        self.assertEqual(reactiva[2:5], ([1000, 2000], [1e-6, .002], 'Henrios (H)'))
        self.assertIn('Original', self.ui['lbl_estado'].config.call_args.kwargs['text'])


class SelectorTkTests(unittest.TestCase):
    def setUp(self):
        with patch.object(tk.Tk, 'mainloop'), patch.object(ajustes, 'cargar', return_value=None):
            ui = runpy.run_path(str(PROYECTO / 'Codigo/Interfaz.py'))
        self.ui = ui['_iniciar_tarea'].__globals__
        self.root = self.ui['root']
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.ui['plt'].close, 'all')

    def test_selector_real_actual_por_defecto_y_restaura_la_seleccion(self):
        ui = self.ui
        self.assertEqual(ui['modo_medicion'].get(), 'Actual')
        self.assertEqual(ui['combo_modo']['values'], ('Actual', 'Original'))
        self.assertIs(ui['combo_modo'].master.master, ui['frame_config'])
        for seleccion in (True, False):
            guardado = perfil()
            ui['_calibracion'] = guardado
            ui['usar_calibracion'].set(seleccion)
            ui['modo_medicion'].set('Original'); ui['cambiar_modo']()
            self.assertIsNone(ui['_perfil_seleccionado']())
            self.assertTrue(ui['chk_calibracion'].instate(['disabled']))
            self.assertEqual(ui['usar_calibracion'].get(), seleccion)
            ui['modo_medicion'].set('Actual'); ui['cambiar_modo']()
            self.assertEqual(ui['usar_calibracion'].get(), seleccion)
            self.assertIs(ui['_calibracion'], guardado)
            self.assertIs(ui['_perfil_seleccionado'](), guardado if seleccion else None)
        self.root.update()
        self.assertFalse(self.root.tk.call('after', 'info'))

    def test_operacion_real_bloquea_selector_y_envia_original_sin_calibracion(self):
        ui = self.ui
        ui['_calibracion'] = perfil(); ui['usar_calibracion'].set(True)
        ui['modo_medicion'].set('Original'); ui['cambiar_modo']()
        finalizar = threading.Event()
        self.addCleanup(finalizar.set)
        def medir(*args, **kwargs):
            finalizar.wait(2)
            return {'exito': False, 'error': 'Lectura simulada'}
        with patch.object(b, 'medicion_simple', side_effect=medir) as medicion:
            ui['ejecutar_medicion']()
            self.assertTrue(ui['combo_modo'].instate(['disabled']))
            finalizar.set()
            limite = time.monotonic() + 3
            while ui['_tarea_en_curso'] and time.monotonic() < limite:
                self.root.update(); time.sleep(.01)
            self.assertFalse(ui['_tarea_en_curso'])
        medicion.assert_called_once_with(10, modo='Original')
        self.assertTrue(ui['combo_modo'].instate(['readonly', '!disabled']))
        self.assertTrue(ui['usar_calibracion'].get())


if __name__ == '__main__':
    unittest.main()
