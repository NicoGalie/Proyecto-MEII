"""Calibración INA128P, compatible con los perfiles medidos de versiones 1 y 2."""

import cmath
import math
from bisect import bisect_left

from calculos import fasor
from configuracion import DATOS, Configuracion, normalizar_fase, positivo
from modelos import Ajuste, Lectura
from persistencia import cargar_json, guardar_json

RUTA_CALIBRACION = DATOS / 'calibracion-ina128p.json'


def complejo(punto, nombre):
    valores = [punto.get(nombre + sufijo) for sufijo in ('_real', '_imag')]
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in valores
    ):
        raise ValueError('Coeficiente complejo de calibración inválido.')
    return complex(*valores)


def configuracion_perfil(perfil):
    circuito = perfil.get('circuito')
    if not isinstance(circuito, dict) or circuito.get('id') != 'ina128p':
        raise ValueError('La calibración no corresponde al circuito.')
    config = Configuracion(perfil['r_sensora'], circuito['rg_ohm'])
    if circuito != config.circuito():
        raise ValueError('La ganancia o polaridad del perfil es inválida.')
    return config


def lectura_punto(punto):
    return Lectura(punto['v_i_out'], punto['v_rms'], punto['frecuencia'], punto['fase_cruda'])


def validar_fase(punto, anterior=None):
    correccion = normalizar_fase(punto['fase_cruda'])
    if abs(correccion) >= 90 or abs(punto['correccion_fase']) >= 90:
        raise ValueError(
            'La resistencia de referencia no coincide con la polaridad no inversora del circuito.'
        )
    if anterior and abs(normalizar_fase(punto['fase_cruda'] - anterior['fase_cruda'])) > 45:
        raise ValueError('Salto de fase mayor a 45° entre frecuencias de calibración.')


def validar_abierto(abierto):
    configuracion_perfil(abierto)
    puntos = abierto.get('puntos')
    if not isinstance(puntos, list) or len(puntos) < 2:
        raise ValueError('El circuito abierto requiere al menos dos frecuencias.')
    anterior = 0
    for punto in puntos:
        f = positivo(punto['frecuencia'], 'Frecuencia de circuito abierto')
        objetivo = positivo(punto['frecuencia_objetivo'], 'Frecuencia programada')
        capturas = punto['lecturas']
        if f <= anterior or abs(f / objetivo - 1) > 0.05 or len(capturas) != 3:
            raise ValueError('Frecuencias o capturas de circuito abierto inválidas.')
        h = complejo(punto, 'residual')
        valores = [fasor(lectura_punto(x)) for x in capturas]
        if (
            abs(h) <= 1e-12
            or abs(h - sum(valores) / 3) > 1e-12
            or max(abs(x - h) for x in valores) > 0.01 * abs(h)
            or any(abs(x['frecuencia'] / objetivo - 1) > 0.05 for x in capturas)
        ):
            raise ValueError('El residual de circuito abierto no es estable entre tres capturas.')
        anterior = f
    return abierto


def validar(perfil):
    if not isinstance(perfil, dict) or perfil.get('version') not in (1, 2):
        raise ValueError('Formato de calibración no reconocido.')
    config = configuracion_perfil(perfil)
    referencia = positivo(perfil['r_referencia'], 'Resistencia conocida')
    puntos = perfil.get('puntos')
    if not isinstance(puntos, list) or len(puntos) < 2:
        raise ValueError('Se requieren al menos dos frecuencias calibradas.')
    if 'osciloscopio' in perfil:
        identidad = perfil['osciloscopio']
        if not isinstance(identidad, dict) or any(
            not isinstance(identidad.get(k), str) or not identidad[k].strip()
            for k in ('fabricante', 'modelo', 'serie')
        ):
            raise ValueError('Identificación de osciloscopio inválida.')
        if (
            'TEKTRONIX' in identidad['fabricante'].upper()
            and perfil.get('metodo_medicion') != 'senoidal_v1'
        ):
            raise ValueError('Repetí la calibración con la captura senoidal.')
    abierto = None
    if perfil['version'] == 2:
        abierto = validar_abierto(perfil['abierto'])
        if (
            configuracion_perfil(abierto) != config
            or abierto.get('osciloscopio') != perfil.get('osciloscopio')
            or abierto.get('metodo_medicion') != perfil.get('metodo_medicion')
            or [p['frecuencia_objetivo'] for p in abierto['puntos']]
            != [p['frecuencia_objetivo'] for p in puntos]
        ):
            raise ValueError('El circuito abierto pertenece a otra configuración o barrido.')
    anterior = None
    for i, punto in enumerate(puntos):
        lectura = lectura_punto(punto)
        objetivo = positivo(punto['frecuencia_objetivo'], 'Frecuencia programada')
        positivo(punto['ganancia'], 'Ganancia calibrada')
        if abs(lectura.frecuencia / objetivo - 1) > 0.05 or (
            anterior and lectura.frecuencia <= anterior['frecuencia']
        ):
            raise ValueError('Las frecuencias calibradas deben ser válidas y crecientes.')
        esperada = normalizar_fase(lectura.fase)
        if abierto is None and not math.isclose(
            punto['ganancia'], lectura.vo * referencia / (lectura.vz * config.rs), rel_tol=1e-9
        ):
            raise ValueError('La ganancia no coincide con las lecturas de la resistencia conocida.')
        if abierto is not None:
            a, h = complejo(punto, 'transferencia'), complejo(punto, 'residual')
            calculada = (fasor(lectura) - h) * referencia
            if (
                h != complejo(abierto['puntos'][i], 'residual')
                or abs(a) <= 1e-12
                or abs(a - calculada) > 1e-9 * max(1, abs(a))
                or abs(a / referencia) <= 0.1 * abs(h)
                or not math.isclose(punto['ganancia'], abs(a) / config.rs, rel_tol=1e-9)
            ):
                raise ValueError('Transferencia o residual de calibración inconsistente.')
            esperada = normalizar_fase(-math.degrees(cmath.phase(a)))
        if not isinstance(punto['correccion_fase'], (int, float)) or not math.isclose(
            punto['correccion_fase'], esperada, abs_tol=1e-9
        ):
            raise ValueError('Corrección de fase inconsistente.')
        validar_fase(punto, anterior)
        anterior = punto
    return perfil


def seleccionar(perfil, config, frecuencia, identidad, metodo, usar=True, objetivo=None):
    """Una condición no cubierta usa TODO el modelo nominal, incluido residual cero."""

    def nominal(motivo):
        return Ajuste(config.ganancia, motivo=motivo)

    if not usar:
        return nominal('Calibración desactivada')
    if perfil is None:
        return nominal('Sin calibración guardada')
    validar(perfil)
    guardada = configuracion_perfil(perfil)
    if not math.isclose(config.rs, guardada.rs, rel_tol=1e-9):
        return nominal('Rs sin calibrar: se usan parámetros nominales')
    if config.rg_ohm != guardada.rg_ohm:
        return nominal('RG distinta: se usan parámetros nominales')
    if perfil.get('osciloscopio') != identidad or perfil.get('metodo_medicion') != metodo:
        return nominal('Equipo o método distinto: se usan parámetros nominales')
    puntos = perfil['puntos']
    if (
        objetivo is not None
        and not puntos[0]['frecuencia_objetivo'] <= objetivo <= puntos[-1]['frecuencia_objetivo']
    ):
        return nominal('Frecuencia fuera de calibración: se usan parámetros nominales')
    frecuencias = [p['frecuencia'] for p in puntos]
    f = frecuencia
    if f < frecuencias[0] or f > frecuencias[-1]:
        extremo = frecuencias[0] if f < frecuencias[0] else frecuencias[-1]
        if abs(f / extremo - 1) <= 0.001:
            f = extremo  # Tolerancia del reloj; sin extrapolación.
        else:
            return nominal('Frecuencia fuera de calibración: se usan parámetros nominales')
    # Buscar los dos puntos que rodean la frecuencia de esta medición.
    indice = bisect_left(frecuencias, f)
    if frecuencias[indice] == f or abs(f / frecuencias[indice] - 1) <= 1e-9:
        punto_inicial = puntos[indice]
        punto_final = puntos[indice]
        peso = 0
    else:
        punto_inicial = puntos[indice - 1]
        punto_final = puntos[indice]
        distancia_total = punto_final['frecuencia'] - punto_inicial['frecuencia']
        peso = (f - punto_inicial['frecuencia']) / distancia_total

    # Peso 0 usa el primer punto; peso 1 usa el segundo; 0,5 toma el medio.
    ganancia = interpolar(punto_inicial['ganancia'], punto_final['ganancia'], peso)
    fase_inicial = punto_inicial['correccion_fase']
    diferencia_fase = normalizar_fase(punto_final['correccion_fase'] - fase_inicial)
    fase = normalizar_fase(fase_inicial + peso * diferencia_fase)
    transferencia, residual = None, 0j
    if perfil['version'] == 2:
        transferencia = interpolar(
            complejo(punto_inicial, 'transferencia'), complejo(punto_final, 'transferencia'), peso
        )
        residual = interpolar(
            complejo(punto_inicial, 'residual'), complejo(punto_final, 'residual'), peso
        )
        ganancia = abs(transferencia) / config.rs
    return Ajuste(ganancia, fase, transferencia, residual, True, 'Calibración aplicada')


def interpolar(valor_inicial, valor_final, peso):
    """Recorrer una fracción del camino entre dos valores conocidos."""
    return valor_inicial + peso * (valor_final - valor_inicial)


def crear_punto(lectura, objetivo, config, referencia, anterior=None, abierto=None):
    """Usar la resistencia conocida para averiguar la ganancia y el desfase."""
    positivo(referencia, 'Resistencia conocida')
    corriente_referencia = lectura.vz / referencia
    tension_sobre_rs = corriente_referencia * config.rs
    ganancia_medida = lectura.vo / tension_sobre_rs
    punto = dict(
        frecuencia_objetivo=objetivo,
        frecuencia=lectura.frecuencia,
        v_i_out=lectura.vo,
        v_rms=lectura.vz,
        fase_cruda=lectura.fase,
        ganancia=ganancia_medida,
        correccion_fase=normalizar_fase(lectura.fase),
    )
    if abierto is not None:
        h = complejo(abierto, 'residual')
        a = (fasor(lectura) - h) * referencia
        if abs(a / referencia) <= 0.1 * abs(h):
            raise ValueError('Corriente de referencia demasiado próxima al residual.')
        punto.update(
            residual_real=h.real,
            residual_imag=h.imag,
            transferencia_real=a.real,
            transferencia_imag=a.imag,
            ganancia=abs(a) / config.rs,
            correccion_fase=normalizar_fase(-math.degrees(cmath.phase(a))),
        )
    positivo(punto['ganancia'], 'Ganancia medida')
    validar_fase(punto, anterior)
    return punto


def guardar(perfil, ruta=None):
    guardar_json(ruta or RUTA_CALIBRACION, validar(perfil))


def cargar(ruta=None):
    perfil = cargar_json(ruta or RUTA_CALIBRACION)
    return validar(perfil) if perfil is not None else None
