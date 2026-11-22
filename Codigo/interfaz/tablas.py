"""Tablas desplazables y copia al portapapeles; sin gráficos."""

import cmath
import math
from tkinter import font, ttk

from interfaz.comunes import factor, valor_componente

COLUMNAS_MEDICION = (
    ('objetivo', 'Programada (Hz)', 160),
    ('medida', 'Medida (Hz)', 140),
    ('tipo', 'Tipo', 150),
    ('valor', 'Valor del componente', 220),
    ('esr', 'ESR (Ω)', 140),
    ('xs', 'Xs (Ω)', 140),
    ('z', '|Z| (Ω)', 140),
    ('fase', 'Fase (°)', 140),
    ('factor', 'D / Q', 150),
    ('vo', 'Vo CH1 RMS (V)', 180),
    ('vz', 'VZ CH2 RMS (V)', 180),
    ('ganancia', 'Ganancia', 140),
    ('calibracion', 'Calibración', 160),
    ('motivo', 'Corrección utilizada', 480),
    ('intentos', 'Intentos', 100),
    ('estado', 'Estado / error', 450),
)

COLUMNAS_CALIBRACION = tuple(
    (nombre, titulo, 150)
    for nombre, titulo in (
        ('frecuencia_objetivo', 'Programada (Hz)'),
        ('frecuencia', 'Medida (Hz)'),
        ('v_i_out', 'Vo CH1 RMS (V)'),
        ('v_rms', 'VZ CH2 RMS (V)'),
        ('fase_cruda', 'Fase medida (°)'),
        ('correccion_fase', 'Corrección (°)'),
        ('ganancia', 'Ganancia'),
    )
)


def valores_medicion(fila):
    datos = dict(
        objetivo=fila.frecuencia,
        intentos=fila.intentos,
        estado=fila.estado + (': ' + fila.error if fila.error else ''),
    )
    m = fila.medicion
    if m:
        datos.update(
            medida=m.lectura.frecuencia,
            tipo=m.tipo,
            valor=valor_componente(m),
            esr=m.z.real,
            xs=m.z.imag,
            z=abs(m.z),
            fase=math.degrees(cmath.phase(m.z)),
            factor=factor(m),
            vo=m.lectura.vo,
            vz=m.lectura.vz,
            ganancia=m.ajuste.ganancia,
            calibracion='Aplicada' if m.ajuste.aplicada else 'Nominal',
            motivo=m.ajuste.motivo,
        )
    return [formato(datos.get(nombre)) for nombre, _, _ in COLUMNAS_MEDICION]


def formato(valor):
    if valor is None:
        return '—'
    if isinstance(valor, (int, float)):
        return f'{valor:.8g}'
    return str(valor).replace('\t', ' ').replace('\n', ' ')


class Tabla(ttk.Frame):
    def __init__(self, padre, columnas):
        super().__init__(padre)
        self.columnas = columnas
        self.tree = ttk.Treeview(
            self, columns=[c[0] for c in columnas], show='headings', style='Datos.Treeview'
        )
        fuente = font.nametofont('TkHeadingFont')
        for nombre, titulo, ancho in columnas:
            self.tree.heading(nombre, text=titulo)
            self.tree.column(
                nombre,
                width=max(ancho, fuente.measure(titulo) + 24),
                minwidth=70,
                stretch=False,
                anchor='center',
            )
        self.tree.tag_configure('ERROR', foreground='#b00020')
        self.tree.tag_configure('CANCELADO', foreground='#975900')
        self.tree.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        ttk.Button(self, text='Copiar tabla', command=self.copiar).grid(
            row=2, column=0, sticky='w', pady=5
        )
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def limpiar(self):
        self.tree.delete(*self.tree.get_children())

    def agregar(self, valores, estado='OK'):
        fila = self.tree.insert('', 'end', values=valores, tags=(estado,))
        self.tree.see(fila)

    def copiar(self):
        lineas = ['\t'.join(c[1] for c in self.columnas)]
        lineas.extend(
            '\t'.join(self.tree.item(fila, 'values')) for fila in self.tree.get_children()
        )
        self.clipboard_clear()
        self.clipboard_append('\n'.join(lineas))


class TablaMediciones(Tabla):
    def __init__(self, padre):
        super().__init__(padre, COLUMNAS_MEDICION)

    def agregar_fila(self, fila):
        self.agregar(valores_medicion(fila), fila.estado)

    def mostrar(self, filas):
        self.limpiar()
        for fila in filas:
            self.agregar_fila(fila)


class TablaCalibracion(Tabla):
    def __init__(self, padre):
        super().__init__(padre, COLUMNAS_CALIBRACION)

    def agregar_punto(self, punto):
        self.agregar([formato(punto[nombre]) for nombre, _, _ in self.columnas])
