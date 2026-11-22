"""Detección USBTMC por sysfs en Linux y mediante VISA en Windows."""

import os
import subprocess
import webbrowser
from pathlib import Path

from pyvisa import rname

from entorno import ES_WINDOWS
from visa_backend import VISA_WINDOWS_URL, crear_gestor

SYSFS_USB = Path('/sys/bus/usb/devices')
DEV_USB = Path('/dev/bus/usb')
CONFIGURADOR = Path(__file__).resolve().parent.parent / 'linux/configurar_usb.py'
_identificaciones = {}


def _leer(ruta, defecto=''):
    try:
        return ruta.read_text().strip()
    except OSError:
        return defecto


def _enumerar_usb():
    """sysfs expone los descriptores aun sin acceso al puerto USB."""
    equipos = []
    for dispositivo in sorted(SYSFS_USB.iterdir()):
        interfaces = [
            interfaz
            for interfaz in dispositivo.glob(f'{dispositivo.name}:*')
            if _leer(interfaz / 'bInterfaceClass') == 'fe'
            and _leer(interfaz / 'bInterfaceSubClass') == '03'
        ]
        if not interfaces:
            continue
        try:
            vendor = int(_leer(dispositivo / 'idVendor'), 16)
            producto = int(_leer(dispositivo / 'idProduct'), 16)
            bus = int(_leer(dispositivo / 'busnum'))
            numero = int(_leer(dispositivo / 'devnum'))
            interfaz = int(_leer(interfaces[0] / 'bInterfaceNumber'), 16)
        except ValueError:
            # Puede desconectarse mientras recorremos los descriptores.
            continue
        puerto = DEV_USB / f'{bus:03d}' / f'{numero:03d}'
        serie = _leer(dispositivo / 'serial')
        nombre = ' '.join(
            filter(
                None,
                (
                    _leer(dispositivo / 'manufacturer'),
                    _leer(dispositivo / 'product', 'Instrumento USB'),
                ),
            )
        )
        equipos.append(
            {
                'clave': f'{bus}:{numero}:{serie}',
                'vendor': f'{vendor:04x}',
                'producto': f'{producto:04x}',
                'nombre': nombre,
                'serie': serie,
                'puerto': str(puerto),
                'direccion': f'USB0::{vendor}::{producto}::{serie}::{interfaz}::INSTR',
                'estado': 'conectado' if os.access(puerto, os.R_OK | os.W_OK) else 'sin_permisos',
            }
        )
    return equipos


def detectar_instrumentos(actualizar=False):
    """Consulta *IDN? solo en conexiones nuevas con acceso, sin interferir al medir."""
    if ES_WINDOWS:
        return _detectar_windows()
    try:
        equipos = _enumerar_usb()
    except OSError as error:
        return {'exito': False, 'error': f'No se pudo detectar el USB: {error}'}
    presentes = {equipo['clave'] for equipo in equipos}
    for clave in list(_identificaciones):
        if actualizar or clave not in presentes:
            del _identificaciones[clave]
    rm = None
    try:
        for equipo in equipos:
            if equipo['estado'] == 'sin_permisos':
                continue
            if equipo['clave'] not in _identificaciones:
                try:
                    if rm is None:
                        rm = crear_gestor()
                    with rm.open_resource(equipo['direccion']) as inst:
                        inst.timeout = 1500
                        inst.write_termination = '\n'
                        inst.read_termination = '\n'
                        identidad = inst.query('*IDN?').strip()
                    if not identidad:
                        raise ValueError('El instrumento no devolvió su identificación.')
                    partes = identidad.split(',')
                    _identificaciones[equipo['clave']] = ' '.join(p.strip() for p in partes[:2])
                except Exception as error:
                    equipo['estado'] = 'sin_respuesta'
                    equipo['error'] = str(error)
                    continue
            equipo['nombre'] = _identificaciones[equipo['clave']]
    finally:
        if rm is not None:
            rm.close()
    return {'exito': True, 'equipos': equipos}


def _detectar_windows():
    equipos = []
    try:
        with crear_gestor() as gestor:
            for direccion in gestor.list_resources('USB?*::INSTR'):
                datos = rname.parse_resource_name(direccion)
                equipo = dict(
                    clave=direccion,
                    vendor=f'{int(datos.manufacturer_id, 0):04x}',
                    producto=f'{int(datos.model_code, 0):04x}',
                    nombre='Instrumento USB',
                    serie=datos.serial_number,
                    direccion=direccion,
                    estado='conectado',
                )
                try:
                    with gestor.open_resource(direccion) as instrumento:
                        instrumento.timeout = 1500
                        instrumento.write_termination = instrumento.read_termination = '\n'
                        identidad = instrumento.query('*IDN?').strip()
                    partes = [p.strip() for p in identidad.split(',')]
                    if len(partes) < 2 or not partes[0] or not partes[1]:
                        raise ValueError('El instrumento no devolvió una identificación válida.')
                    equipo['nombre'] = ' '.join(partes[:2])
                    if len(partes) > 2 and partes[2]:
                        equipo['serie'] = partes[2]
                except Exception as error:
                    equipo.update(estado='sin_respuesta', error=str(error))
                equipos.append(equipo)
    except Exception as error:
        return dict(exito=False, error=f'No se pudo detectar el USB: {error}')
    return dict(exito=True, equipos=equipos)


def habilitar_permisos(equipos):
    if ES_WINDOWS:
        try:
            abierto = webbrowser.open(VISA_WINDOWS_URL)
        except OSError:
            abierto = False
        if not abierto:
            return dict(exito=False, error=f'Abrí esta página para instalar VISA: {VISA_WINDOWS_URL}')
        return dict(
            exito=True,
            mensaje='Se abrió la descarga de NI-VISA. Instalá el controlador de 64 bits '
            'con soporte USB y después reiniciá el programa.',
        )
    pares = sorted(
        {
            f'{equipo["vendor"]}:{equipo["producto"]}'
            for equipo in equipos
            if equipo['estado'] == 'sin_permisos'
        }
    )
    if not pares:
        return {'exito': True}
    try:
        resultado = subprocess.run(
            ['pkexec', '/usr/bin/python3', str(CONFIGURADOR), *pares],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return {'exito': False, 'error': f'No se pudo abrir la autorización de Linux: {error}'}
    if resultado.returncode != 0:
        error = (
            'La autorización se canceló o no fue concedida.'
            if resultado.returncode in (126, 127)
            else resultado.stderr.strip() or 'No se pudieron configurar los permisos USB.'
        )
        return {'exito': False, 'error': error}
    return {'exito': True}
