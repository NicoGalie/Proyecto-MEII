"""Transferencia y residual de la fundamental: circuito abierto y resistencia."""

from bisect import bisect_left
import json
import math
import cmath
import os
from pathlib import Path
import tempfile

RUTA_CALIBRACION = Path(__file__).resolve().parent.parent / 'datos/calibracion.json'


def normalizar_fase(grados):
    return (grados + 180.0) % 360.0 - 180.0


def positivo(valor, nombre):
    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not math.isfinite(valor) or valor <= 0:
        raise ValueError(f'{nombre} debe ser un número positivo y finito.')
    return valor


def fasor(v_i, v_r, fase):
    """I_OUT/V_OUT; la fase cruda es CH2 menos CH1."""
    return v_i / v_r * cmath.exp(-1j * math.radians(fase))


def complejo(punto, prefijo):
    if not isinstance(punto, dict):
        raise ValueError('Punto complejo de calibración inválido.')
    valores = [punto.get(prefijo + sufijo) for sufijo in ('_real', '_imag')]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in valores):
        raise ValueError('Coeficiente complejo de calibración inválido.')
    return complex(*valores)


def validar_abierto(abierto):
    if not isinstance(abierto, dict):
        raise ValueError('Lectura de circuito abierto inválida.')
    positivo(abierto.get('r_sensora'), 'R1 de circuito abierto')
    puntos = abierto.get('puntos')
    if not isinstance(puntos, list) or len(puntos) < 2:
        raise ValueError('Se requieren al menos dos puntos de circuito abierto.')
    anterior = 0
    for punto in puntos:
        if not isinstance(punto, dict):
            raise ValueError('Punto de circuito abierto inválido.')
        f = positivo(punto.get('frecuencia'), 'Frecuencia de circuito abierto')
        objetivo = positivo(punto.get('frecuencia_objetivo'), 'Frecuencia programada de circuito abierto')
        if f <= anterior or abs(f / objetivo - 1) > .05:
            raise ValueError('Frecuencias de circuito abierto inválidas.')
        anterior = f
        h = complejo(punto, 'residual')
        lecturas = punto.get('lecturas')
        if not isinstance(lecturas, list) or len(lecturas) != 3:
            raise ValueError('Cada punto abierto requiere tres capturas.')
        fasores = []
        for lectura in lecturas:
            if not isinstance(lectura, dict):
                raise ValueError('Captura de circuito abierto inválida.')
            vi = positivo(lectura.get('v_i_out'), 'I_OUT en abierto')
            vr = positivo(lectura.get('v_rms'), 'V_OUT en abierto')
            fl = positivo(lectura.get('frecuencia'), 'Frecuencia capturada en abierto')
            fase = lectura.get('fase_cruda')
            if not isinstance(fase, (int, float)) or not math.isfinite(fase) or abs(fase) > 360 or abs(fl / objetivo - 1) > .05:
                raise ValueError('Captura de circuito abierto inválida.')
            fasores.append(fasor(vi, vr, fase))
        if (abs(h) <= 1e-12 or abs(h - sum(fasores) / 3) > 1e-12
                or max(abs(x - h) for x in fasores) > .01 * abs(h)):
            raise ValueError('Residual de circuito abierto inconsistente o inestable.')
    return abierto


def validar_fase_referencia(punto, anterior=None):
    correccion = normalizar_fase(punto['fase_cruda'] - 180)
    if abs(correccion) >= 90:
        raise ValueError('La fase de la resistencia conocida no es coherente con el amplificador inversor. Revisá la captura y repetí la calibración.')
    if anterior is not None and abs(normalizar_fase(punto['fase_cruda'] - anterior['fase_cruda'])) > 45:
        raise ValueError('Salto de fase mayor a 45° entre puntos de calibración. Repetí la lectura o aumentá la cantidad de puntos.')


def validar_perfil(perfil):
    if not isinstance(perfil, dict) or perfil.get('version') not in (1, 2):
        raise ValueError('Formato de calibración no reconocido.')
    positivo(perfil.get('r_sensora'), 'La resistencia sensora de calibración')
    positivo(perfil.get('r_referencia'), 'La resistencia conocida')
    if 'osciloscopio' in perfil:
        identidad = perfil['osciloscopio']
        if not isinstance(identidad, dict) or any(
                not isinstance(identidad.get(k), str) or not identidad[k].strip()
                for k in ('fabricante', 'modelo', 'serie')):
            raise ValueError('Identificación del osciloscopio de calibración inválida.')
        if ('TEKTRONIX' in identidad['fabricante'].upper()
                and perfil.get('metodo_medicion') != 'senoidal_v1'):
            raise ValueError('La calibración Tektronix anterior debe repetirse con la captura senoidal nueva.')
    puntos = perfil.get('puntos')
    if not isinstance(puntos, list) or len(puntos) < 2:
        raise ValueError('La calibración requiere al menos dos frecuencias válidas.')
    if any(not isinstance(p, dict) for p in puntos):
        raise ValueError('Punto de calibración inválido.')
    if perfil['version'] == 2:
        abierto = validar_abierto(perfil.get('abierto'))
        if (abierto['r_sensora'] != perfil['r_sensora']
                or abierto.get('osciloscopio') != perfil.get('osciloscopio')
                or abierto.get('metodo_medicion') != perfil.get('metodo_medicion')
                or [p['frecuencia_objetivo'] for p in abierto['puntos']] != [p.get('frecuencia_objetivo') for p in puntos]):
            raise ValueError('El circuito abierto no corresponde a esta calibración.')
        for p, pa in zip(puntos, abierto['puntos']):
            if complejo(p, 'residual') != complejo(pa, 'residual'):
                raise ValueError('El residual no coincide con el circuito abierto medido.')
    anterior = 0
    punto_anterior = None
    for punto in puntos:
        if not isinstance(punto, dict):
            raise ValueError('Punto de calibración inválido.')
        f = positivo(punto.get('frecuencia'), 'La frecuencia de calibración')
        positivo(punto.get('frecuencia_objetivo'), 'La frecuencia programada')
        positivo(punto.get('v_i_out'), 'La tensión I_OUT de calibración')
        positivo(punto.get('v_rms'), 'La tensión V_OUT de calibración')
        positivo(punto.get('ganancia'), 'La ganancia de calibración')
        fase = punto.get('fase_cruda')
        if not isinstance(fase, (int, float)) or not math.isfinite(fase) or abs(fase) > 360:
            raise ValueError('Fase de calibración inválida.')
        correccion = punto.get('correccion_fase')
        esperada = normalizar_fase(fase - 180)
        if perfil['version'] == 2:
            h, a = complejo(punto, 'residual'), complejo(punto, 'transferencia')
            calculada = (fasor(punto['v_i_out'], punto['v_rms'], fase) - h) * perfil['r_referencia']
            if abs(a) <= 1e-12 or abs(a - calculada) > 1e-9 * max(1, abs(a)):
                raise ValueError('La transferencia no coincide con las lecturas de referencia.')
            if abs(a / perfil['r_referencia']) <= .1 * abs(h):
                raise ValueError('La corriente de referencia está demasiado próxima al residual.')
            if not math.isclose(punto['ganancia'], abs(a) / perfil['r_sensora'], rel_tol=1e-9):
                raise ValueError('La ganancia no coincide con la transferencia calibrada.')
            esperada = normalizar_fase(-math.degrees(cmath.phase(a)) - 180)
        if (not isinstance(correccion, (int, float)) or not math.isfinite(correccion)
                or not math.isclose(correccion, esperada, abs_tol=1e-9)):
            raise ValueError('Corrección de fase de calibración inválida.')
        if f <= anterior:
            raise ValueError('Las frecuencias de calibración deben ser distintas y crecientes.')
        anterior = f
        validar_fase_referencia(punto, punto_anterior)
        if abs(correccion) >= 90:
            raise ValueError('La transferencia calibrada no corresponde a un amplificador inversor.')
        punto_anterior = punto
    return perfil


def _intervalo(perfil, frecuencia, r_sensora):
    validar_perfil(perfil)
    positivo(frecuencia, 'La frecuencia')
    if not math.isclose(r_sensora, perfil['r_sensora'], rel_tol=1e-9):
        raise ValueError(f"Esta calibración corresponde a R1 = {perfil['r_sensora']:g} Ω. Seleccioná esa resistencia o desactivá la calibración.")
    puntos = perfil['puntos']
    frecuencias = [p['frecuencia'] for p in puntos]
    if not frecuencias[0] <= frecuencia <= frecuencias[-1]:
        extremo = frecuencias[0] if frecuencia < frecuencias[0] else frecuencias[-1]
        # El ajuste senoidal mide pequeñas variaciones del reloj entre capturas.
        # Cerca del extremo usa su corrección, sin extrapolar una recta.
        if perfil.get('metodo_medicion') == 'senoidal_v1' and abs(frecuencia / extremo - 1) <= .001:
            frecuencia = extremo
        else:
            raise ValueError(f'Frecuencia fuera de la calibración ({frecuencias[0]:g}–{frecuencias[-1]:g} Hz). Calibrá ese rango o desactivá la corrección.')
    i = bisect_left(frecuencias, frecuencia)
    if frecuencias[i] == frecuencia:
        p = puntos[i]
        return p, p, 0.0
    a, b = puntos[i - 1], puntos[i]
    peso = (frecuencia - a['frecuencia']) / (b['frecuencia'] - a['frecuencia'])
    return a, b, peso


def correcciones(perfil, frecuencia, r_sensora):
    a, b, peso = _intervalo(perfil, frecuencia, r_sensora)
    ganancia = a['ganancia'] + peso * (b['ganancia'] - a['ganancia'])
    fase_a = a['correccion_fase']
    fase_b = fase_a + normalizar_fase(b['correccion_fase'] - fase_a)
    return ganancia, normalizar_fase(fase_a + peso * (fase_b - fase_a))


def coeficientes(perfil, frecuencia, r_sensora):
    if perfil.get('version') != 2:
        raise ValueError('Se requiere calibración de circuito abierto y resistencia.')
    a, b, peso = _intervalo(perfil, frecuencia, r_sensora)
    return tuple(complejo(a, campo) + peso * (complejo(b, campo) - complejo(a, campo))
                 for campo in ('transferencia', 'residual'))


def guardar(perfil, ruta=None):
    validar_perfil(perfil)
    ruta = Path(ruta) if ruta is not None else RUTA_CALIBRACION
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=ruta.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            json.dump(perfil, archivo, ensure_ascii=False, allow_nan=False, indent=2)
            archivo.write('\n')
        os.replace(temporal, ruta)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def cargar(ruta=None):
    ruta = Path(ruta) if ruta is not None else RUTA_CALIBRACION
    try:
        with ruta.open(encoding='utf-8') as archivo:
            perfil = json.load(archivo)
    except FileNotFoundError:
        return None
    return validar_perfil(perfil)
