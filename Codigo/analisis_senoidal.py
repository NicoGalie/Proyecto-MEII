"""Amplitud y fase de la fundamental sobre una captura común de dos canales."""

import math
import numpy as np


def _ajustar(t, y, frecuencia):
    angulo = 2 * np.pi * frecuencia * t
    matriz = np.column_stack((np.sin(angulo), np.cos(angulo), np.ones(t.size)))
    coef, _, _, _ = np.linalg.lstsq(matriz, y, rcond=None)
    residuo = y - matriz @ coef
    return coef, float(np.mean(residuo ** 2))


def analizar(t, ch1, ch2, frecuencia_estimada, circuito_abierto=False):
    t, ch1, ch2 = (np.asarray(x, dtype=float) for x in (t, ch1, ch2))
    if (any(x.ndim != 1 or not np.all(np.isfinite(x)) for x in (t, ch1, ch2))
            or t.size < 100 or ch1.size != t.size or ch2.size != t.size):
        raise ValueError('Captura incompleta o no finita en CH1/CH2.')
    pasos = np.diff(t)
    if np.any(pasos <= 0) or not np.allclose(pasos, pasos[0], rtol=1e-5, atol=1e-15):
        raise ValueError('La captura no tiene un intervalo de muestreo uniforme.')
    if not math.isfinite(frecuencia_estimada) or frecuencia_estimada <= 0:
        raise ValueError('No se obtuvo una frecuencia válida de CH2.')
    if frecuencia_estimada * (t[-1] - t[0]) < 2.5:
        raise ValueError('La captura requiere al menos 2,5 ciclos de la señal.')
    if frecuencia_estimada * pasos[0] > .05:
        raise ValueError('La captura requiere al menos 20 muestras por ciclo.')
    # Origen común; evita pérdida de precisión con tiempos absolutos grandes.
    t = t - t[0]
    # Refinamiento por mínimos cuadrados de CH2 dentro del ±5% de la lectura
    # inicial. No depende de que la ventana contenga un número entero de ciclos.
    a, b = frecuencia_estimada * .95, frecuencia_estimada * 1.05
    razon = (math.sqrt(5) - 1) / 2
    c, d = b - razon * (b - a), a + razon * (b - a)
    fc, fd = _ajustar(t, ch2, c)[1], _ajustar(t, ch2, d)[1]
    for _ in range(40):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - razon * (b - a)
            fc = _ajustar(t, ch2, c)[1]
        else:
            a, c, fc = c, d, fd
            d = a + razon * (b - a)
            fd = _ajustar(t, ch2, d)[1]
    frecuencia = (a + b) / 2
    if abs(frecuencia / frecuencia_estimada - 1) >= .049:
        raise ValueError('La frecuencia de la captura no coincide con la lectura de CH2.')
    amplitudes, fases = [], []
    errores = []
    for canal, y in (('CH1', ch1), ('CH2', ch2)):
        coef, error = _ajustar(t, y, frecuencia)
        rms = math.hypot(coef[0], coef[1]) / math.sqrt(2)
        if not math.isfinite(rms) or rms <= 1e-12:
            raise ValueError(f'{canal}: no hay una señal senoidal medible.')
        residuo_relativo = math.sqrt(error) / rms
        if residuo_relativo > .05 and not (circuito_abierto and canal == 'CH1'):
            raise ValueError(f'{canal}: residuo {residuo_relativo:.1%}, señal distorsionada o demasiado ruido; revisá amplitud y escalas.')
        amplitudes.append(rms)
        errores.append(math.sqrt(error))
        fases.append(math.degrees(math.atan2(coef[1], coef[0])))
    # En abierto no se exige un porcentaje respecto de una corriente casi
    # nula: acotá el ruido absoluto referido a V_OUT. El backend exige además
    # coherencia del fasor entre tres capturas (1%).
    if circuito_abierto and errores[0] > .001 * amplitudes[1]:
        raise ValueError('Circuito abierto: ruido residual mayor al 0,1% de V_OUT.')
    fase = (fases[1] - fases[0] + 180) % 360 - 180
    return amplitudes[0], amplitudes[1], frecuencia, fase
