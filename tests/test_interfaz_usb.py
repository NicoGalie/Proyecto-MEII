from pathlib import Path
import runpy
import sys
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / 'Codigo'))


class InterfazUSBTests(unittest.TestCase):
    def setUp(self):
        import calibracion
        with patch.object(tk.Tk, 'mainloop'), patch.object(calibracion, 'cargar', return_value=None):
            ui = runpy.run_path(str(PROYECTO / 'Codigo/Interfaz.py'))
        self.ui = ui['_iniciar_tarea'].__globals__
        self.root = self.ui['root']
        self.addCleanup(self.root.destroy)
        self.equipo = {'nombre':'Marca Modelo', 'serie':'SERIE', 'vendor':'1234',
                       'producto':'5678', 'estado':'sin_permisos'}

    def esperar(self, condicion):
        limite = time.monotonic() + 3
        while not condicion() and time.monotonic() < limite:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(condicion())

    def mostrar(self, equipos):
        self.ui['mostrar_equipos']({'exito':True, 'equipos':equipos})
        self.ui['_actualizar_botones']()

    def test_label_y_boton_ante_conexion_permiso_y_desconexion(self):
        self.mostrar([self.equipo])
        self.assertIn('Marca Modelo', self.ui['lbl_equipos']['text'])
        self.assertIn('requiere permiso USB', self.ui['lbl_equipos']['text'])
        self.assertFalse(self.ui['btn_permisos'].instate(['disabled']))
        self.mostrar([{**self.equipo, 'estado':'conectado'}])
        self.assertIn('listo', self.ui['lbl_equipos']['text'])
        self.assertTrue(self.ui['btn_permisos'].instate(['disabled']))
        self.mostrar([])
        self.assertIn('ninguno', self.ui['lbl_equipos']['text'])

    def test_actualizacion_solo_al_pulsar_boton(self):
        resultado = {'exito':True, 'equipos':[self.equipo]}
        with patch.object(self.ui['instrumentos_usb'], 'detectar_instrumentos', return_value=resultado) as detectar:
            self.root.update()
            detectar.assert_not_called()
            self.assertFalse(self.root.tk.call('after', 'info'))
            self.ui['btn_actualizar_equipos'].invoke()
            self.esperar(lambda: not self.ui['_tarea_en_curso'])
            detectar.assert_called_once_with(actualizar=True)
            self.assertIn('Marca Modelo', self.ui['lbl_equipos']['text'])
            self.root.update()
            self.assertFalse(self.root.tk.call('after', 'info'))
            self.assertEqual(detectar.call_count, 1)

    def test_actualizacion_bloqueada_durante_otra_operacion(self):
        fin = threading.Event()
        self.addCleanup(fin.set)
        self.ui['_iniciar_tarea'](lambda: (fin.wait(2), {'exito':True})[1], lambda resultado: None)
        with patch.object(self.ui['instrumentos_usb'], 'detectar_instrumentos') as detectar:
            self.ui['actualizar_equipos']()
            detectar.assert_not_called()
        self.assertTrue(self.ui['btn_actualizar_equipos'].instate(['disabled']))
        fin.set()
        self.esperar(lambda: not self.ui['_tarea_en_curso'])

    def test_cancelar_permiso_no_consulta_y_permite_reintentar(self):
        self.mostrar([self.equipo])
        with patch.object(self.ui['instrumentos_usb'], 'habilitar_permisos', return_value={'exito':False,'error':'Cancelado'}), patch.object(self.ui['instrumentos_usb'], 'detectar_instrumentos') as detectar, patch.object(self.ui['messagebox'], 'showerror') as mensaje:
            self.ui['ejecutar_permisos']()
            self.esperar(lambda: not self.ui['_tarea_en_curso'])
            detectar.assert_not_called()
            mensaje.assert_called_once_with('Permisos USB', 'Cancelado')
        self.assertFalse(self.ui['btn_permisos'].instate(['disabled']))

    def test_autorizacion_exitosa_espera_actualizacion_manual(self):
        self.mostrar([self.equipo])
        with patch.object(self.ui['instrumentos_usb'], 'habilitar_permisos', return_value={'exito':True}), patch.object(self.ui['instrumentos_usb'], 'detectar_instrumentos') as detectar:
            self.ui['ejecutar_permisos']()
            self.esperar(lambda: not self.ui['_tarea_en_curso'])
            detectar.assert_not_called()
        self.assertIn('Actualizar equipos', self.ui['lbl_equipos']['text'])
        self.assertTrue(self.ui['btn_permisos'].instate(['disabled']))


if __name__ == '__main__':
    unittest.main()
