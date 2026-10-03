"""Paso 1: agrupa los archivos de clases/ por numero de clase."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .curso import Curso

RE_CLASE = re.compile(r"^clase[\s_-]*(\d+)$", re.IGNORECASE)
EXT_VIDEO = {".mp4", ".mov", ".webm", ".mkv", ".avi"}


@dataclass
class Clase:
    numero: str  # "01"
    video: Path | None = None
    chat: Path | None = None  # .txt de Zoom
    transcripcion: Path | None = None  # .vtt de Zoom
    otros: list[Path] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        return f"Clase{self.numero}"

    def faltantes(self) -> list[str]:
        f = []
        if not self.video:
            f.append("video (.mp4)")
        if not self.chat:
            f.append("chat (.txt)")
        if not self.transcripcion:
            f.append("transcripcion (.vtt)")
        return f

    def archivos(self) -> list[Path]:
        return [p for p in (self.video, self.chat, self.transcripcion) if p] + self.otros


def inventario(curso: Curso) -> tuple[list[Clase], list[Path]]:
    """Devuelve las clases en orden numerico y los archivos que no se reconocen."""
    clases: dict[str, Clase] = {}
    desconocidos = []
    if not curso.clases.exists():
        return [], []
    for p in sorted(curso.clases.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        m = RE_CLASE.match(p.stem)
        if not m:
            desconocidos.append(p)
            continue
        num = f"{int(m.group(1)):02d}"
        c = clases.setdefault(num, Clase(num))
        ext = p.suffix.lower()
        if ext in EXT_VIDEO and not c.video:
            c.video = p
        elif ext == ".txt" and not c.chat:
            c.chat = p
        elif ext == ".vtt" and not c.transcripcion:
            c.transcripcion = p
        else:
            c.otros.append(p)
    return [clases[k] for k in sorted(clases, key=int)], desconocidos
