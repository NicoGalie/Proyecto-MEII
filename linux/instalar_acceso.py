"""Genera un acceso de escritorio con las rutas de esta instalación."""

import argparse
import shutil
import subprocess
from pathlib import Path


def carpeta_escritorio():
    if shutil.which('xdg-user-dir'):
        resultado = subprocess.run(
            ['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True
        )
        if resultado.stdout.strip():
            return Path(resultado.stdout.strip())
    for nombre in ('Escritorio', 'Desktop'):
        ruta = Path.home() / nombre
        if ruta.is_dir():
            return ruta
    return Path.home() / 'Desktop'


def valor_escritorio(ruta):
    # Escape de valores string del formato Desktop Entry.
    return str(ruta).replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def instalar(destino):
    proyecto = Path(__file__).resolve().parents[1]
    lanzador = proyecto / 'iniciar.sh'
    lanzador.chmod(lanzador.stat().st_mode | 0o111)
    ejecutable = str(proyecto / 'iniciar.sh')
    # Exec tiene una segunda capa de interpretación y expande códigos con %.
    for caracter in ('\\', '"', '`', '$'):
        ejecutable = ejecutable.replace(caracter, '\\' + caracter)
    ejecutable = ejecutable.replace('%', '%%')
    texto = (proyecto / 'linux/analizador-lc.desktop.in').read_text(encoding='utf-8')
    texto = texto.replace('@EJECUTABLE@', valor_escritorio(ejecutable))
    texto = texto.replace('@PROYECTO@', valor_escritorio(proyecto))
    texto = texto.replace('@ICONO@', valor_escritorio(proyecto / 'recursos/utn-fondo-blanco.png'))
    destino = destino.expanduser().resolve()
    destino.mkdir(parents=True, exist_ok=True)
    acceso = destino / 'Analizador de Impedancias LC Complejas.desktop'
    acceso.write_text(texto, encoding='utf-8')
    acceso.chmod(0o755)
    if shutil.which('gio'):
        subprocess.run(
            ['gio', 'set', str(acceso), 'metadata::trusted', 'true'],
            capture_output=True,
            check=False,
        )
    print(f'Acceso creado: {acceso}')
    return acceso


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, help='Carpeta donde crear el acceso directo')
    argumentos = parser.parse_args()
    instalar(argumentos.destino if argumentos.destino is not None else carpeta_escritorio())


if __name__ == '__main__':
    main()
