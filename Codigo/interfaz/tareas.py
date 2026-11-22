"""Un trabajador USB; Tk recibe resultados exclusivamente por su cola."""

from queue import Empty, Queue
from threading import Thread

from cancelacion import Cancelacion


class Tareas:
    def __init__(self, root, estado, error):
        self.root, self.estado, self.error = root, estado, error
        self.activa = False
        self.cancelable = False
        self.control = None

    def iniciar(self, trabajo, terminado, progreso=None, cancelable=True):
        if self.activa:
            return
        self.activa, self.cancelable = True, cancelable
        self.control = Cancelacion()
        cola = Queue()
        self.estado(True)

        def enviar_progreso(evento):
            cola.put(('progreso', evento))

        def ejecutar():
            try:
                self.control.comprobar()
                resultado = trabajo(self.control, enviar_progreso)
            except Exception as error:
                resultado = error
            cola.put(('resultado', resultado))

        def revisar():
            try:
                while True:
                    tipo, dato = cola.get_nowait()
                    if tipo == 'resultado':
                        break
                    if progreso:
                        try:
                            progreso(dato)
                        except Exception as error:
                            self.control.cancelar()
                            self.error(error)
            except Empty:
                self.root.after(50, revisar)
                return
            try:
                if isinstance(dato, Exception):
                    self.error(dato)
                else:
                    terminado(dato)
            except Exception as error:
                self.error(error)
            finally:
                self.activa = False
                self.estado(False)

        Thread(target=ejecutar, daemon=True).start()
        self.root.after(50, revisar)

    def cancelar(self):
        if self.activa and self.cancelable:
            self.control.cancelar()
