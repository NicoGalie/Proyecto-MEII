"""Adquisición de resistencia conocida, con circuito abierto opcional."""

import tkinter as tk
from tkinter import ttk

from interfaz.comunes import bloquear, entrada, numero, rango
from interfaz.tablas import TablaCalibracion


class PanelCalibracion(ttk.Frame):
    def __init__(self, padre, calibrar, abierto, cancelar):
        super().__init__(padre, padding=10)
        ttk.Label(
            self,
            text='Colocá una resistencia conocida en Zx. Mantené Rs, RG y sondas. La referencia debe comportarse como resistencia en todo el rango.',
            wraplength=1050,
        ).pack(anchor='w')
        campos = ttk.Frame(self)
        campos.pack(anchor='w', pady=5)
        self.referencia = entrada(campos, 'Referencia (Ω):', 10, 0)
        self.inicio = entrada(campos, 'Inicial (Hz):', 1000, 1)
        self.fin = entrada(campos, 'Final (Hz):', 10000, 1, 2)
        self.cantidad = entrada(campos, 'Puntos:', 10, 1, 4, 6)
        acciones = ttk.Frame(self)
        acciones.pack(fill='x', pady=5)
        self.calibrar = ttk.Button(acciones, text='Calibrar con resistencia', command=calibrar)
        self.calibrar.pack(side='left')
        self.abierto = ttk.Button(acciones, text='Medir abierto (opcional)', command=abierto)
        self.abierto.pack(side='left', padx=8)
        self.cancelar = ttk.Button(acciones, text='Cancelar', command=cancelar, state='disabled')
        self.cancelar.pack(side='left')
        self.usar_abierto = tk.BooleanVar(value=False)
        self.chk_abierto = ttk.Checkbutton(
            self,
            text='Compensar residual de circuito abierto (requiere tres capturas estables)',
            variable=self.usar_abierto,
        )
        self.chk_abierto.pack(anchor='w', pady=4)
        self.perfil = ttk.Label(self, text='Sin calibración guardada.', wraplength=1050)
        self.perfil.pack(anchor='w', pady=5)
        self.tabla = TablaCalibracion(self)
        self.tabla.pack(fill='both', expand=True)

    def parametros(self):
        return rango(self.inicio, self.fin, self.cantidad)

    def resistencia(self):
        return numero(self.referencia, 'Resistencia conocida')

    def bloquear(self, ocupado, activo=False):
        bloquear(
            [
                self.referencia,
                self.inicio,
                self.fin,
                self.cantidad,
                self.calibrar,
                self.abierto,
                self.chk_abierto,
            ],
            ocupado,
        )
        self.cancelar.configure(state='normal' if ocupado and activo else 'disabled')

    def mostrar_perfil(self, perfil):
        self.tabla.limpiar()
        if perfil is None:
            self.perfil.configure(text='Sin calibración guardada.')
            return
        puntos = perfil['puntos']
        self.perfil.configure(
            text=f'Guardada: Rs={perfil["r_sensora"]:g} Ω; referencia={perfil["r_referencia"]:g} Ω; {puntos[0]["frecuencia_objetivo"]:g}–{puntos[-1]["frecuencia_objetivo"]:g} Hz.'
        )
        for punto in puntos:
            self.tabla.agregar_punto(punto)
        self.tabla.tree.yview_moveto(0)
