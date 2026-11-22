"""Selecciona el transporte VISA adecuado al sistema operativo."""

import pyvisa

from entorno import ES_WINDOWS

VISA_WINDOWS_URL = 'https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html'


def crear_gestor():
    try:
        return pyvisa.ResourceManager('@ivi' if ES_WINDOWS else '@py')
    except (OSError, ValueError, ImportError) as error:
        if ES_WINDOWS:
            raise ValueError(
                'No se pudo abrir VISA. Instalá NI-VISA de 64 bits con soporte USB '
                'y reiniciá el programa.'
            ) from error
        raise
