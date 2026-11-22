"""Sesión VISA: conexión, frecuencia del generador y adquisición común."""

import math
from contextlib import contextmanager

from cancelacion import Cancelado
from modelos import Lectura
from osciloscopios import Osciloscopio, protocolo_para, validar_tiempo_promedio
from visa_backend import crear_gestor


def leer_numero(recurso, comando, control, max_reintentos=5):
    respuesta = ''
    for intento in range(max_reintentos):
        control.comprobar()
        respuesta = recurso.query(comando).strip()
        try:
            valor = float(respuesta)
            if math.isfinite(valor) and abs(valor) <= 1e10:
                return valor
        except ValueError:
            pass
        if intento + 1 < max_reintentos:
            control.esperar(1)
    raise ValueError(f'Respuesta inválida para {comando}: {respuesta!r}')


class Sesion:
    """Agrupa un osciloscopio (osc), un generador (gen) y la cancelación."""

    def __init__(self, osciloscopio, generador, control):
        self.osc = osciloscopio
        self.gen = generador
        self.control = control
        self.identidad = osciloscopio.identidad.copy()
        self.metodo = osciloscopio.metodo_medicion

    def preparar(self, frecuencia):
        """Programar frecuencia → esperar → ajustar escalas → esperar."""
        self.control.comprobar()
        self.osc.frecuencia_objetivo = frecuencia
        self.gen.write(f':CHANnel1:BASE:FREQuency {frecuencia}')
        self.control.esperar(0.5)
        self.osc.autoset()
        self.control.esperar(3)

    def validar_promedio(self, segundos):
        if segundos is not None:
            validar_tiempo_promedio(segundos)
            if self.osc.protocolo != 'tektronix_tbs2000b':
                raise ValueError('El promedio ajustable requiere Tektronix TBS2000B.')

    def leer(self, promedio=None, progreso=None):
        """Devuelve las cuatro lecturas y, si se usó, información del promedio."""

        def lector(recurso, comando, max_reintentos=5):
            return leer_numero(recurso, comando, self.control, max_reintentos)

        self.control.comprobar()
        if promedio is None:
            valores = self.osc.leer(lector)
            datos_promedio = {}
        else:
            valores, datos_promedio = self.osc.leer_promediado(lector, promedio, progreso)
        self.control.comprobar()
        vo, vz, frecuencia, fase = valores
        lectura = Lectura(vo=vo, vz=vz, frecuencia=frecuencia, fase=fase)
        return lectura, datos_promedio


@contextmanager
def conectar(control):
    """Una sesión posee todos los recursos y los libera incluso al cancelar."""
    control.comprobar()
    rm = crear_gestor()
    recursos, osciloscopios, generadores, errores = [], [], [], []
    try:
        for direccion in rm.list_resources('USB?*::INSTR'):
            control.comprobar()
            try:
                recurso = rm.open_resource(direccion)
                recursos.append(recurso)
                recurso.timeout = 4000
                recurso.write_termination = recurso.read_termination = '\n'
                identidad = recurso.query('*IDN?').strip()
                protocolo = protocolo_para(identidad)
                if protocolo:
                    osciloscopios.append(Osciloscopio(recurso, identidad, protocolo, control))
                elif 'UTG' in identidad.upper():
                    generadores.append(recurso)
            except Cancelado:
                raise
            except Exception as error:
                errores.append(str(error))
        control.comprobar()
        if len(osciloscopios) > 1 or len(generadores) > 1:
            raise ValueError(
                'Conectá un solo osciloscopio y un solo generador para elegirlos sin ambigüedad.'
            )
        if not osciloscopios or not generadores:
            detalle = ' '.join(errores)
            raise ValueError(
                'Se requieren osciloscopio y generador USB. Actualizá equipos y verificá sus permisos. '
                + detalle
            )
        osc = osciloscopios[0]
        osc.configurar()
        yield Sesion(osc, generadores[0], control)
    finally:
        for recurso in reversed(recursos):
            try:
                recurso.close()
            except Exception:
                pass
        rm.close()
