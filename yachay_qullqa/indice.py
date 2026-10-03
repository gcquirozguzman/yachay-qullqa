"""Paso 8 e indice: INDICE.md y archivos_pendientes.md (siempre se regeneran; son baratos)."""

from urllib.parse import quote

from . import descargas
from .utiles import escribir_atomico, leer_json

ACCIONES = {
    descargas.DESCARGADO: "Nada; ya esta en materiales/{clase}/.",
    descargas.SIN_PERMISO: "Abrelo con tu cuenta o pide acceso; guardalo en materiales/{clase}/.",
    descargas.ENLACE_ROTO: "Pide el archivo al docente o a la coordinacion; guardalo en materiales/{clase}/.",
    descargas.SIN_ENLACE: "Buscalo (Canvas, correo) o pidelo; si lo consigues, guardalo en materiales/{clase}/.",
    descargas.CARPETA: "Abre la carpeta y descarga lo que necesites a materiales/{clase}/.",
    descargas.REFERENCIA: "Ninguna: es una pagina de consulta.",
    descargas.DEMASIADO_GRANDE: "Bajalo a mano solo si lo necesitas.",
    descargas.ERROR: "Vuelve a intentarlo con: procesar --reintentar-descargas.",
    "agregado a mano": "Nada; lo agregaste tu.",
    "pendiente de descarga": "Ejecuta procesar de nuevo.",
}


def _celda(texto) -> str:
    return " ".join(str(texto or "").split()).replace("|", "\\|")


def escribir(ctx, clases) -> None:
    from .pipeline import materiales_de_clase  # evita import circular

    curso = ctx.curso
    reg = ctx.estado["temas"]
    l = [f"# {curso.nombre}", "", curso.descripcion, "",
         "> Indice generado por yachay-qullqa. Empieza por los temas; ve a los apuntes de cada",
         "> clase para el detalle cronologico. Las citas usan (ClaseNN, HH:MM:SS).", "",
         "## Temas", ""]
    if reg["catalogo"]:
        for tema_id, t in sorted(reg["catalogo"].items(), key=lambda x: x[1]["numero"]):
            cl = ", ".join(f"Clase{n}" for n in sorted(t["clases"], key=int))
            l.append(f"- [{t['nombre']}](temas/{t['numero']:02d}-{tema_id}.md) — {t['descripcion']} _({cl})_")
    else:
        l.append("_Todavia no hay temas (se generan cuando hay apuntes de clases)._")
    l += ["", "## Clases", "", "| Clase | Titulo | Duracion | Temas | Estado |", "|---|---|---|---|---|"]

    filas_pend = []
    for c in clases:
        e = ctx.estado["clases"].get(c.numero, {})
        ap = e.get("etapas", {}).get("apuntes")
        temas_clase = [t["nombre"] for t in sorted(reg["catalogo"].values(), key=lambda t: t["numero"])
                       if c.numero in t["clases"]]
        if ap and (curso.apuntes / f"{c.nombre}.md").exists():
            enlace, estado_txt = f"[{c.nombre}](apuntes/{c.nombre}.md)", "apuntes listos"
        else:
            enlace, estado_txt = c.nombre, e.get("pendiente") or "sin procesar"
        if e.get("error"):
            estado_txt = f"error: {e['error'][:80]}"
        if c.faltantes():
            estado_txt += f"; falta {', '.join(c.faltantes())}"
        l.append(f"| {enlace} | {_celda((ap or {}).get('titulo', ''))} | {(ap or {}).get('duracion', '')} "
                 f"| {_celda(', '.join(temas_clase))} | {_celda(estado_txt)} |")

        trabajo = ctx.trabajo(c)
        datos_texto = leer_json(trabajo / "texto.json")
        if datos_texto is None:
            continue
        hechas = leer_json(trabajo / "descargas.json", {})
        notas = leer_json(trabajo / "notas_final.json")
        for f in materiales_de_clase(ctx, c, datos_texto, hechas, notas):
            filas_pend.append((c.nombre, f))

    l += ["", "Otros archivos: [archivos_pendientes.md](archivos_pendientes.md)", ""]
    escribir_atomico(curso.indice, "\n".join(l))

    orden = {descargas.SIN_PERMISO: 0, descargas.ENLACE_ROTO: 0, descargas.ERROR: 0, descargas.CARPETA: 1,
             descargas.SIN_ENLACE: 2, descargas.DEMASIADO_GRANDE: 3, "pendiente de descarga": 3,
             descargas.DESCARGADO: 4, "agregado a mano": 4, descargas.REFERENCIA: 5}
    resumen = {}
    for _, f in filas_pend:
        resumen[f["estado"]] = resumen.get(f["estado"], 0) + 1
    p = [f"# Archivos pendientes — {curso.nombre}", "",
         "Material mencionado en las clases y en que estado esta. Lo que consigas a mano,",
         "guardalo en `materiales/ClaseNN/` y vuelve a ejecutar `procesar`.", ""]
    p += [f"- **{k}**: {v}" for k, v in sorted(resumen.items(), key=lambda x: orden.get(x[0], 9))] or ["_Nada registrado._"]
    p += ["", "| Clase | Archivo o enlace | Donde se menciono | Estado | Que debes hacer |", "|---|---|---|---|---|"]
    for nombre_clase, f in filas_pend:
        estado_txt = f["estado"] + (f" ({f['detalle']})" if f.get("detalle") and f["estado"] != descargas.DESCARGADO else "")
        accion = ACCIONES.get(f["estado"], "Revisalo.").format(clase=nombre_clase)
        if f.get("archivo") and f["estado"] == descargas.DESCARGADO:
            accion = f"Nada; esta en [materiales/{nombre_clase}/{f['archivo']}](materiales/{nombre_clase}/{quote(f['archivo'])})."
        p.append(f"| {nombre_clase} | {_celda(f['material'])} | {_celda(f['donde'])} | {_celda(estado_txt)} | {accion} |")
    p.append("")
    escribir_atomico(curso.pendientes, "\n".join(p))
