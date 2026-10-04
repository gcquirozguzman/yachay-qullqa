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


def dividir(video: Path, carpeta: Path, seg_tramo: float, solape: int = 120) -> list[dict]:
    """Divide sin recodificar en tramos que se solapan unos `solape` segundos, para
    no perder el hilo en el corte. Devuelve [{archivo, inicio, fin, desde}]:
    `desde` es donde empieza lo nuevo del tramo (antes de eso, repite el anterior).

    Primero corta piezas cortas (ffmpeg da sus tiempos exactos) y luego arma cada
    tramo uniendo piezas, asi los tiempos siguen siendo exactos."""
    piezas_dir = carpeta / "piezas"
    piezas_dir.mkdir(parents=True, exist_ok=True)
    lista = piezas_dir / "piezas.csv"
    _ejecutar(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-map", "0", "-c", "copy",
               "-f", "segment", "-segment_time", str(max(30, solape)), "-reset_timestamps", "1",
               "-segment_list", str(lista), "-segment_list_type", "csv",
               str(piezas_dir / f"pieza_%04d{video.suffix}")])
    with open(lista, encoding="utf-8") as f:
        piezas = [(piezas_dir / fila[0], float(fila[1]), float(fila[2])) for fila in csv.reader(f) if len(fila) >= 3]

    tramos = []
    for indices in agrupar_piezas([(p[1], p[2]) for p in piezas], seg_tramo):
        j_ini, j_desde, j_fin = indices
        destino = carpeta / f"tramo_{len(tramos):02d}{video.suffix}"
        concat = carpeta / f"tramo_{len(tramos):02d}.txt"
        concat.write_text("".join(f"file '{piezas[j][0].as_posix()}'\n" for j in range(j_ini, j_fin + 1)),
                          encoding="utf-8")
        _ejecutar(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                   "-c", "copy", str(destino)])
        concat.unlink()
        tramos.append({"archivo": str(destino), "inicio": piezas[j_ini][1],
                       "fin": piezas[j_fin][2], "desde": piezas[j_desde][1]})
    shutil.rmtree(piezas_dir, ignore_errors=True)
    return tramos


def agrupar_piezas(piezas: list[tuple[float, float]], seg_tramo: float) -> list[tuple[int, int, int]]:
    """Para cada tramo: (primera pieza, pieza donde empieza lo nuevo, ultima pieza).
    Cada tramo, salvo el primero, empieza una pieza antes: ese es el solape."""
    grupos = []
    j_desde = 0
    while j_desde < len(piezas):
        limite = piezas[j_desde][0] + seg_tramo
        j_fin = j_desde
        while j_fin + 1 < len(piezas) and piezas[j_fin + 1][0] < limite:
            j_fin += 1
        grupos.append((max(0, j_desde - 1) if grupos else 0, j_desde, j_fin))
        j_desde = j_fin + 1
    return grupos


def captura(video: Path, segundo: float, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    _ejecutar(["ffmpeg", "-y", "-v", "error", "-ss", f"{segundo:.2f}", "-i", str(video),
               "-frames:v", "1", "-q:v", "3", str(destino)])
