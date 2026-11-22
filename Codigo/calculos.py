"""Cálculos del INA128P, escritos en el orden físico de la medición.

CH1 mide Vo = G · I · Rs. CH2 mide la tensión VZ sobre el componente.
La fase medida es la de CH2 respecto de CH1: no hay inversión de 180°.
"""

import cmath
import math

from configuracion import normalizar_fase, positivo
from modelos import Ajuste, Medicion


def fasor(lectura):
    """Representa Vo/VZ con amplitud y fase en un único número complejo."""
    relacion_tensiones = lectura.vo / lectura.vz
    fase_en_radianes = math.radians(lectura.fase)
    return relacion_tensiones * cmath.exp(-1j * fase_en_radianes)


def calcular(lectura, configuracion, ajuste=None, objetivo=None, intentos=1, promedio=None):
    """Convierte las tensiones y la fase en los parámetros del componente."""
    # 1. Elegir la ganancia: nominal si no se recibió una corrección.
    if ajuste is None:
        ajuste = Ajuste(ganancia=configuracion.ganancia)
    positivo(ajuste.ganancia, 'Ganancia')

    # 2. Calcular la impedancia. El caso habitual sigue I = Vo/(G·Rs).
    if ajuste.transferencia is None:
        corriente = lectura.vo / (ajuste.ganancia * configuracion.rs)
        positivo(corriente, 'Corriente')
        modulo_impedancia = lectura.vz / corriente
        fase_corregida = normalizar_fase(lectura.fase - ajuste.fase)
        fase_en_radianes = math.radians(fase_corregida)

        resistencia_serie = modulo_impedancia * math.cos(fase_en_radianes)
        reactancia = modulo_impedancia * math.sin(fase_en_radianes)
        impedancia = complex(resistencia_serie, reactancia)
    else:
        # Solo la calibración con abierto necesita restar el residual complejo.
        relacion_corregida = fasor(lectura) - ajuste.residual
        limite_residual = max(1e-12, abs(ajuste.residual) * 0.01)
        if abs(relacion_corregida) <= limite_residual:
            raise ValueError('La corriente no se distingue del residual de circuito abierto.')
        impedancia = ajuste.transferencia / relacion_corregida

    # 3. Comprobar que el resultado es físicamente utilizable.
    if not math.isfinite(impedancia.real) or not math.isfinite(impedancia.imag):
        raise ValueError('La impedancia calculada no es finita.')
    positivo(abs(impedancia), 'Impedancia')

    resistencia_serie = impedancia.real
    reactancia = impedancia.imag
    if resistencia_serie < 0:
        raise ValueError(
            f'ESR negativa ({resistencia_serie:.6g} Ω). Revisá señal, conexiones o calibración.'
        )

    # 4. Identificar el componente por el signo de su reactancia.
    omega = 2 * math.pi * lectura.frecuencia
    if reactancia < 0:
        tipo = 'CAPACITOR'
        valor = 1 / (omega * abs(reactancia))
        factor = resistencia_serie / abs(reactancia)  # Factor D.
    elif reactancia > 0:
        tipo = 'INDUCTOR'
        valor = reactancia / omega
        factor = reactancia / resistencia_serie if resistencia_serie > 0 else None  # Q.
    else:
        tipo = 'RESISTENCIA'
        valor = resistencia_serie
        factor = None

    if not math.isfinite(valor) or (factor is not None and not math.isfinite(factor)):
        raise ValueError('Los parámetros del componente no son finitos.')

    # 5. Devolver datos numéricos. La interfaz se ocupa de las unidades y textos.
    return Medicion(
        objetivo=objetivo if objetivo is not None else lectura.frecuencia,
        lectura=lectura,
        z=impedancia,
        corriente=lectura.vz / abs(impedancia),
        tipo=tipo,
        valor=valor,
        factor=factor,
        ajuste=ajuste,
        intentos=intentos,
        promedio=promedio or {},
    )
