"""Linea de comandos. Cada comando trabaja sobre un solo curso.

  python -m yachay_qullqa crear <curso> --nombre "..." --descripcion "..."
  python -m yachay_qullqa procesar <curso> [--clase 01] [--reintentar-descargas]
  python -m yachay_qullqa estado <curso>
"""

import argparse
import sys

from . import estado as est, gemini, video
from .curso import RAIZ_CURSOS, Curso
from .inventario import inventario
from .pipeline import procesar

ETAPAS = ("texto", "video", "capturas", "apuntes")


def cmd_crear(a) -> int:
    curso = Curso.crear(a.curso, a.nombre or a.curso, a.descripcion or "")
    print(f"Curso creado en {curso.carpeta}")
    print(f"Copia los archivos de clase (Clase01.mp4, Clase01.txt, Clase01.vtt...) en {curso.clases}")
    if not a.descripcion:
        print(f"Escribe una descripcion del curso en {curso.carpeta / 'curso.toml'}: se usa en los prompts.")
    return 0


def cmd_procesar(a) -> int:
    return procesar(Curso.abrir(a.curso), a.clase, a.reintentar_descargas)


def cmd_estado(a) -> int:
    curso = Curso.abrir(a.curso)
    estado = est.cargar(curso)
    clases, desconocidos = inventario(curso)
    print(f"Curso: {curso.nombre} ({curso.carpeta})")
    print(f"ffmpeg: {'si' if video.ffmpeg_disponible() else 'NO'} | GEMINI_API_KEY: {'si' if gemini.clave_disponible() else 'NO'}")
    print(f"\n{'Clase':8} {'Archivos':12} {'Cambios':22} " + " ".join(f"{e:9}" for e in ETAPAS))
    for c in clases:
        e = estado["clases"].get(c.numero, {})
        archivos = "".join(x if p else "-" for x, p in (("V", c.video), ("C", c.chat), ("T", c.transcripcion)))
        actuales = {p.name: est.huella_archivo(p) for p in c.archivos()}
        actuales_mat = est.huellas_carpeta(curso.materiales / c.nombre)
        if not e:
            cambios = "nueva"
        elif actuales != e.get("archivos") or actuales_mat != e.get("materiales", {}):
            cambios = "archivos nuevos/cambiados"
        else:
            cambios = "-"
        etapas = " ".join(f"{'ok' if et in e.get('etapas', {}) else '·':9}" for et in ETAPAS)
        print(f"{c.nombre:8} {archivos:12} {cambios:22} {etapas}")
        if e.get("error"):
            print(f"         error: {e['error']}")
        elif e.get("pendiente"):
            print(f"         pendiente: {e['pendiente']}")
    for p in desconocidos:
        print(f"no reconocido: {p.name}")
    print("\nArchivos: V=video C=chat T=transcripcion. '·' = etapa sin hacer.")
    print(f"Temas: {len(estado['temas']['catalogo'])}. Ver {curso.indice.name} y {curso.pendientes.name}.")
    return 0


def main(argv=None) -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(prog="yachay_qullqa", description="Apuntes de clases de Zoom, por curso.")
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("crear", help="crea la carpeta de un curso")
    c.add_argument("curso", help="nombre de carpeta: minusculas y guiones, p. ej. big-data")
    c.add_argument("--nombre", help='nombre para mostrar, p. ej. "Big Data"')
    c.add_argument("--descripcion", help="descripcion del curso (se usa en los prompts)")
    c.set_defaults(f=cmd_crear)

    c = sub.add_parser("procesar", help="procesa lo nuevo o cambiado de un curso")
    c.add_argument("curso")
    c.add_argument("--clase", help="procesa solo esta clase (p. ej. 01); temas e indice se actualizan igual")
    c.add_argument("--reintentar-descargas", action="store_true", help="reintenta enlaces que fallaron")
    c.set_defaults(f=cmd_procesar)

    c = sub.add_parser("estado", help="muestra que esta hecho y que falta")
    c.add_argument("curso")
    c.set_defaults(f=cmd_estado)

    a = p.parse_args(argv)
    if hasattr(a, "curso") and not (RAIZ_CURSOS / a.curso).exists() and a.comando != "crear":
        sys.exit(f"No existe el curso '{a.curso}' en {RAIZ_CURSOS}")
    sys.exit(a.f(a))
