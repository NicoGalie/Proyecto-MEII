"""Cancelación cooperativa: interrumpe las esperas y respeta el cierre de VISA."""

from threading import Event


class Cancelado(Exception):
    pass


class Cancelacion:
    def __init__(self):
        self.evento = Event()

    def cancelar(self):
        self.evento.set()

    @property
    def solicitada(self):
        return self.evento.is_set()

    def comprobar(self):
        if self.solicitada:
            raise Cancelado('Operación cancelada por el usuario.')

    def esperar(self, segundos):
        if self.evento.wait(segundos):
            self.comprobar()
