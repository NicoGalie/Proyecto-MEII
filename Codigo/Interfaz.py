import tkinter as tk
from tkinter import ttk, messagebox
import medidor_backend

# --- SOLUCIÓN AL ERROR DE GRÁFICOS EN LINUX ---
import matplotlib
matplotlib.use('TkAgg')  # Obligamos a usar el motor de ventanas
import matplotlib.pyplot as plt
# ----------------------------------------------

def _obtener_resistencia():
    valor_texto = combo_r.get()
    multiplicador = 1.0
    if "k" in valor_texto:
        multiplicador = 1000.0
    numero = float(valor_texto.replace("kΩ", "").replace("Ω", "").strip())
    return numero * multiplicador

def ejecutar_medicion():
    btn_medir.config(state="disabled", text="Midiendo...")
    lbl_estado.config(text="Adquiriendo datos...", fg="blue")
    root.update()

    r_sensora = _obtener_resistencia()
    res = medidor_backend.medicion_simple(r_sensora)

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
        lbl_tipo_final.config(text=d["tipo"], fg="green")
        lbl_valor_final.config(text=d["valor_final"])
        lbl_factor_final.config(text=d["factor_str"])
        lbl_estado.config(text=f"Lectura exitosa (Rs = {r_sensora} Ω)", fg="green")
    else:
        lbl_estado.config(text=res["error"], fg="red")
        
    btn_medir.config(state="normal", text="Medición Simple")

def ejecutar_barrido():
    try:
        f_ini = float(ent_f_ini.get())
        f_fin = float(ent_f_fin.get())
        pasos = int(ent_pasos.get())
        r_sensora = _obtener_resistencia()
    except ValueError:
        messagebox.showerror("Error", "Los parámetros de barrido deben ser numéricos.")
        return

    btn_barrido.config(state="disabled", text="Barriendo (Toma tiempo)...")
    root.update()

    res = medidor_backend.barrido_automatico(f_ini, f_fin, pasos, r_sensora)
    
    if res["exito"]:
        lbl_estado.config(text="Barrido finalizado. Abriendo gráficos.", fg="green")
        
        plt.figure("Resistencia Serie Equivalente (ESR)")
        plt.title("ESR vs Frecuencia")
        plt.plot(res["frec_medida"], res["esr"], marker='o', color='red')
        plt.xlabel("Frecuencia (Hz)")
        plt.ylabel("ESR (Ω)")
        plt.grid(True)
        
        plt.figure("Factor de Mérito")
        plt.title(f"Factor {'D' if res['tipo'] == 'CAPACITOR' else 'Q'} vs Frecuencia")
        plt.plot(res["frec_medida"], res["q_d"], marker='s', color='orange')
        plt.xlabel("Frecuencia (Hz)")
        plt.ylabel("Factor")
        plt.grid(True)
        
        plt.figure("Magnitud Reactiva")
        plt.title(f"{res['tipo']} vs Frecuencia")
        plt.plot(res["frec_medida"], res["cap_ind"], marker='^', color='blue')
        plt.xlabel("Frecuencia (Hz)")
        plt.ylabel("Faradios (F)" if res["tipo"] == "CAPACITOR" else "Henrios (H)")
        plt.grid(True)
        
        if res.get("errores_log"):
            cant_errores = len(res["errores_log"])
            messagebox.showwarning("Advertencia", f"Se saltaron {cant_errores} puntos por error de lectura.")

        plt.show()
    else:
        messagebox.showerror("Error de Hardware", res["error"])
        
    btn_barrido.config(state="normal", text="Iniciar Barrido")

root = tk.Tk()
root.title("Analizador de Impedancias Automático")
root.geometry("650x550")
style = ttk.Style(); style.theme_use("clam")

frame_config = tk.LabelFrame(root, text="Configuración de Hardware", font=("Arial", 10, "bold"), padx=10, pady=5)
frame_config.pack(fill="x", padx=10, pady=5)

tk.Label(frame_config, text="Resistencia Sensora (R1):").pack(side="left")
combo_r = ttk.Combobox(frame_config, values=["10 Ω", "100 Ω", "1 kΩ", "10 kΩ", "100 kΩ"], state="readonly", width=10)
combo_r.current(0)
combo_r.pack(side="left", padx=10)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=5)

tab_simple = tk.Frame(notebook)
notebook.add(tab_simple, text="Medición Simple")

btn_medir = tk.Button(tab_simple, text="Medición Simple", font=("Arial", 12, "bold"), bg="#0052cc", fg="white", command=ejecutar_medicion)
btn_medir.pack(pady=10)
lbl_estado = tk.Label(tab_simple, text="Listo.", font=("Arial", 10, "italic")); lbl_estado.pack()

frame_datos = tk.Frame(tab_simple); frame_datos.pack(fill="x", pady=10)
frame_crudos = tk.LabelFrame(frame_datos, text="Crudos"); frame_crudos.pack(side="left", fill="both", expand=True, padx=5)
frame_imp = tk.LabelFrame(frame_datos, text="Impedancia"); frame_imp.pack(side="right", fill="both", expand=True, padx=5)

tk.Label(frame_crudos, text="V I_OUT:").grid(row=0, column=0, sticky="e"); lbl_v_i = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_v_i.grid(row=0, column=1)
tk.Label(frame_crudos, text="V RMS:").grid(row=1, column=0, sticky="e"); lbl_v_rms = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_v_rms.grid(row=1, column=1)
tk.Label(frame_crudos, text="Frec:").grid(row=2, column=0, sticky="e"); lbl_frec = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_frec.grid(row=2, column=1)
tk.Label(frame_crudos, text="Fase:").grid(row=3, column=0, sticky="e"); lbl_fase = tk.Label(frame_crudos, text="---", font=("Arial", 10, "bold")); lbl_fase.grid(row=3, column=1)

tk.Label(frame_imp, text="I RMS:").grid(row=0, column=0, sticky="e"); lbl_i_rms = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_i_rms.grid(row=0, column=1)
tk.Label(frame_imp, text="|Z|:").grid(row=1, column=0, sticky="e"); lbl_z = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_z.grid(row=1, column=1)
tk.Label(frame_imp, text="ESR:").grid(row=2, column=0, sticky="e"); lbl_esr = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_esr.grid(row=2, column=1)
tk.Label(frame_imp, text="Xs:").grid(row=3, column=0, sticky="e"); lbl_xs = tk.Label(frame_imp, text="---", font=("Arial", 10, "bold")); lbl_xs.grid(row=3, column=1)

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

root.mainloop()