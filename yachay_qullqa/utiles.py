"""Funciones pequenas compartidas: tiempos, hashes, escritura atomica."""

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

_RE_TIEMPO = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,]\d+)?\s*$")


def a_segundos(texto: str) -> int:
    """'01:02:03', '02:03' o '01:02:03.500' -> segundos enteros."""
    m = _RE_TIEMPO.match(str(texto))
    if not m:
        raise ValueError(f"Marca de tiempo no valida: {texto!r}")
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s)


def a_hhmmss(segundos: float) -> str:
    segundos = max(0, int(round(segundos)))
    return f"{segundos // 3600:02d}:{segundos % 3600 // 60:02d}:{segundos % 60:02d}"


def sha256_archivo(ruta: Path, bloque: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while chunk := f.read(bloque):
            h.update(chunk)
    return h.hexdigest()


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def huella_json(obj) -> str:
    return sha256_texto(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def escribir_atomico(ruta: Path, contenido: str) -> None:
    """Escribe en un temporal y lo renombra: un corte nunca deja el archivo a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def leer_json(ruta: Path, defecto=None):
    if not ruta.exists():
        return defecto
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta: Path, datos) -> None:
    escribir_atomico(ruta, json.dumps(datos, ensure_ascii=False, indent=2) + "\n")


def slug(texto: str, largo: int = 60) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto[:largo].rstrip("-") or "sin-nombre"
