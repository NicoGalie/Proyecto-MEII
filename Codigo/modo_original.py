"""Algoritmo del commit 03d21e8; comunicación delegada al osciloscopio.

Se conservan intencionalmente umbral ±2°, ESR negativa a cero, ganancia 5,
frecuencia programada en barrido y reintentos únicamente por lectura textual.
"""

import math
import time

GANANCIA_AMP = 5.0


def _procesar_matematica(v_i_out, v_rms, frecuencia, fase_cruda, r_sensora):
    """Aplica las correcciones de hardware y el modelo matemático."""
    fase_verdadera = fase_cruda - 180.0
    if fase_verdadera < -180.0: fase_verdadera += 360.0
    elif fase_verdadera > 180.0: fase_verdadera -= 360.0
        
    fase_rad = math.radians(fase_verdadera)
    
    # Evitar divisiones por cero si hay ruido
    if r_sensora == 0 or GANANCIA_AMP == 0: i_rms = 0.0001
    else: i_rms = v_i_out / (r_sensora * GANANCIA_AMP)
    
    if i_rms == 0: z_mod = float('inf')
    else: z_mod = v_rms / i_rms
    
    r_esr = z_mod * math.cos(fase_rad)
    x_s = z_mod * math.sin(fase_rad)
    omega = 2 * math.pi * frecuencia
    
    if r_esr < 0: r_esr = 0.0

    tipo = "RESISTENCIA"
    valor_num, factor_num = 0.0, 0.0
    valor_str, factor_str = f"{r_esr:.2f} Ω", "N/A"

    if fase_verdadera < -2.0:
        tipo = "CAPACITOR"
        valor_num = 1 / (omega * abs(x_s)) if (x_s != 0 and omega != 0) else 0
        factor_num = r_esr / abs(x_s) if x_s != 0 else 0
        valor_str = f"{valor_num * 1e6:.2f} μF" if valor_num >= 1e-6 else f"{valor_num * 1e9:.2f} nF"
        factor_str = f"Factor D: {factor_num:.4f}"
        
    elif fase_verdadera > 2.0:
        tipo = "INDUCTOR"
        valor_num = abs(x_s) / omega if omega != 0 else 0
        factor_num = abs(x_s) / r_esr if r_esr > 0 else float('inf')
        valor_str = f"{valor_num * 1000:.2f} mH" if valor_num >= 1e-3 else f"{valor_num * 1e6:.2f} μH"
        factor_str = f"Factor Q: {factor_num:.2f}"

    return {
        "v_i": f"{v_i_out:.4f} V", "v_rms": f"{v_rms:.4f} V", 
        "frecuencia": f"{frecuencia:.2f} Hz", "fase_real": f"{fase_verdadera:.2f}°",
        "i_rms": f"{i_rms * 1000:.2f} mA", "z_mod": f"{z_mod:.2f} Ω",
        "esr_str": f"{r_esr:.4f} Ω", "xs_str": f"{x_s:.2f} Ω",
        "tipo": tipo, "valor_final": valor_str, "factor_str": factor_str,
        "esr_num": r_esr, "valor_num": valor_num, "factor_num": factor_num
    }

def _leer_seguro(osc, comando, max_reintentos=5):
    """Filtra respuestas basura del osciloscopio (ej. 'NULL') y reintenta."""
    ultima_respuesta = ""
    for _ in range(max_reintentos):
        try:
            ultima_respuesta = osc.query(comando).strip()
            # Si logra convertirlo a float, rompe el bucle y devuelve el valor
            return float(ultima_respuesta)
        except ValueError:
            # Si devuelve texto, esperamos 1 segundo para que termine de acomodar la onda y reintentamos
            time.sleep(1.0)
            
    # Si después de 5 intentos sigue devolviendo texto, lanzamos el error con el texto exacto
    raise ValueError(f"Comando '{comando}' falló. El equipo devolvió textualmente: '{ultima_respuesta}'")


def _leer(osc, frecuencia_barrido=None):
    vi, vr, f, fase = osc.leer_original(_leer_seguro, frecuencia_barrido)
    # Filtro numérico del original. En barrido no se consulta la frecuencia.
    valores = (vi, vr, fase) if frecuencia_barrido is not None else (vi, vr, f, fase)
    if any(valor > 1e10 for valor in valores):
        raise ValueError(f'El equipo devolvió un código de error numérico. V_i={vi}, V_r={vr}, Freq={f}, Fase={fase}')
    return vi, vr, f, fase


def medicion_simple(r_sensora, conectar, cerrar):
    rm, osc = None, None
    try:
        rm, osc, _ = conectar()
        # El original no hace Autoset ni repite la adquisición completa.
        datos = _procesar_matematica(*_leer(osc), r_sensora)
        datos.update(ganancia_num=GANANCIA_AMP, calibrada=False, modo='Original', intentos=1)
        return {'exito': True, 'datos': datos}
    except Exception as error:
        return {'exito': False, 'error': f'Error de lectura: {error}'}
    finally:
        cerrar(rm, osc)


def barrido_automatico(f_ini, f_fin, pasos, r_sensora, conectar, cerrar, progreso=None):
    rm, osc, gen = None, None, None
    resultados = {'exito': True, 'modo': 'Original', 'frec_medida': [], 'esr': [],
                  'cap_ind': [], 'q_d': [], 'tipo': '', 'errores_log': []}
    try:
        rm, osc, gen = conectar(requiere_generador=True)
        paso = (f_fin - f_ini) / max(1, pasos - 1)
        for indice, f in enumerate((f_ini + i * paso for i in range(pasos)), 1):
            try:
                gen.write(f':CHANnel1:BASE:FREQuency {f}')
                time.sleep(.5)
                osc.autoset_original()
                time.sleep(3.0)
                datos = _procesar_matematica(*_leer(osc, f), r_sensora)
                resultados['frec_medida'].append(f)
                resultados['esr'].append(datos['esr_num'])
                resultados['cap_ind'].append(datos['valor_num'])
                resultados['q_d'].append(datos['factor_num'])
                resultados['tipo'] = datos['tipo']
                evento = {'indice': indice, 'total': pasos, 'punto': datos}
            except Exception as error:
                mensaje = f'Punto saltado en {f:.1f} Hz. Detalle: {error}'
                resultados['errores_log'].append(mensaje)
                evento = {'indice': indice, 'total': pasos, 'error': mensaje}
            if progreso is not None:
                progreso(evento)
        if not resultados['frec_medida']:
            ultimo = resultados['errores_log'][-1] if resultados['errores_log'] else 'No se programaron puntos.'
            return {'exito': False, 'error': f'El barrido falló en TODAS las frecuencias.\nÚltimo error: {ultimo}'}
        return resultados
    except Exception as error:
        return {'exito': False, 'error': f'Falla crítica en el sistema: {error}'}
    finally:
        cerrar(rm, osc, gen)
