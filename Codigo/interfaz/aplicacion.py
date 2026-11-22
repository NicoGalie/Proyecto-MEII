"""Conecta los paneles con las operaciones; no contiene fórmulas ni SCPI."""

import tkinter as tk
from pathlib import Path
from tkinter import font, ttk

import calibracion
import instrumentos_usb
import operaciones
from cancelacion import Cancelado
from configuracion import Configuracion, cargar_configuracion, guardar_configuracion

from interfaz.barrido import PanelBarrido
from interfaz.calibracion import PanelCalibracion
from interfaz.hardware import PanelHardware
from interfaz.medicion import PanelMedicion
from interfaz.tareas import Tareas


class Aplicacion:
    def __init__(self, root):
        self.root = root
        self.perfil = None
        self.abierto = None
        self.operacion = ''
        self.cerrando = False
        self.usar = tk.BooleanVar(root, value=False)
        root.title('Analizador de Impedancias LC Complejas')
        # Usar el mismo símbolo en la ventana y en el acceso del escritorio.
        ruta_icono = Path(__file__).resolve().parents[2] / 'recursos' / 'utn-fondo-blanco.png'
        imagen = tk.PhotoImage(file=str(ruta_icono))
        escala = max(1, (max(imagen.width(), imagen.height()) + 63) // 64)
        self.icono = imagen.subsample(escala)
        root.iconphoto(True, self.icono)
        root.geometry(
            f'{min(1200, root.winfo_screenwidth() - 80)}x{min(880, root.winfo_screenheight() - 100)}'
        )
        root.minsize(900, 650)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure(
            'Datos.Treeview', rowheight=font.nametofont('TkDefaultFont').metrics('linespace') + 8
        )
        error_configuracion = None
        try:
            config = cargar_configuracion()
        except (OSError, ValueError, KeyError, TypeError) as error:
            config = Configuracion()
            error_configuracion = (
                f'Configuración guardada inválida: {error}. Ingresá nuevamente Rs y RG.'
            )
        self.hardware = PanelHardware(
            root,
            config,
            self.usar,
            self.actualizar_equipos,
            self.habilitar_permisos,
            self.guardar_configuracion,
        )
        self.hardware.pack(fill='x', padx=10, pady=5)
        self.tabs = ttk.Notebook(root)
        self.simple = PanelMedicion(self.tabs, self.medir)
        self.barrido = PanelBarrido(self.tabs, self.barrer, self.cancelar)
        self.calibracion = PanelCalibracion(
            self.tabs, self.calibrar, self.medir_abierto, self.cancelar
        )
        for panel, nombre in (
            (self.simple, 'Medición simple'),
            (self.barrido, 'Barrido en frecuencia'),
            (self.calibracion, 'Calibración'),
        ):
            self.tabs.add(panel, text=nombre)
        self.estado = ttk.Label(
            root, text='Listo. Seleccioná Rs, RG y la frecuencia.', wraplength=1100
        )
        self.estado.pack(side='bottom', fill='x', padx=12, pady=7)
        self.tabs.pack(fill='both', expand=True, padx=10, pady=5)
        self.tareas = Tareas(root, self._ocupado, self._error)
        try:
            self.perfil = calibracion.cargar()
            self.calibracion.mostrar_perfil(self.perfil)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._error(
                ValueError(
                    f'Calibración no disponible: {error}. Podés medir con parámetros nominales.'
                )
            )
        if error_configuracion:
            self.hardware.rg.delete(0, 'end')
            self.informar(error_configuracion)
        root.protocol('WM_DELETE_WINDOW', self.cerrar)

    def informar(self, texto):
        self.estado.configure(text=texto)

    def _error(self, error):
        self.informar('Operación cancelada.' if isinstance(error, Cancelado) else str(error))

    def _ocupado(self, ocupado):
        self.hardware.bloquear(ocupado)
        self.simple.bloquear(ocupado)
        self.barrido.bloquear(ocupado, self.operacion == 'barrido')
        self.calibracion.bloquear(ocupado, self.operacion in ('calibracion', 'abierto'))
        if not ocupado and self.cerrando:
            self.root.destroy()

    def _configuracion(self):
        config = self.hardware.configuracion()
        self.hardware.ganancia.configure(
            text=f'Ganancia nominal = {config.ganancia:g}; fase nominal = 0°'
        )
        return config

    def _iniciar(self, nombre, trabajo, terminado, cancelable=True):
        self.operacion = nombre
        self.informar('Operación en curso…')
        self.tareas.iniciar(trabajo, terminado, self._progreso, cancelable)

    def _progreso(self, evento):
        if evento.get('etapa') == 'promedio':
            self.informar(f'Promediando: {evento["transcurrido"]:.1f}/{evento["duracion"]:g} s')
        elif evento['tipo'] == 'punto':
            self.barrido.tabla.agregar_fila(evento['fila'])
            self.informar(f'Barrido: {evento["indice"]}/{evento["total"]} frecuencias')
        elif evento['tipo'] == 'calibracion':
            self.calibracion.tabla.agregar_punto(evento['punto'])
            self.informar(f'Calibración: {evento["indice"]}/{evento["total"]} frecuencias')
        else:
            self.informar(evento['texto'])

    def guardar_configuracion(self):
        try:
            guardar_configuracion(self._configuracion())
            self.informar('Rs y RG guardadas.')
        except (OSError, ValueError) as error:
            self._error(error)

    def actualizar_equipos(self):
        if not self.tareas.activa:

            def buscar_equipos(control, progreso):
                return instrumentos_usb.detectar_instrumentos(actualizar=True)

            self._iniciar(
                'usb',
                buscar_equipos,
                self.hardware.mostrar_equipos,
                cancelable=False,
            )

    def habilitar_permisos(self):
        if self.tareas.activa:
            return

        def configurar_permisos(control, progreso):
            return instrumentos_usb.habilitar_permisos(self.hardware.equipos)

        def terminado(resultado):
            if not resultado['exito']:
                self.informar(resultado['error'])
                return
            for equipo in self.hardware.equipos:
                if equipo['estado'] == 'sin_permisos':
                    equipo['estado'] = 'pendiente_actualizacion'
            self.hardware.mostrar_equipos(dict(exito=True, equipos=self.hardware.equipos))
            self.informar('Permisos configurados. Pulsá Actualizar equipos para comprobarlos.')

        self._iniciar(
            'usb',
            configurar_permisos,
            terminado,
            cancelable=False,
        )

    def medir(self):
        """Leer los campos, ejecutar la medición y mostrar el resultado."""
        if self.tareas.activa:
            return
        self.simple.limpiar()
        try:
            config = self._configuracion()
            frecuencia, promedio = self.simple.parametros()
            perfil, usar = self.perfil, self.usar.get()
        except ValueError as error:
            self._error(error)
            return

        def realizar_medicion(control, progreso):
            return operaciones.medir(frecuencia, config, perfil, usar, promedio, control, progreso)

        def terminado(resultado):
            self.simple.mostrar(resultado)
            self.informar('Medición finalizada. ' + resultado.ajuste.motivo)

        self._iniciar(
            'simple',
            realizar_medicion,
            terminado,
        )

    def barrer(self):
        if self.tareas.activa:
            return
        try:
            config = self._configuracion()
            inicio, fin, cantidad = self.barrido.parametros()
            perfil, usar = self.perfil, self.usar.get()
        except ValueError as error:
            self._error(error)
            return
        self.barrido.tabla.limpiar()

        def realizar_barrido(control, progreso):
            return operaciones.barrer(
                inicio, fin, cantidad, config, perfil, usar, control, progreso
            )

        def terminado(resultado):
            if self.tareas.control.solicitada:
                resultado.cancelado = True
            self.barrido.mostrar(resultado)
            self.informar(resultado.error or self.barrido.resumen['text'])

        self._iniciar(
            'barrido',
            realizar_barrido,
            terminado,
        )

    def medir_abierto(self):
        if self.tareas.activa:
            return
        try:
            config = self._configuracion()
            inicio, fin, cantidad = self.calibracion.parametros()
        except ValueError as error:
            self._error(error)
            return
        self.abierto = None

        def realizar_abierto(control, progreso):
            return operaciones.medir_abierto(inicio, fin, cantidad, config, control, progreso)

        def terminado(abierto):
            self.tareas.control.comprobar()
            self.abierto = abierto
            self.calibracion.usar_abierto.set(True)
            self.informar(
                'Abierto medido. Colocá la resistencia conocida para completar la calibración.'
            )

        self._iniciar('abierto', realizar_abierto, terminado)

    def calibrar(self):
        if self.tareas.activa:
            return
        try:
            config = self._configuracion()
            inicio, fin, cantidad = self.calibracion.parametros()
            referencia = self.calibracion.resistencia()
            abierto = self.abierto if self.calibracion.usar_abierto.get() else None
            if self.calibracion.usar_abierto.get() and abierto is None:
                raise ValueError('Primero medí el abierto o desmarcá su compensación.')
        except ValueError as error:
            self._error(error)
            return
        self.calibracion.tabla.limpiar()

        def realizar_calibracion(control, progreso):
            return operaciones.calibrar(
                inicio, fin, cantidad, config, referencia, abierto, control, progreso
            )

        def terminado(resultado):
            if resultado.cancelado or self.tareas.control.solicitada:
                self.informar('Calibración cancelada. Se conserva el perfil guardado.')
            elif resultado.error:
                self.informar(
                    'Calibración incompleta: '
                    + resultado.error
                    + '. Se conserva el perfil guardado.'
                )
            else:
                calibracion.guardar(resultado.perfil)
                self.perfil = resultado.perfil
                self.usar.set(True)
                self.calibracion.mostrar_perfil(self.perfil)
                self.informar('Calibración guardada y activada.')

        self._iniciar(
            'calibracion',
            realizar_calibracion,
            terminado,
        )

    def cancelar(self):
        self.tareas.cancelar()
        self.barrido.cancelar.configure(state='disabled')
        self.calibracion.cancelar.configure(state='disabled')
        self.informar('Cancelando… Se libera el equipo al terminar el comando USB en curso.')

    def cerrar(self):
        if self.tareas.activa:
            self.cerrando = True
            self.tareas.control.cancelar()
            self.informar('Cerrando… Esperando la liberación de los instrumentos.')
        else:
            self.root.destroy()


def main():
    root = tk.Tk(className='ME2Analizador')
    Aplicacion(root)
    root.mainloop()
