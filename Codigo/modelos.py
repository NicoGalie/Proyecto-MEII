"""Datos compartidos; los cálculos no dependen de widgets ni de textos de pantalla."""

import math
from dataclasses import dataclass, field

from configuracion import positivo


@dataclass(frozen=True)
class Lectura:
    """Los cuatro números que llegan de los canales del osciloscopio."""

    vo: float
    vz: float
    frecuencia: float
    fase: float

    def __post_init__(self):
        for valor, nombre in (
            (self.vo, 'Vo CH1'),
            (self.vz, 'VZ CH2'),
            (self.frecuencia, 'Frecuencia'),
        ):
            positivo(valor, nombre)
            if valor > 1e10:
                raise ValueError(f'{nombre}: código de error del instrumento.')
        if (
            isinstance(self.fase, bool)
            or not isinstance(self.fase, (int, float))
            or not math.isfinite(self.fase)
            or abs(self.fase) > 360
        ):
            raise ValueError('La fase CH2 respecto de CH1 no es válida.')


@dataclass(frozen=True)
class Ajuste:
    """Ganancia y fase elegidas para esta lectura; opcionalmente, residual."""

    ganancia: float
    fase: float = 0.0
    transferencia: complex | None = None
    residual: complex = 0j
    aplicada: bool = False
    motivo: str = 'Calibración desactivada'


@dataclass(frozen=True)
class Medicion:
    """Resultado de los cálculos, listo para mostrar en pantalla."""

    objetivo: float
    lectura: Lectura
    z: complex
    corriente: float
    tipo: str
    valor: float
    factor: float | None
    ajuste: Ajuste
    intentos: int = 1
    promedio: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Fila:
    """Una fila del barrido: medición válida, error o cancelación."""

    frecuencia: float
    estado: str = 'OK'
    medicion: Medicion | None = None
    error: str = ''
    intentos: int | None = None


@dataclass
class ResultadoBarrido:
    filas: list[Fila] = field(default_factory=list)
    cancelado: bool = False
    error: str = ''


@dataclass
class ResultadoCalibracion:
    puntos: list[dict] = field(default_factory=list)
    perfil: dict | None = None
    cancelado: bool = False
    error: str = ''
