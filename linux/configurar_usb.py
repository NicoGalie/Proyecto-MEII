"""Instala reglas persistentes únicamente para instrumentos USBTMC conectados."""

import os
from pathlib import Path
import re
import subprocess
import sys

SYSFS_USB = Path('/sys/bus/usb/devices')
REGLAS_USB = Path('/etc/udev/rules.d')


def validar_instrumentos(argumentos):
    pares = set()
    for argumento in argumentos:
        if not re.fullmatch(r'[0-9a-fA-F]{4}:[0-9a-fA-F]{4}', argumento):
            raise ValueError('Identificador USB inválido. Se requiere VID:PID hexadecimal.')
        pares.add(tuple(argumento.lower().split(':')))
    if not pares:
        raise ValueError('No se seleccionaron instrumentos.')
    conectados = set()
    for dispositivo in SYSFS_USB.iterdir():
        try:
            pareja = ((dispositivo / 'idVendor').read_text().strip().lower(),
                      (dispositivo / 'idProduct').read_text().strip().lower())
            if pareja not in pares:
                continue
            for interfaz in dispositivo.glob(f'{dispositivo.name}:*'):
                if ((interfaz / 'bInterfaceClass').read_text().strip() == 'fe'
                        and (interfaz / 'bInterfaceSubClass').read_text().strip() == '03'):
                    conectados.add(pareja)
                    break
        except OSError:
            continue
    if pares - conectados:
        raise ValueError('Un equipo seleccionado se desconectó o no es un instrumento USBTMC. Actualizá la lista.')
    return sorted(pares)


def configurar(argumentos):
    # Validar todos antes de escribir cualquier regla.
    pares = validar_instrumentos(argumentos)
    for vendor, producto in pares:
        regla = (f'SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", '
                 f'ATTR{{idVendor}}=="{vendor}", ATTR{{idProduct}}=="{producto}", '
                 'MODE="0660", GROUP="plugdev", TAG+="uaccess"\n')
        ruta = REGLAS_USB / f'70-me2-{vendor}-{producto}.rules'
        ruta.write_text(regla)
        ruta.chmod(0o644)
    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
    for vendor, producto in pares:
        subprocess.run([
            'udevadm', 'trigger', '--action=change', '--subsystem-match=usb',
            f'--attr-match=idVendor={vendor}', f'--attr-match=idProduct={producto}',
        ], check=True)
    subprocess.run(['udevadm', 'settle'], check=True)


def main():
    if os.geteuid() != 0:
        print('Se requiere la autorización de administrador de Linux.', file=sys.stderr)
        return 1
    try:
        configurar(sys.argv[1:])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print('Permisos USB configurados.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
