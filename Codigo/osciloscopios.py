"""Comandos SCPI por familia. Transporte común: VISA sobre USBTMC.

Tektronix: TBS2000B Programmer Manual 077114904, adquisición, CURVe y
WFMOutpre; sincronización con *OPC? (pp. 209–213).
"""

import math
import re
import time

import numpy as np
from analisis_senoidal import analizar
from cancelacion import Cancelacion


def validar_tiempo_promedio(segundos):
    if (
        not isinstance(segundos, (int, float))
        or isinstance(segundos, bool)
        or not math.isfinite(segundos)
        or not 0.5 <= segundos <= 120
    ):
        raise ValueError('El tiempo de promedio debe estar entre 0,5 y 120 segundos.')
    return float(segundos)


def protocolo_para(identificacion):
    partes = identificacion.upper().strip().split(',')
    if len(partes) < 2:
        return None
    fabricante, modelo = (p.strip() for p in partes[:2])
    if 'TEKTRONIX' in fabricante:
        if re.fullmatch(r'TBS2(?:072|074|102|104|202|204)B', modelo):
            return 'tektronix_tbs2000b'
        raise ValueError(
            f'Tektronix {modelo}: todavía no hay un protocolo verificado para este modelo.'
        )
    if ('UNI-T' in fabricante or 'UNI-TREND' in fabricante) and modelo.startswith(('DSO', 'UTD')):
        return 'uni_t'
    return None


class Osciloscopio:
    def __init__(self, recurso, identificacion, protocolo, cancelacion=None):
        self.recurso = recurso
        self.cancelacion = cancelacion or Cancelacion()
        partes = [p.strip() for p in identificacion.strip().split(',')]
        self.identidad = dict(zip(('fabricante', 'modelo', 'serie'), partes[:3]))
        self.protocolo = protocolo
        self.metodo_medicion = 'senoidal_v1' if protocolo == 'tektronix_tbs2000b' else 'scpi_v1'
        self.circuito_abierto = False
        self.frecuencia_objetivo = None

    def configurar(self):
        if self.protocolo == 'tektronix_tbs2000b':
            # Las consultas numéricas deben responder sin encabezado SCPI.
            self.recurso.write('HEADer OFF')

    def leer(self, leer_numero):
        if self.protocolo == 'uni_t':
            return tuple(
                leer_numero(self.recurso, comando)
                for comando in (
                    ':MEASure:VRMS? CHANnel1',
                    ':MEASure:VRMS? CHANnel2',
                    ':MEASure:FREQuency? CHANnel2',
                    ':MEASure:PHASe? CHANnel2,CHANnel1',
                )
            )
        return self._leer_captura(leer_numero)

    def _adquirir_promedio(self, leer_numero, segundos, progreso):
        """Promedio nativo de formas de onda, con ventana de tiempo real.

        TBS2000B 077114904, pp. 42–44: máximo 512; después el promedio
        es exponencial. El contador puede sobrevivir a STOP/RUN, por lo que
        se verifica su incremento, no se confunde con capturas anteriores.
        """
        s = self.recurso
        s.write('ACQuire:STATE OFF')
        s.write('TRIGger:A:TYPe EDGE')
        s.write('TRIGger:A:EDGE:SOUrce CH2')
        s.write('TRIGger:A:MODe NORMal')
        s.write('ACQuire:MODe SAMple')
        s.write('ACQuire:MODe AVErage')
        s.write('ACQuire:NUMAVg 512')
        # Iniciar una secuencia nueva descarta el promedio acumulado anterior;
        # luego continuar RUNSTOP permite alcanzar el tiempo elegido incluso
        # cuando el equipo ya completó sus primeras 512 adquisiciones.
        s.write('ACQuire:STOPAfter SEQuence')
        s.write('ACQuire:STATE ON')
        s.write('ACQuire:STOPAfter RUNSTop')
        inicial = leer_numero(s, 'ACQuire:NUMACq?')
        comienzo = time.monotonic()
        fin = comienzo + segundos
        if progreso:
            progreso({'etapa': 'promedio', 'transcurrido': 0.0, 'duracion': segundos})
        while True:
            restante = fin - time.monotonic()
            if restante <= 0:
                break
            self.cancelacion.esperar(min(0.2, restante))
            if progreso:
                progreso(
                    {
                        'etapa': 'promedio',
                        'transcurrido': min(segundos, time.monotonic() - comienzo),
                        'duracion': segundos,
                    }
                )
        if progreso:
            progreso({'etapa': 'promedio', 'transcurrido': segundos, 'duracion': segundos})
        s.write('ACQuire:STATE OFF')
        if leer_numero(s, 'ACQuire:STATE?') != 0:
            raise ValueError('No se pudo congelar la señal promediada de ambos canales.')
        final = leer_numero(s, 'ACQuire:NUMACq?')
        capturas = final - inicial
        if not math.isfinite(capturas) or capturas < 2 or not float(capturas).is_integer():
            raise ValueError(
                'No hubo al menos dos adquisiciones nuevas durante el promedio. Revisá el disparo de CH2 o aumentá el tiempo.'
            )
        return {
            'tiempo_promedio_s': segundos,
            'tiempo_promedio_real_s': max(segundos, time.monotonic() - comienzo),
            'adquisiciones_promedio': int(capturas),
            'limite_promedio': 512,
        }

    def leer_promediado(self, leer_numero, segundos, progreso=None):
        segundos = validar_tiempo_promedio(segundos)
        if self.protocolo != 'tektronix_tbs2000b':
            raise ValueError('El promedio de señales requiere Tektronix TBS2000B.')
        return self._leer_captura(leer_numero, segundos, progreso)

    def _leer_captura(self, leer_numero, tiempo_promedio=None, progreso=None):
        self.cancelacion.comprobar()
        s = self.recurso
        ajustes = (
            'ACQuire:STATE',
            'ACQuire:STOPAfter',
            'ACQuire:MODe',
            'ACQuire:NUMAVg',
            'DATa:ENCdg',
            'DATa:WIDth',
            'DATa:STARt',
            'DATa:STOP',
            'DATa:SOUrce',
            'MEASUrement:IMMed:TYPe',
            'MEASUrement:IMMed:SOUrce1',
            'MEASUrement:GATing',
        )
        if tiempo_promedio is not None:
            ajustes += ('TRIGger:A:TYPe', 'TRIGger:A:EDGE:SOUrce', 'TRIGger:A:MODe')
        originales = {cmd: s.query(cmd + '?').strip() for cmd in ajustes}
        timeout, chunk_size = s.timeout, s.chunk_size
        try:
            s.timeout = 8000
            # Un bloque completo evita las respuestas truncadas del transporte USB.
            s.chunk_size = 1048576
            s.write('MEASUrement:GATing OFF')
            # Autoset puede dejar la señal sensora de una resistencia grande
            # ocupando menos de una división. Aprovechá unas seis divisiones
            # para reducir el error de cuantización del ADC.
            for canal in ('CH1', 'CH2'):
                self.cancelacion.comprobar()
                s.write(f'MEASUrement:IMMed:SOUrce1 {canal}')
                s.write('MEASUrement:IMMed:TYPe PK2Pk')
                # Las medidas automáticas se actualizan con la adquisición;
                # una consulta inmediata puede devolver el canal anterior.
                self.cancelacion.esperar(0.3)
                if self.circuito_abierto and canal == 'CH1':
                    # En abierto la medida automática puede declarar que
                    # no hay señal. La captura se ajusta y verifica después.
                    try:
                        vpp = leer_numero(s, 'MEASUrement:IMMed:VALue?', max_reintentos=1)
                    except ValueError:
                        vpp = 0.06
                else:
                    vpp = leer_numero(s, 'MEASUrement:IMMed:VALue?')
                if vpp <= 0:
                    raise ValueError(f'{canal}: amplitud no válida para ajustar la escala.')
                # Autoset desplaza los canales para separarlos en pantalla;
                # centrarlos evita recorte al aprovechar el rango del ADC.
                s.write(f'{canal}:POSition 0')
                escala = max(0.002, vpp / 6)
                if self.circuito_abierto and canal == 'CH2':
                    # Con corriente casi nula, Autoset puede estar siguiendo
                    # ruido en CH1. Conservá el rango amplio de tensión de CH2.
                    escala = max(escala, leer_numero(s, 'CH2:SCAle?'))
                s.write(f'{canal}:SCAle {escala:.12g}')
            self.cancelacion.esperar(0.2)
            s.write('MEASUrement:IMMed:SOUrce1 CH2')
            s.write('MEASUrement:IMMed:TYPe FREQuency')
            self.cancelacion.esperar(0.3)
            estimada = (
                self.frecuencia_objetivo
                if self.circuito_abierto and self.frecuencia_objetivo
                else leer_numero(s, 'MEASUrement:IMMed:VALue?')
            )
            if estimada <= 0:
                raise ValueError('No hay una frecuencia válida en CH2.')
            # Ventana de cinco ciclos y registro acotado; la misma adquisición
            # proporciona amplitud, frecuencia y fase de ambos canales.
            s.write('ACQuire:STATE OFF')
            s.write('HORizontal:RECOrdlength:Auto 0')
            s.write('HORizontal:RECOrdlength 20000')
            s.write(
                f'HORizontal:MAIn:SCAle {(4 if self.circuito_abierto else 1) / (3 * estimada):.12g}'
            )
            # Promediar adquisiciones sincronizadas conserva la fase entre canales.
            metadata = None
            if tiempo_promedio is None:
                s.write('ACQuire:MODe AVErage')
                s.write('ACQuire:NUMAVg 128' if self.circuito_abierto else 'ACQuire:NUMAVg 16')
                s.write('ACQuire:STOPAfter SEQuence')
                s.write('ACQuire:STATE ON')
                if leer_numero(s, '*OPC?') != 1:
                    raise ValueError('El osciloscopio no confirmó la nueva adquisición.')
                if leer_numero(s, 'ACQuire:STATE?') != 0:
                    raise ValueError(
                        'La adquisición no se detuvo; no se puede asegurar una captura común.'
                    )
            else:
                metadata = self._adquirir_promedio(leer_numero, tiempo_promedio, progreso)
            s.write('DATa:ENCdg RIBinary')
            # Transferir un byte del ADC evita depender
            # del escalado de los bytes de relleno de este firmware.
            s.write('DATa:WIDth 1')
            s.write('DATa:STARt 1')
            cantidad = int(leer_numero(s, 'HORizontal:RECOrdlength?'))
            if not 100 <= cantidad <= 20000:
                raise ValueError('Longitud de captura no válida para esta medición.')
            s.write(f'DATa:STOP {cantidad}')
            canales, tiempos = [], []
            for canal in ('CH1', 'CH2'):
                self.cancelacion.comprobar()
                s.write(f'DATa:SOUrce {canal}')
                dt = leer_numero(s, 'WFMOutpre:XINcr?')
                x0 = leer_numero(s, 'WFMOutpre:XZEro?')
                off = leer_numero(s, 'WFMOutpre:PT_Off?')
                mul = leer_numero(s, 'WFMOutpre:YMUlt?')
                yoff = leer_numero(s, 'WFMOutpre:YOFf?')
                yzero = leer_numero(s, 'WFMOutpre:YZEro?')
                datos = np.asarray(
                    s.query_binary_values(
                        'CURVe?', datatype='b', is_big_endian=True, expect_termination=False
                    ),
                    dtype=float,
                )
                self.cancelacion.comprobar()
                if datos.size != cantidad:
                    raise ValueError(
                        f'{canal}: transferencia incompleta ({datos.size}/{cantidad} muestras).'
                    )
                if np.any(np.abs(datos) >= 0.98 * 128):
                    raise ValueError(
                        f'{canal}: captura recortada; aumentá la escala vertical o reducí la amplitud.'
                    )
                # El límite analógico puede saturar antes del código extremo
                # del ADC. Una meseta extensa en ambos picos también es recorte.
                if (
                    np.unique(datos).size > 20
                    and min(np.mean(datos == datos.min()), np.mean(datos == datos.max())) > 0.15
                ):
                    raise ValueError(
                        f'{canal}: señal con mesetas de recorte; revisá la escala y el circuito.'
                    )
                if dt <= 0 or mul <= 0:
                    raise ValueError(f'{canal}: escala de captura inválida.')
                canales.append((datos - yoff) * mul + yzero)
                tiempos.append(x0 + (np.arange(cantidad) - off) * dt)
            if not np.allclose(tiempos[0], tiempos[1], rtol=0, atol=1e-12):
                raise ValueError('CH1 y CH2 no comparten el mismo eje de tiempo.')
            if self.circuito_abierto:
                # La fundamental residual es pequeña. Solo en abierto se
                # admite más residuo, con tres capturas coherentes verificadas
                # por el backend. Las mediciones normales conservan el 5%.
                return analizar(tiempos[0], *canales, estimada, circuito_abierto=True)
            lecturas = analizar(tiempos[0], *canales, estimada)
            return (lecturas, metadata) if tiempo_promedio is not None else lecturas
        finally:
            try:
                for cmd, valor in originales.items():
                    if cmd != 'ACQuire:STATE':
                        s.write(f'{cmd} {valor}')
            finally:
                try:
                    s.write('ACQuire:STATE ' + originales['ACQuire:STATE'])
                finally:
                    s.timeout, s.chunk_size = timeout, chunk_size

    def autoset(self):
        self.cancelacion.comprobar()
        if self.protocolo == 'tektronix_tbs2000b':
            for canal in ('CH1', 'CH2'):
                self.recurso.write(f'SELect:{canal} ON')
                self.recurso.write(f'{canal}:COUPling DC')
        self.recurso.write(
            'AUTOSet EXECute' if self.protocolo == 'tektronix_tbs2000b' else ':AUToset'
        )
        if self.protocolo == 'tektronix_tbs2000b':
            self.recurso.write('TRIGger:A:EDGE:SOUrce CH2')
            self.recurso.write('TRIGger:A:LEVel:CH2 0')

    def close(self):
        self.recurso.close()
