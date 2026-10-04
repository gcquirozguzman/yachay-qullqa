"""Acceso a Gemini. Integra lo que hacia procesar_clases.py: subir el video,
esperar a que Google lo procese y pedir la respuesta en segundo plano con
client.interactions.create (processing "agentic", background=True).

Cambios respecto del script original:
- El estado "queued" se trata como "en espera" (antes se tomaba como fallo).
- Se guarda el id de la interaccion y el nombre del archivo subido, para que
  un corte no obligue a subir de nuevo ni a repetir la generacion.
- Se aceptan textos de apoyo (transcripcion, chat) e imagenes.
"""

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Callable

TIPOS = {
    ".mp4": "video/mp4", ".mov": "video/mov", ".avi": "video/avi", ".webm": "video/webm",
    ".mpeg": "video/mpeg", ".mpg": "video/mpg", ".wmv": "video/wmv", ".flv": "video/x-flv",
    ".3gp": "video/3gpp",
}
EN_CURSO = {"queued", "in_progress"}
REINTENTOS = 4
ESPERA_REINTENTO = 90  # segundos, se multiplica por el numero de intento

INSTRUCCIONES_CLAVE = """Falta la variable de entorno GEMINI_API_KEY.
Crea una clave gratuita en https://aistudio.google.com/apikey y pegala en el archivo
.env de la raiz del repositorio (GEMINI_API_KEY=tu_clave), o guardala como variable:
  Windows (PowerShell, permanente):  setx GEMINI_API_KEY "tu_clave"   (y reabre la terminal)
  Mac / Linux:                       export GEMINI_API_KEY="tu_clave"  (agregalo a ~/.bashrc o ~/.zshrc)"""


ARCHIVO_ENV = Path(__file__).resolve().parent.parent / ".env"


def _cargar_env() -> None:
    """Lee GEMINI_API_KEY=... del archivo .env de la raiz (excluido del git).
    Una variable de entorno ya definida tiene prioridad."""
    if os.environ.get("GEMINI_API_KEY") or not ARCHIVO_ENV.exists():
        return
    for linea in ARCHIVO_ENV.read_text(encoding="utf-8-sig").splitlines():
        nombre, _, valor = linea.partition("=")
        if nombre.strip() == "GEMINI_API_KEY" and valor.strip():
            os.environ["GEMINI_API_KEY"] = valor.strip().strip("\"'")


def clave_disponible() -> bool:
    _cargar_env()
    return bool(os.environ.get("GEMINI_API_KEY"))


def crear_cliente():
    if not clave_disponible():
        raise SystemExit(INSTRUCCIONES_CLAVE)
    from google import genai
    return genai.Client()


def con_reintentos(funcion: Callable, etiqueta: str, log=print):
    for intento in range(1, REINTENTOS + 1):
        try:
            return funcion()
        except Exception as error:  # la API puede fallar por cuota, red, etc.
            log(f"    {etiqueta}: error (intento {intento}/{REINTENTOS}): {error}")
            if intento == REINTENTOS:
                raise
            time.sleep(ESPERA_REINTENTO * intento)


def subir_video(client, ruta: Path):
    """Sube el video y espera a que Google termine de procesarlo."""
    with open(ruta, "rb") as f:
        archivo = client.files.upload(file=f, config={"mime_type": TIPOS[ruta.suffix.lower()]})
    return esperar_archivo(client, archivo)


def esperar_archivo(client, archivo):
    while not archivo.state or archivo.state.name == "PROCESSING":
        time.sleep(10)
        archivo = client.files.get(name=archivo.name)
    if archivo.state.name != "ACTIVE":
        raise RuntimeError(f"Google no pudo procesar el archivo ({archivo.state.name})")
    return archivo


def archivo_activo(client, nombre: str):
    """Devuelve el archivo ya subido si sigue disponible (Google los borra a las 48 h)."""
    try:
        archivo = client.files.get(name=nombre)
        return esperar_archivo(client, archivo)
    except Exception:
        return None


def borrar_archivo(client, nombre: str) -> None:
    try:
        client.files.delete(name=nombre)
    except Exception:
        pass  # Google borra los archivos subidos automaticamente


def bloque_video(archivo) -> dict:
    return {"type": "video", "uri": archivo.uri, "mime_type": archivo.mime_type, "processing": "agentic"}


def bloque_texto(texto: str) -> dict:
    return {"type": "text", "text": texto}


def bloque_imagen(ruta: Path) -> dict:
    tipo = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "image", "data": base64.b64encode(ruta.read_bytes()).decode("ascii"), "mime_type": tipo}


def generar(client, modelo: str, entrada: list[dict], id_previo: str | None = None,
            al_crear: Callable[[str], None] | None = None) -> str:
    """Pide la respuesta en segundo plano y espera el resultado.
    Si id_previo apunta a una interaccion que sigue viva, la retoma."""
    interaccion = None
    if id_previo:
        try:
            interaccion = client.interactions.get(id=id_previo)
            if interaccion.status not in EN_CURSO | {"completed"}:
                interaccion = None
        except Exception:
            interaccion = None
    if interaccion is None:
        interaccion = client.interactions.create(model=modelo, input=entrada, background=True)
        if al_crear:
            al_crear(interaccion.id)
    while interaccion.status in EN_CURSO:
        time.sleep(15)
        interaccion = client.interactions.get(id=interaccion.id)
    if interaccion.status != "completed":
        raise RuntimeError(f"La generacion termino con estado: {interaccion.status}")
    texto = interaccion.output_text
    if not texto or not texto.strip():
        raise RuntimeError("La respuesta llego vacia")
    return texto


def extraer_json(texto: str):
    """Lee el JSON de la respuesta aunque venga entre ``` o con texto alrededor."""
    m = re.search(r"```(?:json)?\s*(.*?)```", texto, re.DOTALL)
    candidato = m.group(1) if m else texto
    inicio = min((i for i in (candidato.find("{"), candidato.find("[")) if i >= 0), default=-1)
    if inicio < 0:
        raise ValueError("La respuesta no contiene JSON")
    fin = max(candidato.rfind("}"), candidato.rfind("]"))
    return json.loads(candidato[inicio : fin + 1])
