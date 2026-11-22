"""Construye el paquete de Windows a partir de la aplicación del repositorio."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != 'win32':
        raise SystemExit('El ejecutable de Windows debe compilarse en Windows.')
    proyecto = Path(__file__).resolve().parents[1]
    nombre = 'AnalizadorImpedanciasLC'
    argumentos = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--windowed', '--noupx', '--name', nombre,
        '--paths', str(proyecto / 'Codigo'),
        '--icon', str(proyecto / 'recursos/utn-fondo-blanco.ico'),
        '--add-data', f'{proyecto / "recursos"}:recursos',
        '--collect-submodules', 'pyvisa',
        '--collect-submodules', 'pyvisa_py',
        '--collect-submodules', 'usb',
        '--copy-metadata', 'PyVISA',
        '--copy-metadata', 'PyVISA-py',
        '--distpath', str(proyecto / 'dist'),
        '--workpath', str(proyecto / 'build'),
        '--specpath', str(proyecto / 'build'),
        str(proyecto / 'Codigo/Interfaz.py'),
    ]
    subprocess.run(argumentos, cwd=proyecto, check=True)
    destino = proyecto / 'dist' / nombre
    shutil.copy2(proyecto / 'windows/Crear_acceso_directo.cmd', destino)
    (destino / 'LEEME.txt').write_text(
        'Analizador de Impedancias LC Complejas\n\n'
        'Descomprimir la carpeta completa y abrir AnalizadorImpedanciasLC.exe.\n'
        'Mantener la carpeta _internal junto al ejecutable.\n'
        'No se necesita instalar Python.\n\n'
        'Para conectar instrumentos USB se necesita NI-VISA de 64 bits con soporte USBTMC:\n'
        'https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html\n'
        'Despues de instalar el controlador, abrir el programa y pulsar Actualizar equipos.\n\n'
        'Crear_acceso_directo.cmd agrega el acceso con icono al escritorio.\n'
        'Si se mueve la carpeta del programa, volver a crear ese acceso.\n'
        'La configuracion y la calibracion se guardan en:\n'
        '%LOCALAPPDATA%\\AnalizadorImpedanciasLC\\datos\n',
        encoding='utf-8',
    )
    salida = proyecto / 'dist/Analizador_Impedancias_LC_Complejas_Windows_x64'
    archivo = Path(shutil.make_archive(str(salida), 'zip', destino.parent, destino.name))
    resumen = hashlib.sha256(archivo.read_bytes()).hexdigest()
    archivo.with_suffix('.zip.sha256').write_text(f'{resumen}  {archivo.name}\n', encoding='utf-8')
    print(f'Paquete Windows: {archivo}')


if __name__ == '__main__':
    main()
