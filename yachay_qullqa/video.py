"""ffmpeg/ffprobe: duracion, division en tramos y capturas."""

import csv
import json
import math
import shutil
import subprocess
from pathlib import Path

INSTRUCCIONES_FFMPEG = """ffmpeg no esta instalado o no esta en el PATH. Instalalo y vuelve a abrir la terminal:
  Windows:  winget install Gyan.FFmpeg
  Mac:      brew install ffmpeg
  Linux:    sudo apt install ffmpeg   (o el gestor de tu distribucion)"""


def ffmpeg_disponible() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _ejecutar(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} fallo ({r.returncode}): {r.stderr.strip()[-800:]}")
    return r.stdout


def duracion(video: Path) -> float:
    salida = _ejecutar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(video)])
    return float(json.loads(salida)["format"]["duration"])


def segundos_por_tramo(tam_bytes: int, dur_s: float, tramo_min: int, limite_bytes: int) -> float | None:
    """Duracion de cada tramo, o None si el video se puede enviar entero.
    Se divide si dura mas que tramo_min o si pesa mas que limite_bytes."""
    candidatos = []
    if tramo_min and dur_s > tramo_min * 60:
        candidatos.append(tramo_min * 60)
    if tam_bytes > limite_bytes:
        # Margen del 10 % porque el corte cae en fotogramas clave.
        candidatos.append(dur_s * (limite_bytes / tam_bytes) * 0.9)
    if not candidatos:
        return None
    seg = min(candidatos)
    # Tramos parejos: 3 h con tope de 60 min -> 3 tramos de 60, no 60+60+59+1.
    n = math.ceil(dur_s / seg)
    return math.ceil(dur_s / n)


def dividir(video: Path, carpeta: Path, seg_tramo: float) -> list[dict]:
    """Divide sin recodificar. Devuelve [{archivo, inicio, fin}] con los tiempos
    reales de cada tramo (los da ffmpeg en la lista de segmentos)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    lista = carpeta / "tramos.csv"
    _ejecutar(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-map", "0", "-c", "copy",
               "-f", "segment", "-segment_time", str(int(seg_tramo)), "-reset_timestamps", "1",
               "-segment_list", str(lista), "-segment_list_type", "csv",
               str(carpeta / f"tramo_%02d{video.suffix}")])
    tramos = []
    with open(lista, encoding="utf-8") as f:
        for fila in csv.reader(f):
            if len(fila) >= 3:
                tramos.append({"archivo": str(carpeta / fila[0]), "inicio": float(fila[1]), "fin": float(fila[2])})
    return tramos


def captura(video: Path, segundo: float, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    _ejecutar(["ffmpeg", "-y", "-v", "error", "-ss", f"{segundo:.2f}", "-i", str(video),
               "-frames:v", "1", "-q:v", "3", str(destino)])
