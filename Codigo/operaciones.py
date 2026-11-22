"""Medición simple, barrido cancelable y adquisición de calibración INA128P."""

from datetime import datetime, timezone

import calibracion
from calculos import calcular, fasor
from cancelacion import Cancelacion, Cancelado
from configuracion import positivo
from instrumentos import conectar
from modelos import Fila, ResultadoBarrido, ResultadoCalibracion
from osciloscopios import validar_tiempo_promedio

INTENTOS_POR_PUNTO = 4


def frecuencias(inicio, fin, cantidad):
    """Construye un barrido lineal que incluye el inicio y el final."""
    positivo(inicio, 'Frecuencia inicial')
    positivo(fin, 'Frecuencia final')
    if fin <= inicio or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 2:
        raise ValueError('El barrido requiere final mayor que inicial y al menos dos puntos.')
    lista = []
    for indice in range(cantidad):
        frecuencia = inicio + indice * (fin - inicio) / (cantidad - 1)
        lista.append(frecuencia)
    return lista


def avisar(progreso, texto):
    if progreso:
        progreso(dict(tipo='estado', texto=texto))


def adquirir(sesion, frecuencia, procesar, control, progreso=None, promedio=None):
    """Preparar → leer → procesar. Repetir si falla alguna de esas etapas.

    ``procesar`` es la función que recibe la lectura: calcula la impedancia
    al medir, o calcula un punto de referencia al calibrar. Así un error de
    cálculo también provoca una adquisición nueva, no solo otra cuenta.
    """
    sesion.validar_promedio(promedio)
    for intento in range(1, INTENTOS_POR_PUNTO + 1):
        control.comprobar()
        try:
            sesion.preparar(frecuencia)
            lectura, datos_promedio = sesion.leer(promedio, progreso)
            if abs(lectura.frecuencia / frecuencia - 1) > 0.05:
                raise ValueError('La frecuencia medida no coincide con la programada.')
            dato = procesar(lectura, intento, datos_promedio)
            control.comprobar()
            return dato
        except Cancelado:
            raise
        except Exception as error:
            if intento == INTENTOS_POR_PUNTO:
                raise ValueError(f'Falló tras {intento} intentos: {error}') from error
            avisar(progreso, f'Reintento {intento}/3 en {frecuencia:g} Hz: {error}')


def medir_una_frecuencia(
    sesion, frecuencia, config, perfil, usar, control, progreso=None, promedio=None
):
    """Usado tanto por la medición simple como por cada punto del barrido."""

    def procesar_lectura(lectura, intento, datos_promedio):
        ajuste = calibracion.seleccionar(
            perfil=perfil,
            config=config,
            frecuencia=lectura.frecuencia,
            identidad=sesion.identidad,
            metodo=sesion.metodo,
            usar=usar,
            objetivo=frecuencia,
        )
        return calcular(
            lectura=lectura,
            configuracion=config,
            ajuste=ajuste,
            objetivo=frecuencia,
            intentos=intento,
            promedio=datos_promedio,
        )

    return adquirir(sesion, frecuencia, procesar_lectura, control, progreso, promedio)


def medir(frecuencia, config, perfil=None, usar=False, promedio=None, control=None, progreso=None):
    """Validar los datos, conectar los equipos y medir una sola frecuencia."""
    positivo(frecuencia, 'Frecuencia de medición')
    if promedio is not None:
        validar_tiempo_promedio(promedio)
    control = control or Cancelacion()
    with conectar(control) as sesion:
        return medir_una_frecuencia(
            sesion, frecuencia, config, perfil, usar, control, progreso, promedio
        )


def barrer(inicio, fin, cantidad, config, perfil=None, usar=False, control=None, progreso=None):
    """Repetir la misma medición y guardar una fila por frecuencia intentada."""
    lista = frecuencias(inicio, fin, cantidad)
    control = control or Cancelacion()
    resultado = ResultadoBarrido()
    try:
        with conectar(control) as sesion:
            for indice, frecuencia in enumerate(lista, 1):
                control.comprobar()
                avisar(progreso, f'Midiendo {indice}/{cantidad}: {frecuencia:g} Hz')
                try:
                    dato = medir_una_frecuencia(
                        sesion, frecuencia, config, perfil, usar, control, progreso
                    )
                    fila = Fila(frecuencia, medicion=dato, intentos=dato.intentos)
                except Cancelado:
                    resultado.filas.append(
                        Fila(frecuencia, 'CANCELADO', error='Adquisición cancelada')
                    )
                    raise
                except Exception as error:
                    fila = Fila(frecuencia, 'ERROR', error=str(error), intentos=INTENTOS_POR_PUNTO)
                resultado.filas.append(fila)
                if progreso:
                    progreso(dict(tipo='punto', indice=indice, total=cantidad, fila=fila))
    except Cancelado:
        resultado.cancelado = True
    except Exception as error:
        resultado.error = str(error)
    if (
        not resultado.cancelado
        and not resultado.error
        and not any(fila.medicion for fila in resultado.filas)
    ):
        resultado.error = 'No se obtuvieron mediciones válidas.'
    return resultado


def _encabezado(config, sesion, puntos):
    return dict(
        fecha=datetime.now(timezone.utc).isoformat(),
        r_sensora=config.rs,
        circuito=config.circuito(),
        osciloscopio=sesion.identidad.copy(),
        metodo_medicion=sesion.metodo,
        puntos=puntos,
    )


def _punto_abierto(sesion, primera, objetivo, control):
    lecturas = [primera]
    for _ in range(2):
        control.comprobar()
        lectura, _ = sesion.leer()
        lecturas.append(lectura)
    if any(abs(l.frecuencia / objetivo - 1) > 0.05 for l in lecturas):
        raise ValueError('Frecuencia incorrecta en circuito abierto.')
    valores = [fasor(l) for l in lecturas]
    h = sum(valores) / 3
    if abs(h) <= 1e-12 or max(abs(x - h) for x in valores) > 0.01 * abs(h):
        raise ValueError('El residual no es estable entre tres capturas.')
    return dict(
        frecuencia_objetivo=objetivo,
        frecuencia=sum(l.frecuencia for l in lecturas) / 3,
        residual_real=h.real,
        residual_imag=h.imag,
        lecturas=[
            dict(v_i_out=l.vo, v_rms=l.vz, frecuencia=l.frecuencia, fase_cruda=l.fase)
            for l in lecturas
        ],
    )


def medir_abierto(inicio, fin, cantidad, config, control=None, progreso=None):
    lista = frecuencias(inicio, fin, cantidad)
    control = control or Cancelacion()
    puntos = []
    with conectar(control) as sesion:
        sesion.osc.circuito_abierto = True
        for indice, frecuencia in enumerate(lista, 1):

            def procesar_abierto(lectura, intento, datos_promedio):
                return _punto_abierto(sesion, lectura, frecuencia, control)

            punto = adquirir(sesion, frecuencia, procesar_abierto, control, progreso)
            puntos.append(punto)
            avisar(progreso, f'Circuito abierto: {indice}/{cantidad} frecuencias')
        control.comprobar()
        return calibracion.validar_abierto(_encabezado(config, sesion, puntos))


def calibrar(inicio, fin, cantidad, config, referencia, abierto=None, control=None, progreso=None):
    lista = frecuencias(inicio, fin, cantidad)
    positivo(referencia, 'Resistencia conocida')
    control = control or Cancelacion()
    resultado = ResultadoCalibracion()
    if abierto is not None:
        calibracion.validar_abierto(abierto)
        if (
            calibracion.configuracion_perfil(abierto) != config
            or [p['frecuencia_objetivo'] for p in abierto['puntos']] != lista
        ):
            raise ValueError('Repetí el abierto con la misma Rs, RG y frecuencias.')
    try:
        with conectar(control) as sesion:
            if abierto and (
                abierto.get('osciloscopio') != sesion.identidad
                or abierto.get('metodo_medicion') != sesion.metodo
            ):
                raise ValueError('El circuito abierto corresponde a otro osciloscopio o método.')
            for indice, frecuencia in enumerate(lista, 1):

                def procesar_referencia(lectura, intento, datos_promedio):
                    punto_anterior = resultado.puntos[-1] if resultado.puntos else None
                    punto_abierto = abierto['puntos'][indice - 1] if abierto else None
                    return calibracion.crear_punto(
                        lectura, frecuencia, config, referencia, punto_anterior, punto_abierto
                    )

                punto = adquirir(sesion, frecuencia, procesar_referencia, control, progreso)
                resultado.puntos.append(punto)
                if progreso:
                    progreso(dict(tipo='calibracion', indice=indice, total=cantidad, punto=punto))
            control.comprobar()
            perfil = _encabezado(config, sesion, resultado.puntos)
            perfil.update(version=2 if abierto else 1, r_referencia=referencia)
            if abierto:
                perfil['abierto'] = abierto
            resultado.perfil = calibracion.validar(perfil)
    except Cancelado:
        resultado.cancelado = True
    except Exception as error:
        resultado.error = str(error)
    return resultado
