import pyvisa
import math
import cmath
import time
from datetime import datetime, timezone
import calibracion as ajustes
from osciloscopios import Osciloscopio, protocolo_para, validar_calibracion

GANANCIA_AMP = 5.0
REINTENTOS_POR_FRECUENCIA = 3

def _conectar_instrumentos(requiere_generador=False):
    """Busca y devuelve el osciloscopio y opcionalmente el generador."""
    rm = pyvisa.ResourceManager('@py')
    osc, gen = None, None
    osciloscopios, errores = [], []
    try:
        # Estos equipos usan USBTMC. Evita explorar los 32 puertos serie
        # del sistema, que no corresponden a los instrumentos conectados.
        for direccion in rm.list_resources('USB?*::INSTR'):
            inst = None
            try:
                inst = rm.open_resource(direccion)
                inst.timeout = 4000
                inst.write_termination = '\n'
                inst.read_termination = '\n'
                idn = inst.query("*IDN?").strip()
                protocolo = protocolo_para(idn)
                if protocolo is not None:
                    osciloscopios.append(Osciloscopio(inst, idn, protocolo))
                elif "UTG" in idn.upper() and gen is None:
                    gen = inst
                else:
                    inst.close()
            except Exception as error:
                errores.append(str(error))
                if inst is not None:
                    inst.close()
        if len(osciloscopios) > 1:
            raise RuntimeError('Hay más de un osciloscopio compatible conectado. Dejá conectado por USB el que quieras usar para esta medición.')
        osc = osciloscopios[0] if osciloscopios else None
        if not osc or (requiere_generador and not gen):
            raise RuntimeError(
                "No se encontraron los instrumentos necesarios. Verificá que estén "
                "encendidos y conectados por USB. Si ya están conectados, pulsá "
                "el botón «Habilitar acceso USB» en Configuración de Hardware. "
                + ' '.join(errores)
            )
        osc.configurar()
        if gen is not None and not requiere_generador:
            gen.close()
            gen = None
        return rm, osc, gen
    except Exception:
        for inst in (*osciloscopios, gen):
            if inst is not None:
                inst.close()
        rm.close()
        raise

def _validar_lecturas(v_i_out, v_rms, frecuencia, fase_cruda):
    for valor, nombre in ((v_i_out, 'V I_OUT'), (v_rms, 'V RMS'), (frecuencia, 'La frecuencia')):
        ajustes.positivo(valor, nombre)
        if valor > 1e10:
            raise ValueError(f'{nombre}: el instrumento devolvió un código de error numérico.')
    if not math.isfinite(fase_cruda) or abs(fase_cruda) > 360:
        raise ValueError('La fase medida no es válida.')


def _procesar_matematica(v_i_out, v_rms, frecuencia, fase_cruda, r_sensora, calibracion=None):
    """Calcula parámetros solo a partir de lecturas físicamente válidas."""
    _validar_lecturas(v_i_out, v_rms, frecuencia, fase_cruda)
    ajustes.positivo(r_sensora, 'La resistencia sensora')
    ganancia, correccion = GANANCIA_AMP, 0.0
    if calibracion is not None:
        ganancia, correccion = ajustes.correcciones(calibracion, frecuencia, r_sensora)
    ajustes.positivo(ganancia, 'La ganancia del amplificador')
    fase = ajustes.normalizar_fase(fase_cruda - 180.0 - correccion)
    i_rms = v_i_out / (r_sensora * ganancia)
    ajustes.positivo(i_rms, 'La corriente calculada')
    z_mod = v_rms / i_rms
    ajustes.positivo(z_mod, 'La impedancia calculada')
    if calibracion is not None and calibracion.get('version') == 2:
        transferencia, residual = ajustes.coeficientes(calibracion, frecuencia, r_sensora)
        ganancia = abs(transferencia) / r_sensora
        correccion = ajustes.normalizar_fase(-math.degrees(cmath.phase(transferencia)) - 180)
        respuesta = ajustes.fasor(v_i_out, v_rms, fase_cruda) - residual
        if abs(respuesta) <= max(1e-12, abs(residual) * .01):
            raise ValueError('La corriente no se distingue del residual de circuito abierto.')
        z = transferencia / respuesta
        z_mod = abs(z)
        ajustes.positivo(z_mod, 'La impedancia compensada')
        fase = math.degrees(cmath.phase(z))
        i_rms = v_rms / z_mod
    esr = z_mod * math.cos(math.radians(fase))
    xs = z_mod * math.sin(math.radians(fase))
    if esr < 0:
        raise ValueError(f'ESR negativa ({esr:.6g} Ω), con fase corregida {fase:.6g}°. Revisá la fase, conexiones o calibración.')
    omega = 2 * math.pi * frecuencia
    tipo = 'RESISTENCIA'
    valor, factor = esr, None
    valor_str, factor_str = f'{esr:.2f} Ω', 'N/A'
    if fase < 0:
        tipo = 'CAPACITOR'
        valor = 1 / (omega * abs(xs))
        factor = esr / abs(xs)
        valor_str = f'{valor * 1e6:.2f} μF' if valor >= 1e-6 else f'{valor * 1e9:.2f} nF'
        factor_str = f'Factor D: {factor:.4f}'
    elif fase > 0:
        tipo = 'INDUCTOR'
        valor = abs(xs) / omega
        factor = abs(xs) / esr if esr > 0 else None
        valor_str = f'{valor * 1000:.2f} mH' if valor >= 1e-3 else f'{valor * 1e6:.2f} μH'
        factor_str = f'Factor Q: {factor:.2f}' if factor is not None else 'Factor Q: ∞ (ESR = 0)'
    if not all(math.isfinite(v) for v in (esr, xs, valor)) or (factor is not None and not math.isfinite(factor)):
        raise ValueError('Los parámetros calculados no son finitos; la lectura no es válida.')
    return {
        'v_i': f'{v_i_out:.4f} V', 'v_rms': f'{v_rms:.4f} V',
        'frecuencia': f'{frecuencia:.2f} Hz', 'fase_real': f'{fase:.2f}°',
        'i_rms': f'{i_rms * 1000:.2f} mA', 'z_mod': f'{z_mod:.2f} Ω',
        'esr_str': f'{esr:.4f} Ω', 'xs_str': f'{xs:.2f} Ω',
        'tipo': tipo, 'valor_final': valor_str, 'factor_str': factor_str,
        'esr_num': esr, 'xs_num': xs, 'z_num': z_mod, 'fase_num': fase,
        'valor_num': valor, 'factor_num': factor, 'frecuencia_num': frecuencia,
        'ganancia_num': ganancia, 'correccion_fase': correccion,
        'calibrada': calibracion is not None,
    }


def _leer_seguro(osc, comando, max_reintentos=5):
    ultima_respuesta = ''
    for intento in range(max_reintentos):
        try:
            ultima_respuesta = osc.query(comando).strip()
            valor = float(ultima_respuesta)
            if not math.isfinite(valor) or abs(valor) > 1e10:
                raise ValueError('Lectura no finita o código de error numérico.')
            return valor
        except ValueError:
            if intento < max_reintentos - 1:
                time.sleep(1.0)
    raise ValueError(f"Comando '{comando}' falló. El equipo devolvió: '{ultima_respuesta}'")


def _leer_medicion(osc):
    lecturas = osc.leer(_leer_seguro)
    _validar_lecturas(*lecturas)
    return lecturas


def _cerrar(rm, *instrumentos):
    for inst in instrumentos:
        if inst is not None:
            try:
                inst.close()
            except Exception:
                pass
    if rm is not None:
        rm.close()


def medicion_simple(r_sensora, calibracion=None):
    rm, osc = None, None
    try:
        ajustes.positivo(r_sensora, 'La resistencia sensora')
        rm, osc, _ = _conectar_instrumentos()
        validar_calibracion(osc, calibracion)
        for intento in range(REINTENTOS_POR_FRECUENCIA + 1):
            try:
                osc.autoset()
                time.sleep(3.0)
                datos = _procesar_matematica(*_leer_medicion(osc), r_sensora, calibracion)
                datos['intentos'] = intento + 1
                return {'exito': True, 'datos': datos}
            except Exception as error:
                if intento == REINTENTOS_POR_FRECUENCIA:
                    raise ValueError(f'Falló tras {intento + 1} intentos: {error}') from error
    except Exception as error:
        return {'exito': False, 'error': f'Error de lectura: {error}'}
    finally:
        _cerrar(rm, osc)


def _frecuencias(f_ini, f_fin, pasos, r_sensora):
    ajustes.positivo(f_ini, 'La frecuencia inicial')
    ajustes.positivo(f_fin, 'La frecuencia final')
    ajustes.positivo(r_sensora, 'La resistencia sensora')
    if f_fin <= f_ini or not isinstance(pasos, int) or isinstance(pasos, bool) or pasos < 2:
        raise ValueError('La frecuencia final debe ser mayor que la inicial y se requieren al menos 2 puntos.')
    paso = (f_fin - f_ini) / (pasos - 1)
    return [f_ini + i * paso for i in range(pasos)]


def _preparar_frecuencia(osc, gen, frecuencia):
    osc.frecuencia_objetivo = frecuencia
    gen.write(f':CHANnel1:BASE:FREQuency {frecuencia}')
    time.sleep(0.5)
    osc.autoset()
    time.sleep(3.0)


def _medir_punto(osc, gen, frecuencia, procesar, al_reintentar=None):
    """Intento inicial y hasta tres repeticiones completas en la misma frecuencia."""
    for intento in range(REINTENTOS_POR_FRECUENCIA + 1):
        try:
            _preparar_frecuencia(osc, gen, frecuencia)
            lecturas = _leer_medicion(osc)
            if abs(lecturas[2] / frecuencia - 1) > .05:
                raise ValueError('La frecuencia medida no coincide con la programada.')
            punto = procesar(lecturas)
            punto['intentos'] = intento + 1
            return punto
        except Exception as error:
            if intento == REINTENTOS_POR_FRECUENCIA:
                raise ValueError(f'Falló tras {intento + 1} intentos: {error}') from error
            if al_reintentar is not None:
                al_reintentar(intento + 1, str(error))


def _aviso_reintento(progreso, indice, total, frecuencia):
    def avisar(numero, error):
        if progreso is not None:
            progreso({'indice': indice, 'total': total, 'frecuencia': frecuencia,
                      'reintento': numero, 'max_reintentos': REINTENTOS_POR_FRECUENCIA,
                      'error': error})
    return avisar


def barrido_automatico(f_ini, f_fin, pasos, r_sensora, calibracion=None, progreso=None):
    rm, osc, gen = None, None, None
    puntos, errores = [], []
    try:
        frecuencias = _frecuencias(f_ini, f_fin, pasos, r_sensora)
        if calibracion is not None:
            ajustes.correcciones(calibracion, f_ini, r_sensora)
            ajustes.correcciones(calibracion, f_fin, r_sensora)
        rm, osc, gen = _conectar_instrumentos(True)
        validar_calibracion(osc, calibracion)
        for indice, f in enumerate(frecuencias, 1):
            try:
                datos = _medir_punto(
                    osc, gen, f,
                    lambda lecturas: _procesar_matematica(*lecturas, r_sensora, calibracion),
                    _aviso_reintento(progreso, indice, pasos, f),
                )
                datos['frecuencia_objetivo'] = f
                puntos.append(datos)
                evento = {'indice': indice, 'total': pasos, 'punto': datos}
            except Exception as error:
                mensaje = f'Punto omitido en {f:g} Hz: {error}'
                errores.append(mensaje)
                evento = {'indice': indice, 'total': pasos, 'error': mensaje}
            if progreso is not None:
                progreso(evento)
        if not puntos:
            return {'exito': False, 'error': f'El barrido no obtuvo lecturas válidas. {errores[-1]}', 'errores_log': errores}
        por_tipo = {tipo: [p for p in puntos if p['tipo'] == tipo] for tipo in ('CAPACITOR', 'INDUCTOR', 'RESISTENCIA')}
        tipos = [t for t, valores in por_tipo.items() if valores]
        return {
            'exito': True, 'puntos': puntos, 'por_tipo': por_tipo,
            'tipo': tipos[0] if len(tipos) == 1 else 'MIXTO',
            'frec_medida': [p['frecuencia_num'] for p in puntos],
            'esr': [p['esr_num'] for p in puntos], 'errores_log': errores,
        }
    except Exception as error:
        return {'exito': False, 'error': str(error)}
    finally:
        _cerrar(rm, osc, gen)


def _procesar_punto_calibracion(lecturas, f_objetivo, r_sensora, r_referencia, anterior=None, abierto=None):
    v_i, v_r, frecuencia, fase = lecturas
    _validar_lecturas(v_i, v_r, frecuencia, fase)
    ganancia = v_i * r_referencia / (v_r * r_sensora)
    ajustes.positivo(ganancia, 'La ganancia medida')
    punto = {
        'frecuencia_objetivo': f_objetivo, 'frecuencia': frecuencia,
        'v_i_out': v_i, 'v_rms': v_r, 'fase_cruda': fase,
        'correccion_fase': ajustes.normalizar_fase(fase - 180),
        'ganancia': ganancia,
    }
    if abierto is not None:
        h = ajustes.complejo(abierto, 'residual')
        a = (ajustes.fasor(v_i, v_r, fase) - h) * r_referencia
        if abs(a / r_referencia) <= .1 * abs(h):
            raise ValueError('La resistencia de referencia produce una corriente demasiado próxima al residual. Usá una referencia de menor valor.')
        punto.update(residual_real=h.real, residual_imag=h.imag,
                     transferencia_real=a.real, transferencia_imag=a.imag,
                     ganancia=abs(a) / r_sensora,
                     correccion_fase=ajustes.normalizar_fase(-math.degrees(cmath.phase(a)) - 180))
        ajustes.positivo(punto['ganancia'], 'La ganancia compensada')
        if abs(punto['correccion_fase']) >= 90:
            raise ValueError('Transferencia incoherente con el amplificador inversor.')
    ajustes.validar_fase_referencia(punto, anterior)
    return punto


def validar_abierto(abierto, frecuencias, r_sensora, osc=None):
    ajustes.validar_abierto(abierto)
    if (not math.isclose(abierto['r_sensora'], r_sensora, rel_tol=1e-9)
            or [p['frecuencia_objetivo'] for p in abierto['puntos']] != frecuencias):
        raise ValueError('Repetí el circuito abierto con la misma R1 y el mismo barrido.')
    if osc is not None:
        validar_calibracion(osc, abierto)


def _procesar_abierto(osc, frecuencia, primera):
    lecturas = [primera] + [_leer_medicion(osc) for _ in range(2)]
    for valores in lecturas:
        if abs(valores[2] / frecuencia - 1) > .05:
            raise ValueError('La frecuencia del circuito abierto no coincide con la programada.')
    fasores = [ajustes.fasor(v_i, v_r, fase) for v_i, v_r, f, fase in lecturas]
    h = sum(fasores) / len(fasores)
    if abs(h) <= 1e-12 or max(abs(x - h) for x in fasores) > .01 * abs(h):
        raise ValueError('El residual de circuito abierto no es estable entre tres capturas (tolerancia 1%).')
    return {'frecuencia_objetivo': frecuencia, 'frecuencia': sum(x[2] for x in lecturas) / 3,
            'residual_real': h.real, 'residual_imag': h.imag,
            'lecturas': [dict(zip(('v_i_out', 'v_rms', 'frecuencia', 'fase_cruda'), x)) for x in lecturas]}


def medir_abierto(f_ini, f_fin, pasos, r_sensora, progreso=None):
    """Primer paso de calibración: Zx abierto, sin mover las sondas."""
    rm, osc, gen = None, None, None
    puntos, errores = [], []
    try:
        frecuencias = _frecuencias(f_ini, f_fin, pasos, r_sensora)
        rm, osc, gen = _conectar_instrumentos(True)
        osc.circuito_abierto = True
        for indice, f in enumerate(frecuencias, 1):
            try:
                punto = _medir_punto(osc, gen, f, lambda lectura: _procesar_abierto(osc, f, lectura),
                                     _aviso_reintento(progreso, indice, pasos, f))
                puntos.append(punto)
                evento = {'indice': indice, 'total': pasos, 'punto': punto, 'abierto': True}
            except Exception as error:
                mensaje = f'Circuito abierto inválido en {f:g} Hz: {error}'
                errores.append(mensaje)
                evento = {'indice': indice, 'total': pasos, 'error': mensaje, 'abierto': True}
            if progreso:
                progreso(evento)
        if errores:
            return {'exito': False, 'error': 'El circuito abierto quedó incompleto. ' + errores[-1], 'errores_log': errores}
        abierto = {'r_sensora': r_sensora, 'puntos': puntos, 'fecha': datetime.now(timezone.utc).isoformat()}
        if isinstance(osc, Osciloscopio):
            abierto.update(osciloscopio=osc.identidad.copy(), metodo_medicion=osc.metodo_medicion)
        ajustes.validar_abierto(abierto)
        return {'exito': True, 'abierto': abierto}
    except Exception as error:
        return {'exito': False, 'error': str(error)}
    finally:
        _cerrar(rm, osc, gen)


def calibrar_barrido(f_ini, f_fin, pasos, r_sensora, r_referencia, progreso=None, abierto=None):
    """La resistencia conocida sustituye Zx; no aplica un perfil anterior."""
    rm, osc, gen = None, None, None
    puntos, errores = [], []
    try:
        frecuencias = _frecuencias(f_ini, f_fin, pasos, r_sensora)
        ajustes.positivo(r_referencia, 'La resistencia conocida')
        rm, osc, gen = _conectar_instrumentos(True)
        if abierto is not None:
            validar_abierto(abierto, frecuencias, r_sensora, osc)
        for indice, f in enumerate(frecuencias, 1):
            try:
                punto = _medir_punto(
                    osc, gen, f,
                    lambda lecturas: _procesar_punto_calibracion(lecturas, f, r_sensora, r_referencia, puntos[-1] if puntos else None,
                                                               abierto['puntos'][indice - 1] if abierto else None),
                    _aviso_reintento(progreso, indice, pasos, f),
                )
                puntos.append(punto)
                evento = {'indice': indice, 'total': pasos, 'punto': punto}
            except Exception as error:
                mensaje = f'Calibración inválida en {f:g} Hz: {error}'
                errores.append(mensaje)
                evento = {'indice': indice, 'total': pasos, 'error': mensaje}
            if progreso is not None:
                progreso(evento)
        if errores:
            return {'exito': False, 'error': 'La calibración quedó incompleta y no se aplicó. ' + errores[-1], 'puntos': puntos, 'errores_log': errores}
        perfil = {
            'version': 2 if abierto else 1, 'fecha': datetime.now(timezone.utc).isoformat(),
            'r_sensora': r_sensora, 'r_referencia': r_referencia, 'puntos': puntos,
        }
        if abierto:
            perfil['abierto'] = abierto
        if isinstance(osc, Osciloscopio):
            perfil['osciloscopio'] = osc.identidad.copy()
            perfil['metodo_medicion'] = osc.metodo_medicion
        ajustes.validar_perfil(perfil)
        return {'exito': True, 'calibracion': perfil, 'puntos': puntos}
    except Exception as error:
        return {'exito': False, 'error': str(error), 'puntos': puntos}
    finally:
        _cerrar(rm, osc, gen)
