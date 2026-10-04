"""Linea de comandos.

  python -m yachay_qullqa           lista los cursos; al elegir uno, muestra su estado y procesa
  python -m yachay_qullqa crear <curso> --nombre "..." --descripcion "..."
  python -m yachay_qullqa procesar <curso> [--clase 01] [--reintentar-descargas]
  python -m yachay_qullqa estado <curso>
"""

import argparse
import sys

from . import estado as est, gemini, video
from .curso import RAIZ_CURSOS, RE_NOMBRE_CURSO, Curso
from .inventario import inventario
from .pipeline import procesar

ETAPAS = ("texto", "video", "capturas", "apuntes")


def revisar_clase(curso: Curso, estado: dict, c) -> str:
    """Por que hay que procesar una clase, o "" si esta al dia."""
    e = estado["clases"].get(c.numero)
    if not e:
        return "nueva"
    actuales = {p.name: est.huella_archivo(p) for p in c.archivos()}
    if actuales != e.get("archivos") or est.huellas_carpeta(curso.materiales / c.nombre) != e.get("materiales", {}):
        return "archivos nuevos/cambiados"
    if c.video and "apuntes" not in e.get("etapas", {}):
        return "incompleta"
    return ""


def _revisar_curso(carpeta) -> tuple[Curso | None, list[str]]:
    """Devuelve el curso (o None si no hay nada que procesar) y las lineas de detalle."""
    if not (carpeta / "curso.toml").exists():
        if not RE_NOMBRE_CURSO.match(carpeta.name):
            return None, ["Nombre de carpeta no valido (usa minusculas, numeros y guiones)."]
        Curso.crear(carpeta.name, carpeta.name, "")
        return None, ["CURSO NUEVO: se creo curso.toml y sus carpetas.",
                      "Escribe el nombre y la descripcion en curso.toml, pon los videos en clases/"
                      " y vuelve a ejecutar."]
    curso = Curso.abrir(carpeta.name)
    if not curso.descripcion.strip():
        return None, ["Falta la descripcion en curso.toml (Gemini la necesita)."]
    estado = est.cargar(curso)
    clases, desconocidos = inventario(curso)
    detalle, pendientes = [], 0
    for c in clases:
        motivo = revisar_clase(curso, estado, c)
        faltan = f" (falta {', '.join(c.faltantes())})" if c.faltantes() else ""
        pendientes += bool(motivo)
        detalle.append(f"{c.nombre}: {motivo or 'al dia'}{faltan}")
    for numero in sorted(set(estado["clases"]) - {c.numero for c in clases}, key=int):
        detalle.append(f"Clase{numero}: ya no esta en clases/")
        pendientes += 1
    detalle += [f"No reconocido: {p.name} (se esperan nombres como Clase01.mp4)" for p in desconocidos]
    resumen = f"{len(clases)} clases, " + (f"{pendientes} por procesar." if pendientes else "todo al dia.")
    return (curso if pendientes else None), detalle + [resumen]


def _preguntar(texto: str) -> str:
    try:
        return input(texto).replace("﻿", "").strip().lower()
    except EOFError:
        return ""


def cmd_todo(a) -> int:
    """Lista los cursos; al elegir uno muestra su estado y, si confirmas, procesa lo nuevo."""
    carpetas = []
    if RAIZ_CURSOS.exists():
        carpetas = sorted(d for d in RAIZ_CURSOS.iterdir() if d.is_dir() and not d.name.startswith("."))
    if not carpetas:
        print(f"No hay cursos en {RAIZ_CURSOS}.")
        return 0

    print("Cursos:")
    for n, carpeta in enumerate(carpetas, 1):
        print(f"  {n}. {carpeta.name}")
    eleccion = _preguntar("\nNumero del curso (Enter para salir): ")
    if not eleccion:
        return 0
    if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(carpetas):
        print("Ese numero no existe.")
        return 1

    carpeta = carpetas[int(eleccion) - 1]
    curso, detalle = _revisar_curso(carpeta)
    print(f"\n{carpeta.name}:")
    for linea in detalle:
        print(f"  {linea}")
    if not curso:
        return 0

    faltan = []
    if not video.ffmpeg_disponible():
        faltan.append(video.INSTRUCCIONES_FFMPEG)
    if not gemini.clave_disponible():
        faltan.append(gemini.INSTRUCCIONES_CLAVE)
    if faltan:
        print("\nNo se puede procesar todavia:")
        print("\n\n".join(faltan))
        return 1
    if _preguntar("\nProcesar lo pendiente? Los videos se envian a Gemini. [s/N]: ") not in ("s", "si", "sí"):
        print("No se proceso nada.")
        return 0
    return procesar(curso)


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
        cambios = revisar_clase(curso, estado, c) or "-"
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
    p.set_defaults(f=cmd_todo)
    sub = p.add_subparsers(dest="comando")

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
    if getattr(a, "curso", None) and not (RAIZ_CURSOS / a.curso).exists() and a.comando != "crear":
        sys.exit(f"No existe el curso '{a.curso}' en {RAIZ_CURSOS}")
    sys.exit(a.f(a))
