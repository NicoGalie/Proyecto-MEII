"""Rutas de recursos y datos para ejecución desde código o como aplicación."""

import os
import sys
from pathlib import Path

ES_WINDOWS = sys.platform == 'win32'
BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def recurso(nombre):
    return BASE / 'recursos' / nombre


def directorio_datos():
    if ES_WINDOWS:
        base_usuario = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        return base_usuario / 'AnalizadorImpedanciasLC' / 'datos'
    return BASE / 'datos'
