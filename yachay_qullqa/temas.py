"""Paso 7: temas del curso.

1. Cada clase cuyos apuntes cambiaron se asigna a temas (existentes o nuevos).
2. Solo se reescriben los temas cuyo conjunto de clases o apuntes cambio.
El catalogo de temas vive en estado.json -> "temas".
"""

import re

from . import gemini, prompts
from .progreso import Indicador
from .utiles import escribir_atomico, huella_json, slug


def _ruta(ctx, tema_id: str, t: dict):
    return ctx.curso.temas / f"{t['numero']:02d}-{tema_id}.md"


def actualizar(ctx, clases) -> None:
    reg = ctx.estado["temas"]
    catalogo: dict = reg["catalogo"]
    asignadas: dict = reg["asignadas"]
    generados: dict = reg["generados"]

    listas = {}
    for c in clases:
        etapa = ctx.estado["clases"].get(c.numero, {}).get("etapas", {}).get("apuntes")
        md = ctx.curso.apuntes / f"{c.nombre}.md"
        if etapa and md.exists():
            listas[c.numero] = (etapa["notas"], md)

    # Clases que ya no estan: se quitan de los temas.
    for numero in [n for n in asignadas if n not in listas]:
        for t in catalogo.values():
            t["clases"].pop(numero, None)
        del asignadas[numero]

    for numero in sorted(listas, key=int):
        h, md = listas[numero]
        if asignadas.get(numero) == h:
            continue
        ctx.log(f"\n== temas: asignando Clase{numero}")
        for t in catalogo.values():
            t["clases"].pop(numero, None)
        texto_catalogo = "\n".join(f"{i}: {t['nombre']} - {t['descripcion']}" for i, t in
                                   sorted(catalogo.items(), key=lambda x: x[1]["numero"])) or "(todavia no hay temas)"
        prompt = prompts.ASIGNAR_TEMAS.format(nombre=ctx.curso.nombre, descripcion=ctx.curso.descripcion,
                                              catalogo=texto_catalogo, clase=numero,
                                              apuntes=md.read_text(encoding="utf-8"))
        def asignar():
            with Indicador(f"Gemini identifica los temas de la Clase{numero}"):
                return gemini.extraer_json(gemini.generar(ctx.cliente, ctx.modelo, [gemini.bloque_texto(prompt)]))

        respuesta = gemini.con_reintentos(asignar, "asignar temas", ctx.log)
        for t in respuesta.get("temas", []):
            tema_id = t.get("id")
            if tema_id not in catalogo:
                tema_id = _id_nuevo(catalogo, t.get("nombre") or "tema")
                catalogo[tema_id] = {"nombre": t.get("nombre") or tema_id, "descripcion": t.get("descripcion", ""),
                                     "numero": max((x["numero"] for x in catalogo.values()), default=0) + 1,
                                     "clases": {}}
                ctx.log(f"  tema nuevo: {catalogo[tema_id]['nombre']}")
            catalogo[tema_id]["clases"][numero] = t.get("momentos") or []
        asignadas[numero] = h
        ctx.guardar()

    # Temas que se quedaron sin clases.
    for tema_id in [i for i, t in catalogo.items() if not t["clases"]]:
        _ruta(ctx, tema_id, catalogo[tema_id]).unlink(missing_ok=True)
        generados.pop(tema_id, None)
        del catalogo[tema_id]
    ctx.guardar()

    for tema_id, t in sorted(catalogo.items(), key=lambda x: x[1]["numero"]):
        ruta = _ruta(ctx, tema_id, t)
        h = huella_json({"nombre": t["nombre"], "desc": t["descripcion"], "prompts": prompts.VERSION,
                         "clases": {n: [asignadas[n], m] for n, m in t["clases"].items()}})
        if generados.get(tema_id) == h and ruta.exists():
            continue
        ctx.log(f"  tema: escribiendo {ruta.name}")
        partes = []
        for n in sorted(t["clases"], key=int):
            momentos = ", ".join(t["clases"][n]) or "sin marcas"
            partes.append(f"===== Clase{n} (el tema se trata en: {momentos}) =====\n"
                          + listas[n][1].read_text(encoding="utf-8"))
        prompt = prompts.TEMA.format(nombre=ctx.curso.nombre, descripcion=ctx.curso.descripcion,
                                     tema=t["nombre"], tema_desc=t["descripcion"], reglas=prompts.REGLAS,
                                     apuntes="\n\n".join(partes))
        def escribir_tema():
            with Indicador(f"Gemini escribe el tema \"{t['nombre']}\""):
                return gemini.generar(ctx.cliente, ctx.modelo, [gemini.bloque_texto(prompt)])

        md = gemini.con_reintentos(escribir_tema, "tema", ctx.log)
        md = re.sub(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", r"\1", md.strip(), flags=re.DOTALL)
        fuentes = ", ".join(f"[Clase{n}](../apuntes/Clase{n}.md)" for n in sorted(t["clases"], key=int))
        escribir_atomico(ruta, f"{md}\n\n---\n_Sintesis generada a partir de: {fuentes}._\n")
        generados[tema_id] = h
        ctx.guardar()


def _id_nuevo(catalogo: dict, nombre: str) -> str:
    base = slug(nombre, 50)
    tema_id, n = base, 2
    while tema_id in catalogo:
        tema_id, n = f"{base}-{n}", n + 1
    return tema_id
