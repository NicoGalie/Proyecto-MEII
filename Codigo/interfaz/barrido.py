"""Barrido con tabla visible durante la adquisición y al cancelar."""

from tkinter import ttk

from interfaz.comunes import bloquear, entrada, rango
from interfaz.tablas import TablaMediciones


class PanelBarrido(ttk.Frame):
    def __init__(self, padre, iniciar, cancelar):
        super().__init__(padre, padding=10)
        campos = ttk.Frame(self)
        campos.pack(anchor='w')
        self.inicio = entrada(campos, 'Inicial (Hz):', 1000, 0)
        self.fin = entrada(campos, 'Final (Hz):', 10000, 0, 2)
        self.cantidad = entrada(campos, 'Puntos:', 10, 0, 4, 6)
        acciones = ttk.Frame(self)
        acciones.pack(fill='x', pady=8)
        self.iniciar = ttk.Button(acciones, text='Iniciar barrido', command=iniciar)
        self.iniciar.pack(side='left')
        self.cancelar = ttk.Button(
            acciones, text='Cancelar barrido', command=cancelar, state='disabled'
        )
        self.cancelar.pack(side='left', padx=8)
        self.resumen = ttk.Label(acciones, text='Los resultados se conservan al cancelar.')
        self.resumen.pack(side='left', padx=8)
        self.tabla = TablaMediciones(self)
        self.tabla.pack(fill='both', expand=True)

    def parametros(self):
        return rango(self.inicio, self.fin, self.cantidad)

    def bloquear(self, ocupado, activo=False):
        bloquear([self.inicio, self.fin, self.cantidad, self.iniciar], ocupado)
        self.cancelar.configure(state='normal' if ocupado and activo else 'disabled')

    def mostrar(self, resultado):
        self.tabla.mostrar(resultado.filas)
        validas = sum(f.medicion is not None for f in resultado.filas)
        nominales = sum(
            f.medicion is not None and not f.medicion.ajuste.aplicada for f in resultado.filas
        )
        estado = 'Cancelado' if resultado.cancelado else 'Finalizado'
        self.resumen.configure(
            text=f'{estado}: {validas} válidas; {nominales} con parámetros nominales.'
        )
