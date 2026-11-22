"""Ejemplo para estudiar, sin interfaz y sin conectar instrumentos.

Se inventan solo las lecturas del osciloscopio. La configuración y los
cálculos son los mismos que utiliza el programa real.

Ejecutar desde la carpeta del proyecto:
    .venv/bin/python ejemplos/medicion_paso_a_paso.py
"""

import sys
from pathlib import Path

# Permitir importar los módulos reales guardados en Codigo/.
carpeta_codigo = Path(__file__).resolve().parents[1] / 'Codigo'
sys.path.insert(0, str(carpeta_codigo))

from calculos import calcular
from configuracion import Configuracion
from modelos import Lectura


def main():
    # PASO 1. Definir los valores físicos que el usuario ingresa en pantalla.
    configuracion = Configuracion(rs=10.0, rg_ohm=12500.0)
    print(f'1. Rs = {configuracion.rs:g} Ω; RG = {configuracion.rg_ohm:g} Ω')
    print(f'   Ganancia nominal = 1 + 50000/RG = {configuracion.ganancia:g}')

    # PASO 2. Simular las cuatro lecturas que normalmente entrega el osciloscopio.
    lectura = Lectura(vo=0.050, vz=0.100, frecuencia=5000.0, fase=0.0)
    print(f'2. Vo = {lectura.vo:g} V RMS; VZ = {lectura.vz:g} V RMS')
    print(f'   Frecuencia medida = {lectura.frecuencia:g} Hz; fase = {lectura.fase:g}°')

    # PASO 3. Llamar al cálculo real, sin perfil de calibración: usa G nominal.
    resultado = calcular(lectura, configuracion)

    # PASO 4. Leer los resultados en el mismo orden que las fórmulas físicas.
    print(f'3. Corriente I = Vo/(G·Rs) = {resultado.corriente * 1000:g} mA')
    print(f'4. Módulo |Z| = VZ/I = {abs(resultado.z):g} Ω')
    print(f'5. ESR = |Z|·cos(fase) = {resultado.z.real:g} Ω')
    print(f'   Xs = |Z|·sin(fase) = {resultado.z.imag:g} Ω')
    print(f'6. Tipo = {resultado.tipo}; valor = {resultado.valor:g} Ω')
    print(f'   Corrección utilizada: {resultado.ajuste.motivo}')

    # Se devuelve para poder comprobar el ejemplo sin repetir sus fórmulas.
    return resultado


if __name__ == '__main__':
    main()
