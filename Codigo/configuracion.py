"""Parámetros físicos del único circuito admitido: INA128P sobre Rs."""

import math
from dataclasses import dataclass

from entorno import directorio_datos
from persistencia import cargar_json, guardar_json

DATOS = directorio_datos()
RUTA_CONFIGURACION = DATOS / 'circuito-ina128p.json'


def positivo(valor, nombre):
    if (
        isinstance(valor, bool)
        or not isinstance(valor, (int, float))
        or not math.isfinite(valor)
        or valor <= 0
    ):
        raise ValueError(f'{nombre} debe ser un número positivo y finito.')
    return valor


def normalizar_fase(grados):
    return (grados + 180) % 360 - 180


def leer_rg(texto):
    if str(texto).strip().lower() == 'abierto':
        return None
    try:
        return positivo(float(str(texto).replace(',', '.')), 'RG')
    except ValueError:
        raise ValueError('Ingresá RG en Ω o «abierto» para ganancia 1.') from None


@dataclass(frozen=True)
class Configuracion:
    """Los dos valores físicos ingresados: Rs y la resistencia de ganancia RG."""

    rs: float = 10.0
    rg_ohm: float | None = 12500.0

    def __post_init__(self):
        positivo(self.rs, 'Rs')
        if self.rg_ohm is not None:
            positivo(self.rg_ohm, 'RG')
        if not 1 <= self.ganancia <= 10000:
            raise ValueError('La ganancia debe estar entre 1 y 10000.')

    @property
    def ganancia(self):
        if self.rg_ohm is None:
            return 1.0
        return 1 + 50000 / self.rg_ohm

    def circuito(self):
        return dict(
            id='ina128p', rg_ohm=self.rg_ohm, ganancia_nominal=self.ganancia, fase_nominal=0.0
        )


def cargar_configuracion():
    datos = cargar_json(RUTA_CONFIGURACION)
    if datos is None:
        return Configuracion()
    if not isinstance(datos, dict) or datos.get('id') != 'ina128p':
        raise ValueError('La configuración guardada no corresponde al circuito.')
    return Configuracion(datos.get('r_sensora', 10.0), datos['rg_ohm'])


def guardar_configuracion(configuracion):
    guardar_json(RUTA_CONFIGURACION, dict(configuracion.circuito(), r_sensora=configuracion.rs))
