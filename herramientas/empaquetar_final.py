"""Construye la descarga final con una lista explícita de contenidos."""

import hashlib
import zipfile
from pathlib import Path

CONTENIDOS = (
    'Codigo',
    'recursos',
    'tests',
    'ejemplos',
    'linux',
    'docs',
    'herramientas',
    'README.md',
    'VERSION_FINAL.txt',
    'requirements.txt',
    'iniciar.sh',
    'pyproject.toml',
    '.gitignore',
    '.gitattributes',
)


def main():
    proyecto = Path(__file__).resolve().parents[1]
    destino = proyecto / 'descargas'
    destino.mkdir(exist_ok=True)
    archivo_zip = destino / 'Analizador_Impedancias_LC_Complejas_FINAL.zip'
    with zipfile.ZipFile(archivo_zip, 'w', zipfile.ZIP_DEFLATED) as archivo:
        for nombre in CONTENIDOS:
            fuente = proyecto / nombre
            candidatos = sorted(fuente.rglob('*')) if fuente.is_dir() else [fuente]
            for ruta in candidatos:
                relativa = ruta.relative_to(proyecto)
                if not ruta.is_file() or '__pycache__' in relativa.parts or ruta.suffix == '.pyc':
                    continue
                nombre_zip = str(Path('Analizador_LC_Complejas_FINAL') / relativa)
                archivo.write(ruta, nombre_zip)
    with zipfile.ZipFile(archivo_zip) as archivo:
        fallo = archivo.testzip()
        if fallo is not None:
            raise ValueError(f'Archivo corrupto dentro del ZIP: {fallo}')
    resumen = hashlib.sha256(archivo_zip.read_bytes()).hexdigest()
    (destino / 'SHA256SUMS').write_text(f'{resumen}  {archivo_zip.name}\n', encoding='utf-8')
    print(f'Paquete final: {archivo_zip}')
    print(f'SHA-256: {resumen}')


if __name__ == '__main__':
    main()
