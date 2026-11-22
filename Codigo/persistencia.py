"""Lectura JSON y escritura atómica, sin modificar archivos ante un fallo."""

import json
import os
import tempfile
from pathlib import Path


def cargar_json(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None


def guardar_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=ruta.parent, delete=False
        ) as archivo:
            temporal = Path(archivo.name)
            json.dump(datos, archivo, ensure_ascii=False, allow_nan=False, indent=2)
            archivo.write('\n')
        os.replace(temporal, ruta)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
