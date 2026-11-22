"""Instrumentos simulados; estas pruebas nunca acceden al USB real."""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
TEK = 'TEKTRONIX,TBS2102B,C022681,1'
UNIT = 'UNI-T,UTD2102,SERIEUNIT,1'
GEN = 'UNI-T,UTG1042X,AWGA224490002,1'


class TekSimulado:
    """Captura binaria cuantizada, con estados de adquisición y transferencia."""

    def __init__(self, fase=-135, truncar=False, recortar=False, fallo_opc=False):
        self.timeout, self.chunk_size = 4000, 20480
        self.valores = {
            'ACQuire:STATE': '1',
            'ACQuire:STOPAfter': 'RUNSTOP',
            'ACQuire:MODe': 'SAMPLE',
            'ACQuire:NUMAVg': '8',
            'DATa:ENCdg': 'SRIBINARY',
            'DATa:WIDth': '1',
            'DATa:STARt': '20',
            'DATa:STOP': '20000',
            'DATa:SOUrce': 'CH2',
            'MEASUrement:IMMed:TYPe': 'PHASE',
            'MEASUrement:IMMed:SOUrce1': 'CH2',
            'MEASUrement:GATing': 'OFF',
            'HORizontal:RECOrdlength': '20000',
        }
        self.originales = self.valores.copy()
        self.fase, self.truncar, self.recortar, self.fallo_opc = fase, truncar, recortar, fallo_opc
        self.comandos, self.descargas = [], []

    def write(self, comando):
        self.comandos.append(comando)
        clave, valor = comando.split(' ', 1)
        self.valores[clave] = (
            {'ON': '1', 'OFF': '0'}.get(valor, valor) if clave == 'ACQuire:STATE' else valor
        )

    def query(self, comando):
        self.comandos.append(comando)
        if comando == '*OPC?':
            if self.fallo_opc:
                raise TimeoutError('sin disparo')
            self.valores['ACQuire:STATE'] = '0'
            return '1'
        if comando == 'MEASUrement:IMMed:VALue?':
            if self.valores['MEASUrement:IMMed:TYPe'] == 'PK2Pk':
                return str(
                    2
                    * np.sqrt(2)
                    * (0.05 if self.valores['MEASUrement:IMMed:SOUrce1'] == 'CH1' else 1)
                )
            return '1001'
        valores = {
            'WFMOutpre:XINcr?': 5 / 1000 / 20000,
            'WFMOutpre:XZEro?': -0.001,
            'WFMOutpre:PT_Off?': 0,
            'WFMOutpre:YOFf?': 0,
            'WFMOutpre:YZEro?': 0,
            'CH2:SCAle?': 1,
        }
        if comando == 'WFMOutpre:YMUlt?':
            return str((0.05 if self.valores['DATa:SOUrce'] == 'CH1' else 1) * np.sqrt(2) / 90)
        if comando in valores:
            return str(valores[comando])
        return self.valores[comando.rstrip('?')]

    def query_binary_values(self, comando, **kwargs):
        assert self.valores['ACQuire:STATE'] == '0', 'canales sin congelar'
        assert kwargs['datatype'] == 'b', 'ancho del ADC incorrecto'
        self.descargas.append((self.valores['DATa:SOUrce'], self.valores['ACQuire:STATE']))
        t = -0.001 + np.arange(20000) * 5 / 1000 / 20000
        fase = 0 if self.valores['DATa:SOUrce'] == 'CH1' else np.radians(self.fase)
        datos = np.round(90 * np.sin(2 * np.pi * 1000 * t + fase))
        if self.recortar:
            datos[0] = 127
        return datos[:-20] if self.truncar else datos


class Reloj:
    def __init__(self):
        self.actual = 0.0

    def monotonic(self):
        return self.actual

    def sleep(self, segundos):
        self.actual += segundos


class TekPromedio(TekSimulado):
    def __init__(self, reloj, ruido=False, sin_capturas=False, **kwargs):
        super().__init__(**kwargs)
        self.reloj, self.ruido, self.sin_capturas = reloj, ruido, sin_capturas
        self.inicio, self.capturas = None, 0
        self.valores.update(
            {
                'MEASUrement:IMMed:SOUrce2': 'CH1',
                'TRIGger:A:TYPe': 'EDGE',
                'TRIGger:A:EDGE:SOUrce': 'CH1',
                'TRIGger:A:MODe': 'AUTO',
            }
        )
        self.originales = self.valores.copy()

    def contador(self):
        if self.sin_capturas:
            return 4000
        if self.valores['ACQuire:STATE'] == '1' and self.inicio is not None:
            return 4000 + int((self.reloj.actual - self.inicio) * 50)
        return 4000 + self.capturas

    def write(self, cmd):
        if cmd == 'ACQuire:STATE OFF' and self.inicio is not None:
            self.capturas = self.contador() - 4000
        super().write(cmd)
        if cmd == 'ACQuire:STATE ON':
            self.inicio = self.reloj.actual

    def query(self, cmd):
        if cmd == 'ACQuire:NUMACq?':
            self.comandos.append(cmd)
            return str(self.contador())
        if cmd == 'MEASUrement:IMMed:VALue?':
            tipo = self.valores['MEASUrement:IMMed:TYPe']
            if tipo == 'RMS':
                return '.05' if self.valores['MEASUrement:IMMed:SOUrce1'] == 'CH1' else '1'
            if tipo == 'PHAse':
                return str(self.fase)
        return super().query(cmd)

    def query_binary_values(self, comando, **kwargs):
        datos = super().query_binary_values(comando, **kwargs)
        if self.ruido and self.valores['DATa:SOUrce'] == 'CH1':
            # Simulación de ruido no correlacionado reducido por el promedio
            # de formas de onda del instrumento, antes de descargar el registro.
            n = self.capturas if self.capturas else int(self.valores['ACQuire:NUMAVg'])
            rms = 0.03 / math.sqrt(min(n, 512))
            mul = 0.05 * math.sqrt(2) / 90
            datos = datos + np.random.default_rng(8).normal(0, rms / mul, len(datos))
        return datos


import calibracion
from cancelacion import Cancelacion
from configuracion import Configuracion, normalizar_fase
from modelos import Lectura

IDENTIDAD = dict(fabricante='TEKTRONIX', modelo='TBS2102B', serie='C022681')


class ControlReloj(Cancelacion):
    def __init__(self, reloj, cancelar_en=None):
        super().__init__()
        self.reloj, self.cancelar_en = reloj, cancelar_en

    def esperar(self, segundos):
        self.comprobar()
        self.reloj.sleep(segundos)
        if self.cancelar_en is not None and self.reloj.actual >= self.cancelar_en:
            self.cancelar()
        self.comprobar()


def lectura_compleja(m, f):
    return Lectura(abs(m), 1.0, f, normalizar_fase(-math.degrees(np.angle(m))))


def perfil_simulado(con_abierto=False):
    config = Configuracion()
    puntos, puntos_abiertos = [], []
    for f, g, fase in [(1000, 4.8, 2), (2000, 4.6, 4)]:
        a = g * config.rs * np.exp(-1j * np.radians(fase))
        h = complex(0.001, f * 0.000001) if con_abierto else 0j
        pa = None
        if con_abierto:
            l = lectura_compleja(h, f)
            captura = dict(v_i_out=l.vo, v_rms=l.vz, frecuencia=f, fase_cruda=l.fase)
            pa = dict(
                frecuencia=f,
                frecuencia_objetivo=f,
                residual_real=h.real,
                residual_imag=h.imag,
                lecturas=[captura.copy() for _ in range(3)],
            )
            puntos_abiertos.append(pa)
        l = lectura_compleja(a / 100 + h, f)
        puntos.append(calibracion.crear_punto(l, f, config, 100, abierto=pa))
    datos = dict(
        r_sensora=config.rs,
        circuito=config.circuito(),
        osciloscopio=IDENTIDAD.copy(),
        metodo_medicion='senoidal_v1',
    )
    perfil = dict(datos, version=2 if con_abierto else 1, r_referencia=100, puntos=puntos)
    if con_abierto:
        perfil['abierto'] = dict(datos, puntos=puntos_abiertos)
    return calibracion.validar(perfil)
