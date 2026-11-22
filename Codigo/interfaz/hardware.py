"""Configuración física y detección USB, actualizada solo por el usuario."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from configuracion import Configuracion, leer_rg

from interfaz.comunes import bloquear, entrada, numero


class PanelHardware(ttk.LabelFrame):
    def __init__(self, padre, config, usar, actualizar, permisos, guardar):
        super().__init__(padre, text='Configuración de hardware', padding=8)
        self.equipos = []
        self.columnconfigure(0, weight=1)
        controles = ttk.Frame(self)
        self.controles = controles
        controles.grid(row=0, column=0, sticky='nw', padx=(0, 12))
        campos = ttk.Frame(controles)
        campos.pack(fill='x')
        self.rs = entrada(campos, 'Rs (Ω):', config.rs, 0, ancho=10)
        self.rg = entrada(
            campos,
            'RG (Ω o «abierto»):',
            'abierto' if config.rg_ohm is None else config.rg_ohm,
            1,
            0,
            ancho=10,
        )
        opciones = ttk.Frame(controles)
        opciones.pack(fill='x', pady=(3, 4))
        self.guardar = ttk.Button(opciones, text='Guardar configuración', command=guardar)
        self.guardar.pack(side='left', padx=(5, 8))
        self.chk_cal = ttk.Checkbutton(opciones, text='Usar calibración', variable=usar)
        self.chk_cal.pack(side='left')
        self.ganancia = ttk.Label(
            controles, text=f'Ganancia nominal = {config.ganancia:g}; fase nominal = 0°'
        )
        self.ganancia.pack(anchor='w', pady=3)
        self.identificacion = ttk.Label(
            controles, text='Equipos sin consultar. Pulsá «Actualizar equipos».', wraplength=420
        )
        self.identificacion.pack(anchor='w', pady=5)
        acciones = ttk.Frame(controles)
        acciones.pack(fill='x')
        self.actualizar = ttk.Button(acciones, text='Actualizar equipos', command=actualizar)
        self.actualizar.pack(side='left')
        self.permisos = ttk.Button(
            acciones, text='Habilitar acceso USB', command=permisos, state='disabled'
        )
        self.permisos.pack(side='left', padx=8)

        ruta_circuito = Path(__file__).resolve().parents[2] / 'recursos' / 'circuito-lc.png'
        with Image.open(ruta_circuito) as imagen:
            self.circuito_fuente = imagen.convert('RGB')
        self.circuito_original = tk.PhotoImage(master=self, file=str(ruta_circuito))
        self.circuito_imagen = self.circuito_original.subsample(3)
        self.circuito_tamano = (self.circuito_imagen.width(), self.circuito_imagen.height())
        esquema = ttk.Frame(self)
        esquema.grid(row=0, column=1, sticky='nsew')
        self.circuito = ttk.Label(esquema, image=self.circuito_imagen, cursor='hand2')
        self.circuito.pack(fill='both', expand=True)
        self.circuito.bind('<Button-1>', self.ampliar_circuito)
        self.ventana_circuito = None
        self.bind('<Configure>', self.ajustar_circuito)
        controles.bind('<Configure>', self.ajustar_circuito)

    def ajustar_circuito(self, evento=None):
        if self.winfo_width() <= 1:
            return
        disponible = max(1, self.winfo_width() - self.controles.winfo_reqwidth() - 40)
        alto = self.controles.winfo_reqheight()
        ancho_original, alto_original = self.circuito_fuente.size
        escala = min(disponible / ancho_original, alto / alto_original, 1)
        tamano = (max(1, round(ancho_original * escala)), max(1, round(alto_original * escala)))
        if tamano != self.circuito_tamano:
            self.circuito_tamano = tamano
            imagen = self.circuito_fuente.resize(tamano, Image.Resampling.LANCZOS)
            self.circuito_imagen = ImageTk.PhotoImage(imagen, master=self)
            self.circuito.configure(image=self.circuito_imagen)

    def ampliar_circuito(self, evento=None):
        if self.ventana_circuito is not None and self.ventana_circuito.winfo_exists():
            self.ventana_circuito.lift()
            return
        ventana = tk.Toplevel(self)
        self.ventana_circuito = ventana
        ventana.title('Circuito — Analizador de Impedancias LC Complejas')
        ventana.transient(self.winfo_toplevel())
        # Seleccionar una escala entera que permita ver el esquema completo.
        ancho = max(1, ventana.winfo_screenwidth() - 100)
        alto = max(1, ventana.winfo_screenheight() - 150)
        escala = max(
            1,
            (self.circuito_original.width() + ancho - 1) // ancho,
            (self.circuito_original.height() + alto - 1) // alto,
        )
        self.circuito_ampliado = self.circuito_original.subsample(escala)
        ttk.Label(ventana, image=self.circuito_ampliado).pack(padx=12, pady=12)
        ventana.resizable(False, False)
        ventana.bind('<Escape>', lambda evento: ventana.destroy())

    def configuracion(self):
        return Configuracion(numero(self.rs, 'Rs'), leer_rg(self.rg.get()))

    def bloquear(self, ocupado):
        bloquear([self.rs, self.rg, self.guardar, self.chk_cal, self.actualizar], ocupado)
        faltan = any(e['estado'] == 'sin_permisos' for e in self.equipos)
        self.permisos.configure(state='normal' if faltan and not ocupado else 'disabled')

    def mostrar_equipos(self, resultado):
        if not resultado['exito']:
            self.equipos = []
            self.identificacion.configure(text=resultado['error'])
            return
        self.equipos = resultado['equipos']
        estados = dict(
            conectado='listo',
            sin_permisos='requiere permiso USB',
            sin_respuesta='conectado, sin respuesta',
            pendiente_actualizacion='permiso configurado; pulsá Actualizar equipos',
        )
        texto = '\n'.join(
            f'• {e["nombre"]} (serie {e["serie"]}) — {estados[e["estado"]]}' for e in self.equipos
        )
        self.identificacion.configure(text=texto or 'Equipos conectados: ninguno.')
