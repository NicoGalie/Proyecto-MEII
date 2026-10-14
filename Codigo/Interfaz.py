import tkinter as tk
from tkinter import ttk, messagebox
import medidor_backend
import calibracion as ajustes
import instrumentos_usb
import math
import queue
import threading

# --- SOLUCIÓN AL ERROR DE GRÁFICOS EN LINUX ---
import matplotlib
matplotlib.use('TkAgg')  # Obligamos a usar el motor de ventanas
import matplotlib.pyplot as plt
# ----------------------------------------------

_tarea_en_curso = False
_equipos_usb = []
_calibracion = None
_abierto = None


def _actualizar_botones():
    estado = 'disabled' if _tarea_en_curso else 'normal'
    original = modo_medicion.get() == 'Original'
    btn_medir.config(state=estado)
    btn_barrido.config(state=estado)
    btn_actualizar_equipos.config(state=estado)
    btn_calibrar.config(state='disabled' if original else estado)
    btn_abierto.config(state='disabled' if original else estado)
    btn_curvas_cal.config(state='normal' if _calibracion is not None and not _tarea_en_curso else 'disabled')
    chk_calibracion.config(state='normal' if _calibracion is not None and not _tarea_en_curso and not original else 'disabled')
    combo_modo.config(state='disabled' if _tarea_en_curso else 'readonly')
    combo_r.config(state='disabled' if _tarea_en_curso else 'readonly')
    for entrada in (ent_r_cal, ent_cal_ini, ent_cal_fin, ent_cal_pasos):
        entrada.config(state=estado)
    faltan_permisos = any(equipo['estado'] == 'sin_permisos' for equipo in _equipos_usb)
    btn_permisos.config(state='normal' if faltan_permisos and not _tarea_en_curso else 'disabled')


def mostrar_equipos(resultado):
    global _equipos_usb
    if not resultado['exito']:
        _equipos_usb = []
        lbl_equipos.config(text=resultado['error'], fg='red')
        return
    _equipos_usb = resultado['equipos']
    if not _equipos_usb:
        lbl_equipos.config(text='Equipos conectados: ninguno. Conectá y encendé un instrumento USB.', fg='#555555')
        return
    estados = {'conectado': 'listo', 'sin_permisos': 'requiere permiso USB',
               'sin_respuesta': 'conectado, sin respuesta',
               'pendiente_actualizacion': 'permiso configurado; falta comprobar el acceso'}
    lineas = ['Equipos conectados:']
    for equipo in _equipos_usb:
        serie = f" (serie {equipo['serie']})" if equipo['serie'] else ''
        lineas.append(f"• {equipo['nombre']}{serie} — {estados[equipo['estado']]}")
    if any(equipo['estado'] == 'sin_permisos' for equipo in _equipos_usb):
        lineas.append('Primera conexión o acceso pendiente: pulsá «Habilitar acceso USB».')
    if any(equipo['estado'] == 'pendiente_actualizacion' for equipo in _equipos_usb):
        lineas.append('Pulsá «Actualizar equipos» para comprobar el acceso.')
    lbl_equipos.config(text='\n'.join(lineas), fg='#222222')


def actualizar_equipos():
    if _tarea_en_curso:
        return
    lbl_equipos.config(text='Buscando equipos USB...', fg='#555555')
    _iniciar_tarea(lambda: instrumentos_usb.detectar_instrumentos(actualizar=True), mostrar_equipos)


def ejecutar_permisos():
    if _tarea_en_curso or not any(equipo['estado'] == 'sin_permisos' for equipo in _equipos_usb):
        return
    lbl_equipos.config(text='Autorizá el acceso USB en la ventana de Linux para estos instrumentos.', fg='#555555')
    _iniciar_tarea(lambda: instrumentos_usb.habilitar_permisos(_equipos_usb), mostrar_resultado_permisos)


def mostrar_resultado_permisos(resultado):
    if not resultado['exito']:
        messagebox.showerror('Permisos USB', resultado['error'])
    else:
        for equipo in _equipos_usb:
            if equipo['estado'] == 'sin_permisos':
                equipo['estado'] = 'pendiente_actualizacion'
    mostrar_equipos({'exito': True, 'equipos': _equipos_usb})


def _obtener_resistencia():
    valor_texto = combo_r.get()
    multiplicador = 1.0
    if "k" in valor_texto:
        multiplicador = 1000.0
    numero = float(valor_texto.replace("kΩ", "").replace("Ω", "").strip())
    return numero * multiplicador

def _perfil_seleccionado():
    if modo_medicion.get() == 'Original':
        return None
    if usar_calibracion.get():
        if _calibracion is None:
            raise ValueError('Primero realizá una calibración válida.')
        return _calibracion
    return None


def actualizar_estado_calibracion(evento=None):
    if modo_medicion.get() == 'Original':
        lbl_calibracion_uso.config(text='Original: RMS y fase del osciloscopio; ganancia 5, inversión de 180°, umbral ±2°. Calibración desactivada en este modo.', fg='#555555')
        return
    if _calibracion is None:
        lbl_calibracion_uso.config(text='Sin calibración: ganancia nominal 5 y corrección de inversión de 180°.', fg='#555555')
        return
    puntos = _calibracion['puntos']
    resumen = f"R1 = {_calibracion['r_sensora']:g} Ω; referencia = {_calibracion['r_referencia']:g} Ω; {puntos[0]['frecuencia']:g}–{puntos[-1]['frecuencia']:g} Hz"
    if 'osciloscopio' in _calibracion:
        identidad = _calibracion['osciloscopio']
        resumen += f"; {identidad['modelo']} (serie {identidad['serie']})"
    compatible = math.isclose(_obtener_resistencia(), _calibracion['r_sensora'], rel_tol=1e-9)
    estado = 'Aplicando calibración' if usar_calibracion.get() else 'Calibración guardada, desactivada'
    if usar_calibracion.get() and not compatible:
        estado = 'Calibración incompatible con R1 seleccionada'
    lbl_calibracion_uso.config(text=f'{estado}: {resumen}', fg='green' if compatible and usar_calibracion.get() else '#a05200')


def cambiar_modo(evento=None):
    actualizar_estado_calibracion()
    _actualizar_botones()
    # Evitar presentar una lectura previa como si perteneciera al nuevo modo.
    for etiqueta in (lbl_v_i, lbl_v_rms, lbl_frec, lbl_fase, lbl_i_rms, lbl_z, lbl_esr, lbl_xs,
                     lbl_ganancia, lbl_tipo_final, lbl_valor_final, lbl_factor_final):
        etiqueta.config(text='---')
    lbl_estado.config(text=f'Modo {modo_medicion.get()}. Listo para medir.', fg='#555555')


def _iniciar_tarea(operacion, al_terminar, al_progreso=None):
    """Ejecuta la comunicación USB sin bloquear la ventana de Tk."""
    global _tarea_en_curso
    if _tarea_en_curso:
        return
    _tarea_en_curso = True
    _actualizar_botones()
    respuestas = queue.Queue()

    def trabajar():
        try:
            if al_progreso is None:
                resultado = operacion()
            else:
                resultado = operacion(lambda evento: respuestas.put(('progreso', evento)))
            respuestas.put(('resultado', resultado))
        except Exception as error:
            respuestas.put(('resultado', {"exito": False, "error": str(error)}))

    def revisar():
        global _tarea_en_curso
        try:
            while True:
                tipo, resultado = respuestas.get_nowait()
                if tipo == 'resultado':
                    break
                al_progreso(resultado)
        except queue.Empty:
            root.after(100, revisar)
            return
        try:
            al_terminar(resultado)
        finally:
            _tarea_en_curso = False
            btn_medir.config(text="Medición Simple")
            btn_barrido.config(text="Iniciar Barrido")
            btn_calibrar.config(text='2. Medir resistencia y guardar')
            _actualizar_botones()

    threading.Thread(target=trabajar, daemon=True).start()
    root.after(100, revisar)

def ejecutar_medicion():
    try:
        r_sensora = _obtener_resistencia()
        perfil = _perfil_seleccionado()
        modo = modo_medicion.get()
    except ValueError as error:
        messagebox.showerror('Medición', str(error))
        return
    btn_medir.config(state="disabled", text="Midiendo...")
    lbl_estado.config(text="Adquiriendo datos...", fg="blue")
    _iniciar_tarea(
        lambda: (medidor_backend.medicion_simple(r_sensora, modo='Original') if modo == 'Original'
                 else medidor_backend.medicion_simple(r_sensora, perfil)),
        lambda res: mostrar_medicion(res, r_sensora),
    )

def mostrar_medicion(res, r_sensora):
    if res["exito"]:
        d = res["datos"]
        lbl_v_i.config(text=d["v_i"])
        lbl_v_rms.config(text=d["v_rms"])
        lbl_frec.config(text=d["frecuencia"])
        lbl_fase.config(text=d["fase_real"])
        lbl_i_rms.config(text=d["i_rms"])
        lbl_z.config(text=d["z_mod"])
        lbl_esr.config(text=d["esr_str"])
        lbl_xs.config(text=d["xs_str"])
        lbl_ganancia.config(text=f"{d['ganancia_num']:.5g}")
        lbl_tipo_final.config(text=d["tipo"], fg="green")
        lbl_valor_final.config(text=d["valor_final"])
        lbl_factor_final.config(text=d["factor_str"])
        lbl_estado.config(text=f"Lectura exitosa — {d.get('modo', 'Actual')} (Rs = {r_sensora} Ω)", fg="green")
    else:
        for etiqueta in (lbl_v_i, lbl_v_rms, lbl_frec, lbl_fase, lbl_i_rms, lbl_z, lbl_esr, lbl_xs, lbl_ganancia, lbl_valor_final, lbl_factor_final):
            etiqueta.config(text='---')
        lbl_tipo_final.config(text='LECTURA INVÁLIDA', fg='red')
        lbl_estado.config(text=res["error"], fg="red")
        

def ejecutar_barrido():
    try:
        f_ini = float(ent_f_ini.get())
        f_fin = float(ent_f_fin.get())
        pasos = int(ent_pasos.get())
        r_sensora = _obtener_resistencia()
        perfil = _perfil_seleccionado()
        modo = modo_medicion.get()
    except ValueError as error:
        messagebox.showerror("Error", f"Revisá los parámetros de barrido: {error}")
        return

    if not all(math.isfinite(f) for f in (f_ini, f_fin)) or f_ini <= 0 or f_fin <= f_ini or pasos < 2:
        messagebox.showerror("Error", "Usá frecuencias positivas, final mayor que inicial y al menos 2 pasos.")
        return

    btn_barrido.config(state="disabled", text="Barriendo (Toma tiempo)...")
    lbl_estado.config(text="Barrido en curso...", fg="blue")
    _iniciar_tarea(
        lambda reporte: (medidor_backend.barrido_automatico(f_ini, f_fin, pasos, r_sensora, progreso=reporte, modo='Original')
                         if modo == 'Original' else
                         medidor_backend.barrido_automatico(f_ini, f_fin, pasos, r_sensora, perfil, progreso=reporte)),
        mostrar_barrido, progreso_barrido,
    )


def _texto_reintento(evento):
    return f"Reintentando {evento['frecuencia']:g} Hz ({evento['reintento']}/{evento['max_reintentos']}): {evento['error']}"


def progreso_barrido(evento):
    if 'reintento' in evento:
        lbl_estado.config(text=_texto_reintento(evento), fg='#a05200')
    elif 'error' in evento:
        lbl_estado.config(text=evento['error'], fg='red')
    else:
        lbl_estado.config(text=f"Midiendo punto {evento['indice']} de {evento['total']}...", fg='blue')

def _graficar(nombre, titulo, frecuencias, valores, unidad, color):
    plt.figure(nombre)
    plt.clf()
    plt.title(titulo)
    plt.plot(frecuencias, valores, marker='o', color=color)
    plt.xlabel('Frecuencia medida (Hz)')
    plt.ylabel(unidad)
    plt.grid(True)
    plt.tight_layout()


def mostrar_barrido(res):
    if res["exito"]:
        lbl_estado.config(text=f"Barrido finalizado — {res.get('modo', 'Actual')}. Abriendo gráficos.", fg="green")
        for nombre in ('ESR', 'Capacitancia', 'Factor D', 'Inductancia', 'Factor Q', 'Original: ESR', 'Original: Factor', 'Original: Magnitud reactiva'):
            plt.close(nombre)

        if res.get('modo') == 'Original':
            _graficar('Original: ESR', 'Original — ESR vs Frecuencia programada', res['frec_medida'], res['esr'], 'ESR (Ω)', 'red')
            _graficar('Original: Factor', f"Original — Factor {'D' if res['tipo'] == 'CAPACITOR' else 'Q'} vs Frecuencia programada",
                      res['frec_medida'], res['q_d'], 'Factor', 'orange')
            _graficar('Original: Magnitud reactiva', f"Original — {res['tipo']} vs Frecuencia programada",
                      res['frec_medida'], res['cap_ind'], 'Faradios (F)' if res['tipo'] == 'CAPACITOR' else 'Henrios (H)', 'blue')
            for nombre in ('Original: ESR', 'Original: Factor', 'Original: Magnitud reactiva'):
                plt.figure(nombre).axes[0].set_xlabel('Frecuencia programada (Hz)')
            if res.get('errores_log'):
                messagebox.showwarning('Advertencia', f"Se saltaron {len(res['errores_log'])} puntos por error de lectura.")
            plt.show(block=False)
            return
        
        _graficar('ESR', 'ESR vs Frecuencia', res['frec_medida'], res['esr'], 'ESR (Ω)', 'red')
        for tipo, nombre, campo, unidad, color in (
            ('CAPACITOR', 'Capacitancia', 'valor_num', 'Capacitancia (F)', 'blue'),
            ('CAPACITOR', 'Factor D', 'factor_num', 'D (sin unidad)', 'orange'),
            ('INDUCTOR', 'Inductancia', 'valor_num', 'Inductancia (H)', 'green'),
            ('INDUCTOR', 'Factor Q', 'factor_num', 'Q (sin unidad)', 'purple'),
        ):
            puntos = [p for p in res['por_tipo'][tipo] if p[campo] is not None]
            if puntos:
                _graficar(nombre, f'{nombre} vs Frecuencia', [p['frecuencia_num'] for p in puntos], [p[campo] for p in puntos], unidad, color)
        
        if res.get("errores_log"):
            cant_errores = len(res["errores_log"])
            messagebox.showwarning("Advertencia", f"Se saltaron {cant_errores} puntos por error de lectura.")

        plt.show(block=False)
    else:
        lbl_estado.config(text="No se pudo completar el barrido.", fg="red")
        messagebox.showerror("Error de Hardware", res["error"])


def _fila_calibracion(punto):
    return tuple(f"{punto[campo]:.7g}" for campo in ('frecuencia_objetivo', 'frecuencia', 'v_i_out', 'v_rms', 'fase_cruda', 'correccion_fase', 'ganancia'))


def progreso_calibracion(evento):
    if 'reintento' in evento:
        lbl_estado_cal.config(text=_texto_reintento(evento), fg='#a05200')
        return
    etapa = 'Circuito abierto' if evento.get('abierto') else 'Resistencia conocida'
    lbl_estado_cal.config(text=f"{etapa}: punto {evento['indice']} de {evento['total']}...", fg='blue')
    if 'punto' in evento:
        if not evento.get('abierto'):
            tabla_cal.insert('', 'end', values=_fila_calibracion(evento['punto']))
    else:
        lbl_estado_cal.config(text=evento['error'], fg='red')


def _entradas_calibracion():
    r_referencia = float(ent_r_cal.get().replace(',', '.'))
    r_sensora = _obtener_resistencia()
    f_ini, f_fin = float(ent_cal_ini.get()), float(ent_cal_fin.get())
    pasos = int(ent_cal_pasos.get())
    ajustes.positivo(r_referencia, 'La resistencia conocida')
    medidor_backend._frecuencias(f_ini, f_fin, pasos, r_sensora)
    return f_ini, f_fin, pasos, r_sensora, r_referencia


def ejecutar_abierto():
    global _abierto
    if modo_medicion.get() == 'Original':
        return
    try:
        f_ini, f_fin, pasos, r_sensora, _ = _entradas_calibracion()
    except ValueError as error:
        messagebox.showerror('Calibración', str(error))
        return
    _abierto = None
    lbl_estado_cal.config(text='Midiendo con Zx abierto. Mantené las sondas y R1 conectadas.', fg='blue')
    _iniciar_tarea(lambda reporte: medidor_backend.medir_abierto(f_ini, f_fin, pasos, r_sensora, progreso=reporte),
                   mostrar_abierto, progreso_calibracion)


def mostrar_abierto(res):
    global _abierto
    if not res['exito']:
        lbl_estado_cal.config(text=res['error'], fg='red')
        messagebox.showerror('Circuito abierto', res['error'])
        return
    _abierto = res['abierto']
    lbl_estado_cal.config(text='Circuito abierto medido. Colocá la resistencia conocida en Zx, ingresá su valor y pulsá «2. Medir resistencia y guardar».', fg='green')


def ejecutar_calibracion():
    if modo_medicion.get() == 'Original':
        return
    try:
        f_ini, f_fin, pasos, r_sensora, r_referencia = _entradas_calibracion()
        if _abierto is None:
            raise ValueError('Primero dejá Zx abierto y pulsá «1. Medir circuito abierto».')
        medidor_backend.validar_abierto(_abierto, medidor_backend._frecuencias(f_ini, f_fin, pasos, r_sensora), r_sensora)
    except ValueError as error:
        messagebox.showerror('Calibración', str(error))
        return
    tabla_cal.delete(*tabla_cal.get_children())
    btn_calibrar.config(text='Calibrando...')
    lbl_estado_cal.config(text='Adquiriendo fase y ganancia con la resistencia conocida...', fg='blue')
    _iniciar_tarea(
        lambda reporte: medidor_backend.calibrar_barrido(f_ini, f_fin, pasos, r_sensora, r_referencia, progreso=reporte, abierto=_abierto),
        mostrar_calibracion, progreso_calibracion,
    )


def mostrar_calibracion(res):
    global _calibracion
    if not res['exito']:
        lbl_estado_cal.config(text=res['error'] + ' Se conserva la calibración anterior, si existe.', fg='red')
        messagebox.showerror('Calibración', res['error'])
        return
    perfil = res['calibracion']
    try:
        ajustes.guardar(perfil)
    except (OSError, ValueError) as error:
        lbl_estado_cal.config(text=f'No se pudo guardar la calibración: {error}. Se conserva la anterior.', fg='red')
        messagebox.showerror('Calibración', str(error))
        return
    _calibracion = perfil
    usar_calibracion.set(True)
    actualizar_estado_calibracion()
    lbl_estado_cal.config(text=f"Calibración guardada y activada: {len(perfil['puntos'])} puntos. Reemplazá la resistencia conocida por Zx para medir.", fg='green')


def ver_curvas_calibracion():
    if _calibracion is None:
        return
    puntos = _calibracion['puntos']
    frecuencias = [p['frecuencia'] for p in puntos]
    _graficar('Calibración: fase', 'Corrección de fase medida', frecuencias, [p['correccion_fase'] for p in puntos], 'Corrección (°)', 'blue')
    _graficar('Calibración: ganancia', 'Ganancia del amplificador medida', frecuencias, [p['ganancia'] for p in puntos], 'Ganancia (V/V)', 'green')
    plt.show(block=False)


def cargar_calibracion_guardada():
    global _calibracion
    try:
        _calibracion = ajustes.cargar()
    except (OSError, ValueError, TypeError, KeyError) as error:
        lbl_estado_cal.config(text=f'Calibración guardada inválida: {error}', fg='red')
        _calibracion = None
        usar_calibracion.set(False)
    if _calibracion is not None:
        for punto in _calibracion['puntos']:
            tabla_cal.insert('', 'end', values=_fila_calibracion(punto))
        usar_calibracion.set(_calibracion['version'] == 2)
        mensaje = ('Calibración guardada cargada. Verificá R1 y las conexiones.' if _calibracion['version'] == 2
                   else 'Perfil anterior sin circuito abierto: desactivado. Repetí los dos pasos para compensar la señal residual.')
        lbl_estado_cal.config(text=mensaje, fg='green' if _calibracion['version'] == 2 else '#a05200')
    actualizar_estado_calibracion()
    _actualizar_botones()

root = tk.Tk()
root.title("Analizador de Impedancias Automático")
root.geometry("840x760")
root.minsize(780, 720)
style = ttk.Style(); style.theme_use("clam")

frame_config = tk.LabelFrame(root, text="Configuración de Hardware", font=("Arial", 10, "bold"), padx=10, pady=5)
frame_config.pack(fill="x", padx=10, pady=5)

frame_modo = tk.Frame(frame_config)
frame_modo.pack(fill='x', pady=(0, 5))
tk.Label(frame_modo, text='Modo de medición:').pack(side='left')
modo_medicion = tk.StringVar(value='Actual')
combo_modo = ttk.Combobox(frame_modo, textvariable=modo_medicion, values=['Actual', 'Original'], state='readonly', width=12)
combo_modo.pack(side='left', padx=10)
combo_modo.bind('<<ComboboxSelected>>', cambiar_modo)

frame_resistencia = tk.Frame(frame_config)
frame_resistencia.pack(fill='x')
tk.Label(frame_resistencia, text="Resistencia Sensora (R1):").pack(side="left")
combo_r = ttk.Combobox(frame_resistencia, values=["10 Ω", "100 Ω", "1 kΩ", "10 kΩ", "100 kΩ"], state="readonly", width=10)
combo_r.current(0)
combo_r.pack(side="left", padx=10)
combo_r.bind('<<ComboboxSelected>>', actualizar_estado_calibracion)
usar_calibracion = tk.BooleanVar(value=False)
chk_calibracion = ttk.Checkbutton(frame_resistencia, text='Aplicar calibración', variable=usar_calibracion, command=actualizar_estado_calibracion, state='disabled')
chk_calibracion.pack(side='left', padx=10)
lbl_calibracion_uso = tk.Label(frame_config, text='', anchor='w', justify='left', wraplength=780)
lbl_calibracion_uso.pack(fill='x', pady=(4, 0))

lbl_equipos = tk.Label(frame_config, text='Equipos sin consultar. Pulsá «Actualizar equipos».', anchor='w',
                      justify='left', wraplength=690)
lbl_equipos.pack(fill='x', pady=(8, 4))
frame_usb = tk.Frame(frame_config)
frame_usb.pack(fill='x', pady=(0, 5))
btn_actualizar_equipos = ttk.Button(frame_usb, text='Actualizar equipos', command=actualizar_equipos)
btn_actualizar_equipos.pack(side='left')
btn_permisos = ttk.Button(frame_usb, text='Habilitar acceso USB', command=ejecutar_permisos, state='disabled')
btn_permisos.pack(side='left', padx=10)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=5)

tab_simple = tk.Frame(notebook)
notebook.add(tab_simple, text="Medición Simple")

btn_medir = tk.Button(tab_simple, text="Medición Simple", font=("Arial", 12, "bold"), bg="#0052cc", fg="white", command=ejecutar_medicion)
btn_medir.pack(pady=10)
lbl_estado = tk.Label(tab_simple, text="Listo.", font=("Arial", 10, "italic"), wraplength=780); lbl_estado.pack()

frame_datos = tk.Frame(tab_simple); frame_datos.pack(fill="x", pady=10)
frame_crudos = tk.LabelFrame(frame_datos, text="Crudos"); frame_crudos.pack(side="left", fill="both", expand=True, padx=5)
frame_imp = tk.LabelFrame(frame_datos, text="Impedancia"); frame_imp.pack(side="right", fill="both", expand=True, padx=5)

tk.Label(frame_crudos, text="V I_OUT:").grid(row=0, column=0, sticky="e"); lbl_v_i = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_v_i.grid(row=0, column=1)
tk.Label(frame_crudos, text="V RMS:").grid(row=1, column=0, sticky="e"); lbl_v_rms = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_v_rms.grid(row=1, column=1)
tk.Label(frame_crudos, text="Frec:").grid(row=2, column=0, sticky="e"); lbl_frec = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_frec.grid(row=2, column=1)
tk.Label(frame_crudos, text="Fase corregida:").grid(row=3, column=0, sticky="e"); lbl_fase = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_fase.grid(row=3, column=1)

tk.Label(frame_imp, text="I RMS:").grid(row=0, column=0, sticky="e"); lbl_i_rms = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_i_rms.grid(row=0, column=1)
tk.Label(frame_imp, text="|Z|:").grid(row=1, column=0, sticky="e"); lbl_z = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_z.grid(row=1, column=1)
tk.Label(frame_imp, text="ESR:").grid(row=2, column=0, sticky="e"); lbl_esr = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_esr.grid(row=2, column=1)
tk.Label(frame_imp, text="Xs:").grid(row=3, column=0, sticky="e"); lbl_xs = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_xs.grid(row=3, column=1)
tk.Label(frame_imp, text='Ganancia aplicada:').grid(row=4, column=0, sticky='e'); lbl_ganancia = tk.Label(frame_imp, text='---', font=('Arial', 10, 'bold')); lbl_ganancia.grid(row=4, column=1)

frame_resultado = tk.Frame(tab_simple); frame_resultado.pack(fill="both", expand=True)
lbl_tipo_final = tk.Label(frame_resultado, text="---", font=("Arial", 14, "bold")); lbl_tipo_final.pack()
lbl_valor_final = tk.Label(frame_resultado, text="---", font=("Arial", 28, "bold")); lbl_valor_final.pack()
lbl_factor_final = tk.Label(frame_resultado, text="---", font=("Arial", 12)); lbl_factor_final.pack()

tab_barrido = tk.Frame(notebook)
notebook.add(tab_barrido, text="Barrido de Frecuencia (Automático)")

frame_b = tk.Frame(tab_barrido, pady=20); frame_b.pack()
tk.Label(frame_b, text="Frecuencia Inicial (Hz):").grid(row=0, column=0, pady=5)
ent_f_ini = tk.Entry(frame_b); ent_f_ini.insert(0, "1000"); ent_f_ini.grid(row=0, column=1)
tk.Label(frame_b, text="Frecuencia Final (Hz):").grid(row=1, column=0, pady=5)
ent_f_fin = tk.Entry(frame_b); ent_f_fin.insert(0, "10000"); ent_f_fin.grid(row=1, column=1)
tk.Label(frame_b, text="Cantidad de Pasos:").grid(row=2, column=0, pady=5)
ent_pasos = tk.Entry(frame_b); ent_pasos.insert(0, "10"); ent_pasos.grid(row=2, column=1)

btn_barrido = tk.Button(tab_barrido, text="Iniciar Barrido", font=("Arial", 12, "bold"), bg="#cc0000", fg="white", command=ejecutar_barrido)
btn_barrido.pack(pady=20)

tab_cal = tk.Frame(notebook)
notebook.add(tab_cal, text='Calibración')
tk.Label(tab_cal, text='1. Retirá Zx y medí el circuito abierto. 2. Colocá una resistencia conocida y medila para guardar la calibración. Mantené R1 y las sondas: CH1 en I_OUT, CH2 en V_OUT. Usá señal senoidal.', wraplength=770, justify='left').pack(fill='x', padx=10, pady=8)
frame_cal = tk.Frame(tab_cal)
frame_cal.pack(pady=4)
entradas_cal = []
for fila, (texto, valor) in enumerate((('Resistencia conocida (Ω):', '1800'), ('Frecuencia inicial (Hz):', '1000'), ('Frecuencia final (Hz):', '10000'), ('Cantidad de puntos:', '10'))):
    tk.Label(frame_cal, text=texto).grid(row=fila, column=0, sticky='e', padx=6, pady=3)
    entrada = ttk.Entry(frame_cal, width=16)
    entrada.insert(0, valor)
    entrada.grid(row=fila, column=1, pady=3)
    entradas_cal.append(entrada)
ent_r_cal, ent_cal_ini, ent_cal_fin, ent_cal_pasos = entradas_cal
frame_acciones_cal = tk.Frame(tab_cal)
frame_acciones_cal.pack(pady=5)
btn_abierto = ttk.Button(frame_acciones_cal, text='1. Medir circuito abierto', command=ejecutar_abierto)
btn_abierto.pack(side='left', padx=5)
btn_calibrar = ttk.Button(frame_acciones_cal, text='2. Medir resistencia y guardar', command=ejecutar_calibracion)
btn_calibrar.pack(side='left', padx=5)
btn_curvas_cal = ttk.Button(frame_acciones_cal, text='Ver curvas', command=ver_curvas_calibracion, state='disabled')
btn_curvas_cal.pack(side='left', padx=5)
lbl_estado_cal = tk.Label(tab_cal, text='Sin calibración guardada.', wraplength=770, justify='left')
lbl_estado_cal.pack(fill='x', padx=10, pady=5)
frame_tabla_cal = tk.Frame(tab_cal)
frame_tabla_cal.pack(fill='both', expand=True, padx=10, pady=5)
columnas_cal = ('objetivo', 'frecuencia', 'v_i', 'v_r', 'fase', 'correccion', 'ganancia')
tabla_cal = ttk.Treeview(frame_tabla_cal, columns=columnas_cal, show='headings', height=6)
for columna, titulo in zip(columnas_cal, ('Objetivo Hz', 'Medida Hz', 'I_OUT V', 'V_OUT V', 'Fase medida °', 'Corrección °', 'Ganancia V/V')):
    tabla_cal.heading(columna, text=titulo)
    tabla_cal.column(columna, width=100, minwidth=70, anchor='center')
scroll_cal = ttk.Scrollbar(frame_tabla_cal, orient='vertical', command=tabla_cal.yview)
tabla_cal.configure(yscrollcommand=scroll_cal.set)
scroll_cal.pack(side='right', fill='y')
tabla_cal.pack(side='left', fill='both', expand=True)

cargar_calibracion_guardada()
root.mainloop()
