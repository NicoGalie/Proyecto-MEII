"""Detección USB sin privilegios y autorización mediante la ventana de Linux."""

import os
from pathlib import Path
import subprocess

import pyvisa

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
            interfaz for interfaz in dispositivo.glob(f'{dispositivo.name}:*')
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
        nombre = ' '.join(filter(None, (
            _leer(dispositivo / 'manufacturer'),
            _leer(dispositivo / 'product', 'Instrumento USB'),
        )))
        equipos.append({
            'clave': f'{bus}:{numero}:{serie}',
            'vendor': f'{vendor:04x}', 'producto': f'{producto:04x}',
            'nombre': nombre, 'serie': serie, 'puerto': str(puerto),
            'direccion': f'USB0::{vendor}::{producto}::{serie}::{interfaz}::INSTR',
            'estado': 'conectado' if os.access(puerto, os.R_OK | os.W_OK) else 'sin_permisos',
        })
    return equipos


def detectar_instrumentos(actualizar=False):
    """Consulta *IDN? solo en conexiones nuevas con acceso, sin interferir al medir."""
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
                        rm = pyvisa.ResourceManager('@py')
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


def habilitar_permisos(equipos):
    pares = sorted({
        f"{equipo['vendor']}:{equipo['producto']}"
        for equipo in equipos if equipo['estado'] == 'sin_permisos'
    })
    if not pares:
        return {'exito': True}
    try:
        resultado = subprocess.run(
            ['pkexec', '/usr/bin/python3', str(CONFIGURADOR), *pares],
            capture_output=True, text=True,
        )
    except OSError as error:
        return {'exito': False, 'error': f'No se pudo abrir la autorización de Linux: {error}'}
    if resultado.returncode != 0:
        error = ('La autorización se canceló o no fue concedida.'
                 if resultado.returncode in (126, 127)
                 else resultado.stderr.strip() or 'No se pudieron configurar los permisos USB.')
        return {'exito': False, 'error': error}
    return {'exito': True}
