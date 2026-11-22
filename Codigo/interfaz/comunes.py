"""Campos numéricos y formato de valores para los paneles."""

from tkinter import ttk

from configuracion import positivo


def entrada(marco, texto, valor, fila, columna=0, ancho=12):
    ttk.Label(marco, text=texto).grid(row=fila, column=columna, sticky='w', padx=5, pady=4)
    campo = ttk.Entry(marco, width=ancho)
    campo.insert(0, str(valor))
    campo.grid(row=fila, column=columna + 1, sticky='w', padx=5, pady=4)
    return campo


def numero(campo, nombre):
    try:
        return positivo(float(campo.get().replace(',', '.')), nombre)
    except ValueError:
        raise ValueError(f'{nombre}: ingresá un número positivo y finito.') from None


def rango(inicio, fin, cantidad):
    from operaciones import frecuencias

    a, b = numero(inicio, 'Frecuencia inicial'), numero(fin, 'Frecuencia final')
    try:
        n = int(cantidad.get())
    except ValueError:
        raise ValueError('La cantidad de puntos debe ser un entero.') from None
    frecuencias(a, b, n)
    return a, b, n


def valor_componente(medicion):
    valor = medicion.valor
    if medicion.tipo == 'RESISTENCIA':
        return f'{valor:.7g} Ω'
    escalas = (
        [(1e-3, 'mH'), (1e-6, 'µH'), (1e-9, 'nH')]
        if medicion.tipo == 'INDUCTOR'
        else [(1e-6, 'µF'), (1e-9, 'nF'), (1e-12, 'pF')]
    )
    for escala, unidad in escalas:
        if valor >= escala:
            return f'{valor / escala:.7g} {unidad}'
    return f'{valor:.7g} ' + ('H' if medicion.tipo == 'INDUCTOR' else 'F')


def factor(medicion):
    if medicion.tipo == 'RESISTENCIA':
        return '—'
    nombre = 'Q' if medicion.tipo == 'INDUCTOR' else 'D'
    return f'{nombre}: {medicion.factor:.7g}' if medicion.factor is not None else f'{nombre}: ∞'


def bloquear(campos, ocupado):
    for campo in campos:
        campo.configure(state='disabled' if ocupado else 'normal')
