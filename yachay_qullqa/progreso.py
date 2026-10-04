"""Indicador de "procesando" con tiempo transcurrido, para las esperas largas
(subir el video, esperar a Gemini, dividir el video)."""

import sys
import threading
import time

GIRO = "|/-\\"


class Indicador:
    """Uso: with Indicador("Subiendo video"): ...
    Muestra una linea que gira con el tiempo transcurrido y al terminar deja
    "listo (mm:ss)". Si la salida no es una terminal, no muestra nada."""

    def __init__(self, texto: str):
        self.texto = texto
        self.activo = sys.stdout.isatty()
        self._parar = threading.Event()
        self._hilo = None
        self._inicio = 0.0

    def _tiempo(self) -> str:
        s = int(time.monotonic() - self._inicio)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"

    def _girar(self):
        i = 0
        while not self._parar.wait(0.25):
            sys.stdout.write(f"\r  {GIRO[i % len(GIRO)]} {self.texto}... {self._tiempo()}  ")
            sys.stdout.flush()
            i += 1

    def __enter__(self):
        self._inicio = time.monotonic()
        if self.activo:
            self._hilo = threading.Thread(target=self._girar, daemon=True)
            self._hilo.start()
        return self

    def __exit__(self, tipo, *_):
        if not self.activo:
            return False
        self._parar.set()
        self._hilo.join()
        fin = "listo" if tipo is None else "interrumpido"
        sys.stdout.write(f"\r  {self.texto}: {fin} ({self._tiempo()})" + " " * 10 + "\n")
        sys.stdout.flush()
        return False
