import runpy
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import calibracion
import operaciones
from calculos import calcular
from configuracion import Configuracion
from falsos import perfil_simulado
from interfaz.aplicacion import Aplicacion
from modelos import Fila, Lectura, ResultadoBarrido, ResultadoCalibracion


class InterfazTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        with (
            patch('interfaz.aplicacion.cargar_configuracion', return_value=Configuracion()),
            patch.object(calibracion, 'cargar', return_value=None),
        ):
            self.app = Aplicacion(self.root)
        self.addCleanup(self.root.destroy)

    def entrada(self, campo, texto):
        campo.delete(0, 'end')
        campo.insert(0, texto)

    def esperar(self):
        limite = time.monotonic() + 4
        while self.app.tareas.activa and time.monotonic() < limite:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.tareas.activa)

    def test_importar_punto_de_entrada_no_abre_ventanas(self):
        with patch.object(tk, 'Tk') as crear:
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'Codigo/Interfaz.py'))
        crear.assert_not_called()

    def test_actualizacion_manual_y_habilitacion_sin_consultas_periodicas(self):
        equipo = dict(
            nombre='TEKTRONIX TBS2102B',
            serie='SERIE',
            estado='sin_permisos',
            vendor='0699',
            producto='036a',
        )
        with patch(
            'instrumentos_usb.detectar_instrumentos',
            return_value=dict(exito=True, equipos=[equipo]),
        ) as detectar:
            self.root.update()
            detectar.assert_not_called()
            self.assertTrue(self.app.estado.winfo_ismapped())
            self.assertFalse(self.root.tk.call('after', 'info'))
            self.app.hardware.actualizar.invoke()
            self.esperar()
        detectar.assert_called_once_with(actualizar=True)
        self.assertFalse(self.app.hardware.permisos.instate(['disabled']))
        with (
            patch('instrumentos_usb.habilitar_permisos', return_value=dict(exito=True)),
            patch('instrumentos_usb.detectar_instrumentos') as detectar,
        ):
            self.app.hardware.permisos.invoke()
            self.esperar()
            detectar.assert_not_called()
        self.assertIn('permiso configurado', self.app.hardware.identificacion['text'])
        self.assertFalse(self.root.tk.call('after', 'info'))

    def test_simple_envia_frecuencia_rs_y_promedio_y_muestra_modelo_nominal(self):
        a = self.app
        self.entrada(a.simple.frecuencia, '7500,5')
        self.entrada(a.hardware.rs, '47,2')
        a.simple.promediar.set(True)
        self.entrada(a.simple.segundos, '2,5')
        a.usar.set(True)
        dato = calcular(Lectura(0.5, 1, 7500.5, 45), Configuracion(47.2), objetivo=7500.5)
        with patch.object(operaciones, 'medir', return_value=dato) as medir:
            a.simple.medir.invoke()
            self.esperar()
        args = medir.call_args.args
        self.assertEqual(args[:5], (7500.5, Configuracion(47.2), None, True, 2.5))
        self.assertIn('7500.5', a.simple.datos['text'])
        self.assertIn('Ganancia', a.simple.datos['text'])

    def test_cancelar_barrido_desbloquea_y_conserva_tabla_parcial(self):
        a = self.app
        listo = threading.Event()
        fila = Fila(1000, medicion=calcular(Lectura(0.5, 1, 1000, 0), Configuracion()), intentos=1)

        def barrer(*args):
            control, progreso = args[-2:]
            progreso(dict(tipo='punto', indice=1, total=10, fila=fila))
            listo.set()
            control.evento.wait(2)
            return ResultadoBarrido([fila], cancelado=control.solicitada)

        with patch.object(operaciones, 'barrer', side_effect=barrer):
            a.barrido.iniciar.invoke()
            self.assertTrue(a.hardware.rs.instate(['disabled']))
            self.assertFalse(a.barrido.cancelar.instate(['disabled']))
            self.assertTrue(a.simple.medir.instate(['disabled']))
            self.assertTrue(listo.wait(1))
            a.barrido.cancelar.invoke()
            self.esperar()
        filas = a.barrido.tabla.tree.get_children()
        self.assertEqual(len(filas), 1)
        self.assertIn('Cancelado', a.barrido.resumen['text'])
        self.assertFalse(a.hardware.rs.instate(['disabled']))
        self.assertTrue(a.barrido.cancelar.instate(['disabled']))
        self.assertFalse(self.root.tk.call('after', 'info'))

    def test_copiar_tabla_errores_no_tienen_ceros_ficticios(self):
        a = self.app
        a.barrido.mostrar(
            ResultadoBarrido(
                [Fila(1000, 'ERROR', error='Sin señal', intentos=4), Fila(2000, 'CANCELADO')], True
            )
        )
        a.barrido.tabla.copiar()
        lineas = self.root.clipboard_get().splitlines()
        self.assertEqual(len(lineas), 3)
        self.assertIn('Calibración', lineas[0])
        self.assertIn('ERROR: Sin señal', lineas[1])
        self.assertIn('CANCELADO', lineas[2])
        self.assertEqual(lineas[1].split('\t')[1:15], ['—'] * 13 + ['4'])

    def test_calibracion_completa_guarda_y_cancelada_preserva_el_archivo(self):
        a = self.app
        nuevo = perfil_simulado()
        self.entrada(a.calibracion.fin, '2000')
        self.entrada(a.calibracion.cantidad, '2')
        self.entrada(a.calibracion.referencia, '100')
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(calibracion, 'RUTA_CALIBRACION', Path(d) / 'cal.json'),
        ):
            with patch.object(
                operaciones, 'calibrar', return_value=ResultadoCalibracion(nuevo['puntos'], nuevo)
            ):
                a.calibracion.calibrar.invoke()
                self.esperar()
            self.assertEqual(calibracion.cargar(), nuevo)
            self.assertTrue(a.usar.get())
            previo = calibracion.RUTA_CALIBRACION.read_bytes()
            with patch.object(
                operaciones,
                'calibrar',
                return_value=ResultadoCalibracion(nuevo['puntos'][:1], cancelado=True),
            ):
                a.calibracion.calibrar.invoke()
                self.esperar()
            self.assertEqual(calibracion.RUTA_CALIBRACION.read_bytes(), previo)
            self.assertIs(a.perfil, nuevo)

    def test_campos_invalidos_no_inician_trabajo_ni_muestran_datos_anteriores_como_nuevos(self):
        a = self.app
        a.simple.resultado.configure(text='Lectura anterior: 100 Ω')
        self.entrada(a.simple.frecuencia, 'nan')
        with patch.object(operaciones, 'medir') as medir:
            a.simple.medir.invoke()
        medir.assert_not_called()
        self.assertFalse(a.tareas.activa)
        self.assertIn('positivo', a.estado['text'])
        self.assertEqual(a.simple.resultado['text'], 'Sin medición válida.')


if __name__ == '__main__':
    unittest.main()
