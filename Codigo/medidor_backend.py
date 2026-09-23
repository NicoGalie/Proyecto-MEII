import pyvisa
import math
import time

GANANCIA_AMP = 5.0

def _conectar_instrumentos(requiere_generador=False):
    """Busca y devuelve el osciloscopio y opcionalmente el generador."""
    rm = pyvisa.ResourceManager('@py')
    osc, gen = None, None
    
    for direccion in rm.list_resources():
        try:
            inst = rm.open_resource(direccion)
            inst.timeout = 4000
            inst.write_termination = '\n'
            inst.read_termination = '\n'
            idn = inst.query("*IDN?")
            if "DSO" in idn and "UTG" not in idn:
                osc = inst
            elif "UTG" in idn:
                gen = inst
        except:
            pass
            
    if requiere_generador and (not osc or not gen):
        return None, None
    return osc, gen

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

def medicion_simple(r_sensora):
    osc, _ = _conectar_instrumentos(requiere_generador=False)
    if not osc: return {"exito": False, "error": "No se encontró el osciloscopio."}

    try:
        v_i = _leer_seguro(osc, ":MEASure:VRMS? CHANnel1")
        v_r = _leer_seguro(osc, ":MEASure:VRMS? CHANnel2")
        freq = _leer_seguro(osc, ":MEASure:FREQuency? CHANnel2")
        fase = _leer_seguro(osc, ":MEASure:PHASe? CHANnel2,CHANnel1")
        
        # Filtro Anti-Basura
        if v_i > 1e10 or v_r > 1e10 or freq > 1e10 or fase > 1e10:
            return {"exito": False, "error": f"El equipo devolvió un código de error numérico. V_i={v_i}, V_r={v_r}, Freq={freq}, Fase={fase}"}
            
        datos = _procesar_matematica(v_i, v_r, freq, fase, r_sensora)
        return {"exito": True, "datos": datos}
    except Exception as e:
        return {"exito": False, "error": f"Error de lectura: {str(e)}"}
    finally:
        osc.close()

def barrido_automatico(f_ini, f_fin, pasos, r_sensora):
    osc, gen = _conectar_instrumentos(requiere_generador=True)
    if not osc or not gen:
        return {"exito": False, "error": "Se requieren Osciloscopio y Generador encendidos para el barrido."}

    paso_frec = (f_fin - f_ini) / max(1, (pasos - 1))
    frecuencias_objetivo = [f_ini + i * paso_frec for i in range(pasos)]
    
    resultados = {"exito": True, "frec_medida": [], "esr": [], "cap_ind": [], "q_d": [], "tipo": "", "errores_log": []}

    try:
        for f in frecuencias_objetivo:
            try:
                gen.write(f":CHANnel1:BASE:FREQuency {f}")
                time.sleep(0.5)
                
                osc.write(":AUToset")
                time.sleep(3.0) 
                
                v_i = _leer_seguro(osc, ":MEASure:VRMS? CHANnel1")
                v_r = _leer_seguro(osc, ":MEASure:VRMS? CHANnel2")
                fase = _leer_seguro(osc, ":MEASure:PHASe? CHANnel2,CHANnel1")
                
                # Ya no medimos la frecuencia con el osciloscopio, usamos la que emitimos 'f'
                if v_i > 1e10 or v_r > 1e10 or fase > 1e10:
                    raise ValueError(f"Valores espurios: V_i={v_i}, V_r={v_r}, Fase={fase}")
                
                datos = _procesar_matematica(v_i, v_r, f, fase, r_sensora)
                
                resultados["frec_medida"].append(f)
                resultados["esr"].append(datos["esr_num"])
                resultados["cap_ind"].append(datos["valor_num"])
                resultados["q_d"].append(datos["factor_num"])
                resultados["tipo"] = datos["tipo"]
                
                print(f"✅ Punto medido: {f:.1f} Hz")
                
            except Exception as e_punto:
                msj_error = f"⚠️ Punto saltado en {f:.1f} Hz. Detalle: {str(e_punto)}"
                print(msj_error)
                resultados["errores_log"].append(msj_error)
                continue 
                
        if not resultados["frec_medida"]:
            return {"exito": False, "error": f"El barrido falló en TODAS las frecuencias.\nÚltimo error: {resultados['errores_log'][-1]}"}
            
        return resultados
    except Exception as e_general:
        return {"exito": False, "error": f"Falla crítica en el sistema: {str(e_general)}"}
    finally:
        osc.close()
        gen.close()