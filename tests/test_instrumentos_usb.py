import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / 'Codigo'))
import instrumentos_usb as usb

spec = importlib.util.spec_from_file_location('configurar_usb', PROYECTO / 'linux/configurar_usb.py')
configurador = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configurador)


class InstrumentosUSBTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.sysfs = Path(self.temporal.name) / 'usb'
        self.sysfs.mkdir()
        self.reglas = Path(self.temporal.name) / 'rules'
        self.reglas.mkdir()
        self.dispositivo = self.crear_dispositivo('1-1', '1234', '5678', 'fe', '03')
        self.crear_dispositivo('1-2', '046d', 'c52f', '03', '01')
        usb._identificaciones.clear()
        for modulo in (usb, configurador):
            parche = patch.object(modulo, 'SYSFS_USB', self.sysfs)
            parche.start()
            self.addCleanup(parche.stop)

    def crear_dispositivo(self, nombre, vendor, producto, clase, subclase):
        dispositivo = self.sysfs / nombre
        dispositivo.mkdir()
        for clave, valor in {'idVendor':vendor, 'idProduct':producto, 'busnum':'1',
                             'devnum':'6', 'serial':'SERIE', 'manufacturer':'Marca',
                             'product':'Instrumento nuevo'}.items():
            (dispositivo / clave).write_text(valor)
        interfaz = dispositivo / f'{nombre}:1.0'
        interfaz.mkdir()
        for clave, valor in {'bInterfaceClass':clase, 'bInterfaceSubClass':subclase,
                             'bInterfaceNumber':'00'}.items():
            (interfaz / clave).write_text(valor)
        return dispositivo

    def test_detecta_instrumento_nuevo_sin_permiso_y_excluye_receptor(self):
        with patch.object(usb.os, 'access', return_value=False), patch.object(usb.pyvisa, 'ResourceManager') as visa:
            resultado = usb.detectar_instrumentos()
        self.assertTrue(resultado['exito'])
        self.assertEqual(len(resultado['equipos']), 1)
        self.assertEqual(resultado['equipos'][0]['estado'], 'sin_permisos')
        self.assertEqual(resultado['equipos'][0]['nombre'], 'Marca Instrumento nuevo')
        visa.assert_not_called()

    def test_identifica_al_habilitar_cachea_y_detecta_reconexion(self):
        rm = MagicMock()
        inst = rm.open_resource.return_value.__enter__.return_value
        inst.query.return_value = 'Marca,Modelo preciso,SERIE,1.0'
        with patch.object(usb.os, 'access', return_value=True), patch.object(usb.pyvisa, 'ResourceManager', return_value=rm):
            primero = usb.detectar_instrumentos()
            usb.detectar_instrumentos()
            self.assertEqual(rm.open_resource.call_count, 1)
            self.assertEqual(primero['equipos'][0]['nombre'], 'Marca Modelo preciso')
            (self.dispositivo / 'devnum').write_text('7')
            usb.detectar_instrumentos()
            self.assertEqual(rm.open_resource.call_count, 2)
            usb.detectar_instrumentos(actualizar=True)
            self.assertEqual(rm.open_resource.call_count, 3)
        self.assertEqual(rm.close.call_count, 3)

    def test_instrumento_sin_respuesta_no_figura_como_listo(self):
        rm = MagicMock()
        rm.open_resource.return_value.__enter__.return_value.query.side_effect = TimeoutError('sin respuesta')
        with patch.object(usb.os, 'access', return_value=True), patch.object(usb.pyvisa, 'ResourceManager', return_value=rm):
            resultado = usb.detectar_instrumentos()
        self.assertEqual(resultado['equipos'][0]['estado'], 'sin_respuesta')
        rm.close.assert_called_once()

    def test_cancelacion_y_exito_de_autorizacion(self):
        equipos = [{'vendor':'1234', 'producto':'5678', 'estado':'sin_permisos'}]
        with patch.object(usb.subprocess, 'run', return_value=subprocess.CompletedProcess([],126,'','cancelado')) as ejecutar:
            self.assertFalse(usb.habilitar_permisos(equipos)['exito'])
            self.assertEqual(ejecutar.call_args.args[0][-1], '1234:5678')
            self.assertEqual(ejecutar.call_args.args[0][:2], ['pkexec','/usr/bin/python3'])
        with patch.object(usb.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,'','')):
            self.assertTrue(usb.habilitar_permisos(equipos)['exito'])

    def test_regla_persistente_restringida_al_instrumento_seleccionado(self):
        with patch.object(configurador, 'REGLAS_USB', self.reglas), patch.object(configurador.subprocess, 'run') as ejecutar:
            configurador.configurar(['1234:5678'])
        regla = self.reglas / '70-me2-1234-5678.rules'
        self.assertIn('ATTR{idVendor}=="1234", ATTR{idProduct}=="5678"', regla.read_text())
        self.assertIn('MODE="0660"', regla.read_text())
        self.assertEqual(ejecutar.call_count, 3)

    def test_rechaza_otros_dispositivos_y_argumentos_invalidos_sin_escribir(self):
        for argumento in ['046d:c52f', 'abcd:1234', '../../regla', '1234:5678;id']:
            with self.subTest(argumento=argumento), patch.object(configurador, 'REGLAS_USB', self.reglas), patch.object(configurador.subprocess, 'run') as ejecutar:
                with self.assertRaises(ValueError):
                    configurador.configurar([argumento])
                ejecutar.assert_not_called()
                self.assertEqual(list(self.reglas.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
