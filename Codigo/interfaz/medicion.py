"""Medición simple a la frecuencia elegida, con promedio opcional."""

import cmath
import math
import tkinter as tk
from tkinter import ttk

from osciloscopios import validar_tiempo_promedio

from interfaz.comunes import bloquear, entrada, factor, numero, valor_componente


class PanelMedicion(ttk.Frame):
    def __init__(self, padre, medir):
        super().__init__(padre, padding=10)
        campos = ttk.Frame(self)
        campos.pack(anchor='w')
        self.frecuencia = entrada(campos, 'Frecuencia (Hz):', 5000, 0)
        self.promediar = tk.BooleanVar(value=False)
        self.chk_promedio = ttk.Checkbutton(campos, text='Promediar señal', variable=self.promediar)
        self.chk_promedio.grid(row=0, column=2, padx=8)
        self.segundos = entrada(campos, 'Tiempo (s):', 5, 0, 3, 7)
        self.medir = ttk.Button(campos, text='Medir', command=medir)
        self.medir.grid(row=0, column=5, padx=8)
        ttk.Label(
            self,
            text='Se programa el generador; el cálculo utiliza la frecuencia medida por el osciloscopio.',
        ).pack(anchor='w', pady=8)
        self.resultado = ttk.Label(self, text='Sin medición.', font=('Arial', 22, 'bold'))
        self.resultado.pack(anchor='w', pady=8)
        self.datos = ttk.Label(self, text='', justify='left')
        self.datos.pack(anchor='w', pady=8)
        self.correccion = ttk.Label(self, text='', wraplength=1050)
        self.correccion.pack(anchor='w')

    def parametros(self):
        f = numero(self.frecuencia, 'Frecuencia')
        segundos = (
            validar_tiempo_promedio(numero(self.segundos, 'Tiempo'))
            if self.promediar.get()
            else None
        )
        return f, segundos

    def bloquear(self, ocupado):
        bloquear([self.frecuencia, self.chk_promedio, self.segundos, self.medir], ocupado)

    def limpiar(self):
        self.resultado.configure(text='Sin medición válida.')
        self.datos.configure(text='')
        self.correccion.configure(text='')

    def mostrar(self, m):
        self.resultado.configure(text=f'{m.tipo}: {valor_componente(m)}')
        self.datos.configure(
            text=(
                f'Programada: {m.objetivo:.8g} Hz     Medida: {m.lectura.frecuencia:.8g} Hz\n'
                f'Vo CH1: {m.lectura.vo:.8g} V RMS     VZ CH2: {m.lectura.vz:.8g} V RMS\n'
                f'Corriente: {m.corriente * 1000:.8g} mA     |Z|: {abs(m.z):.8g} Ω\n'
                f'ESR: {m.z.real:.8g} Ω     Xs: {m.z.imag:.8g} Ω\n'
                f'Fase: {math.degrees(cmath.phase(m.z)):.8g}°     {factor(m)}\n'
                f'Ganancia: {m.ajuste.ganancia:.8g}     Intentos: {m.intentos}'
            )
        )
        self.correccion.configure(
            text=m.ajuste.motivo
            + (f'. Promedio: {m.promedio["tiempo_promedio_s"]:g} s' if m.promedio else '')
        )
