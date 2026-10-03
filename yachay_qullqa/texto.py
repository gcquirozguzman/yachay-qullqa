"""Paso 2: lee el chat (.txt) y la transcripcion (.vtt) de Zoom y extrae
enlaces y menciones a archivos o materiales, con su hora y linea."""

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .utiles import a_hhmmss, a_segundos

# Chat de Zoom: "HH:MM:SS<tab>Autor:<tab>mensaje". Las lineas siguientes sin hora
# son continuacion del mismo mensaje.
RE_LINEA_CHAT = re.compile(r"^(\d{1,2}:\d{2}:\d{2})\t([^\t]*?):?\t(.*)$")
RE_CUE = re.compile(r"^(\S+)\s+-->\s+(\S+)")
RE_URL = re.compile(r"(?:https?://|\bwww\.[\w-]+\.[a-z]{2,})[^\s<>\"'`]*", re.IGNORECASE)
# Sube este numero si cambia la extraccion: las clases se vuelven a leer.
VERSION_EXTRACCION = "2"
EXTENSIONES = (
    "pdf|docx?|xlsx?|xlsm|csv|tsv|pptx?|ipynb|zip|rar|7z|json|parquet|avro|orc|sql|py|"
    "ya?ml|png|jpe?g|gif|txt|md|r|sav|dta"
)
RE_NOMBRE_ARCHIVO = re.compile(rf"\b[\w\-]+(?:\.[\w\-]+)*\.(?:{EXTENSIONES})\b", re.IGNORECASE)

# Palabras que indican un material. Se busca por palabra completa.
PALABRAS_MATERIAL = {
    "Word": r"word|documento|doc",
    "PDF": r"pdf",
    "Excel": r"excel|hoja de c[aá]lculo|spreadsheet|sheets?",
    "Presentacion": r"presentaci[oó]n(?:es)?|diapositivas?|ppt|power\s?point|slides?",
    "Dataset": r"datasets?|data\s?sets?|conjuntos? de datos|csv",
    "Repositorio": r"repositorios?|repo|github|gitlab",
    "Notebook": r"notebooks?|colab|jupyter",
    "Archivo": r"archivos?|plantillas?|gu[ií]as?|r[uú]bricas?|enunciados?|material(?:es)?",
    "Plataforma de curso": r"canvas|drive",
}
RE_PALABRAS = {
    tipo: re.compile(rf"\b(?:{patron})\b", re.IGNORECASE) for tipo, patron in PALABRAS_MATERIAL.items()
}
NOTA_ZOOM_TRUNCADO = "[Full message cannot be displayed here]"


@dataclass
class Mensaje:
    tiempo: str  # HH:MM:SS
    autor: str
    texto: str
    linea: int


@dataclass
class Cue:
    inicio: int  # segundos
    fin: int
    texto: str
    linea: int


@dataclass
class Hallazgo:
    """Un enlace o una mencion encontrada en el chat o en la transcripcion."""
    tipo: str  # "enlace" | "nombre_archivo" | categoria de PALABRAS_MATERIAL
    valor: str  # URL, nombre de archivo o palabra encontrada
    fuente: str  # "chat" | "transcripcion"
    tiempo: str
    linea: int
    contexto: str
    autor: str = ""


def leer_chat(ruta: Path) -> list[Mensaje]:
    mensajes: list[Mensaje] = []
    for n, linea in enumerate(ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        m = RE_LINEA_CHAT.match(linea)
        if m:
            mensajes.append(Mensaje(m.group(1).zfill(8), m.group(2).strip(), m.group(3), n))
        elif mensajes:
            mensajes[-1].texto += "\n" + linea
        elif linea.strip():
            mensajes.append(Mensaje("00:00:00", "", linea, n))
    return mensajes


def leer_vtt(ruta: Path) -> list[Cue]:
    cues: list[Cue] = []
    actual: Cue | None = None
    for n, linea in enumerate(ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        m = RE_CUE.match(linea.strip())
        if m:
            actual = Cue(a_segundos(m.group(1)), a_segundos(m.group(2)), "", n)
            cues.append(actual)
        elif not linea.strip():
            actual = None
        elif actual is not None:
            actual.texto = f"{actual.texto} {linea.strip()}".strip()
    return [c for c in cues if c.texto]


def vtt_compacto(cues: list[Cue], desde: int = 0, hasta: int | None = None, restar: int = 0) -> str:
    """Transcripcion en lineas '[HH:MM:SS] texto', recortada a un tramo y con el
    tiempo relativo al inicio del tramo."""
    lineas = []
    for c in cues:
        if c.fin < desde or (hasta is not None and c.inicio > hasta):
            continue
        lineas.append(f"[{a_hhmmss(c.inicio - restar)}] {c.texto}")
    return "\n".join(lineas)


def _limpiar_url(url: str) -> str:
    url = url.rstrip(".,;:!?)]}»”’")
    if url.lower().startswith("www."):
        url = "https://" + url
    return url


def _recortar(texto: str, largo: int = 160) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _buscar(texto: str, fuente: str, tiempo: str, linea: int, autor: str = "") -> list[Hallazgo]:
    hallazgos = []
    contexto = _recortar(texto)
    for m in RE_URL.finditer(texto):
        hallazgos.append(Hallazgo("enlace", _limpiar_url(m.group(0)), fuente, tiempo, linea, contexto, autor))
    sin_urls = RE_URL.sub(" ", texto)
    for m in RE_NOMBRE_ARCHIVO.finditer(sin_urls):
        hallazgos.append(Hallazgo("nombre_archivo", m.group(0), fuente, tiempo, linea, contexto, autor))
    for tipo, patron in RE_PALABRAS.items():
        m = patron.search(sin_urls)
        if m:
            hallazgos.append(Hallazgo(tipo, m.group(0), fuente, tiempo, linea, contexto, autor))
    return hallazgos


def extraer(chat: Path | None, vtt: Path | None) -> dict:
    """Devuelve {'enlaces': [...], 'menciones': [...], 'truncados': [...]} listo para JSON."""
    hallazgos: list[Hallazgo] = []
    truncados = []
    if chat:
        for msg in leer_chat(chat):
            hallazgos += _buscar(msg.texto, "chat", msg.tiempo, msg.linea, msg.autor)
            if NOTA_ZOOM_TRUNCADO in msg.texto:
                truncados.append({"tiempo": msg.tiempo, "linea": msg.linea, "autor": msg.autor})
    if vtt:
        for cue in leer_vtt(vtt):
            hallazgos += _buscar(cue.texto, "transcripcion", a_hhmmss(cue.inicio), cue.linea)

    enlaces, vistos = [], set()
    for h in hallazgos:
        if h.tipo == "enlace" and h.valor not in vistos:
            vistos.add(h.valor)
            enlaces.append(asdict(h))
    menciones = [asdict(h) for h in hallazgos if h.tipo != "enlace"]
    return {"enlaces": enlaces, "menciones": menciones, "truncados": truncados}
