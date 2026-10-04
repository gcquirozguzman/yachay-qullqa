"""Paso 6: une los tramos y escribe apuntes/ClaseNN.md."""

from urllib.parse import quote

from .utiles import a_hhmmss, a_segundos

LISTAS = ("desarrollo", "codigo", "pasos", "tareas", "materiales", "dudas")


def _seg(tiempo) -> int | None:
    try:
        return a_segundos(tiempo)
    except (ValueError, TypeError):
        return None


def desplazar(notas: dict, segundos: float) -> dict:
    """Suma el inicio del tramo a todas las marcas de tiempo."""
    salida = dict(notas)
    for clave in LISTAS:
        items = []
        for item in notas.get(clave) or []:
            item = dict(item)
            s = _seg(item.get("tiempo"))
            item["tiempo"] = a_hhmmss(s + segundos) if s is not None else f"[ILEGIBLE] {item.get('tiempo', '')}".strip()
            items.append(item)
        salida[clave] = items
    return salida


def recortar_antes_de(notas: dict, segundos: float, tolerancia: int = 5) -> dict:
    """Quita lo anterior a `segundos` (tiempos ya absolutos): es el solape con el
    tramo previo. Lo que tiene la hora [ILEGIBLE] se conserva."""
    salida = dict(notas)
    for clave in LISTAS:
        salida[clave] = [item for item in notas.get(clave) or []
                         if (s := _seg(item.get("tiempo"))) is None or s >= segundos - tolerancia]
    return salida


def unir(tramos: list[dict]) -> dict:
    """tramos: [{'inicio': s, 'notas': {...}}] con tiempos ya desplazados."""
    if len(tramos) == 1:
        return tramos[0]["notas"]
    titulos, resumenes = [], []
    for i, t in enumerate(tramos, 1):
        n = t["notas"]
        if n.get("titulo") and n["titulo"] not in titulos:
            titulos.append(n["titulo"])
        if n.get("resumen"):
            resumenes.append(f"**Tramo {i} (desde {a_hhmmss(t['inicio'])}).** {n['resumen'].strip()}")
    unidas = {"titulo": " · ".join(titulos), "resumen": "\n\n".join(resumenes)}
    for clave in LISTAS:
        unidas[clave] = [item for t in tramos for item in t["notas"].get(clave) or []]
    return unidas


def nombre_captura(indice: int, tiempo: str) -> str:
    return f"paso-{indice:02d}_{tiempo.replace(':', '-').replace(' ', '')}.jpg"


def _celda(texto) -> str:
    return " ".join(str(texto or "").split()).replace("|", "\\|")


def _verificacion(paso: dict) -> str:
    v = paso.get("verificacion")
    if not v:
        return "Verificacion: pendiente (no hay captura)"
    if v["estado"] == "coincide":
        return f"Verificado con la captura: coincide. _{v.get('observacion', '')}_"
    if v["estado"] == "corregido":
        antes = f"{paso.get('accion_original', '')} {paso.get('valores_original', '')}".strip()
        return f"**Corregido segun la captura.** Antes decia: \"{antes}\". _{v.get('observacion', '')}_"
    return f"**Atencion: la captura no muestra este paso; revisa el video cerca de esa hora.** _{v.get('observacion', '')}_"


def render(clase: str, curso_nombre: str, notas: dict, fuentes: dict, materiales: list[dict],
           menciones: list[dict]) -> str:
    l = [f"# Clase{clase} — {notas.get('titulo') or '[ILEGIBLE]'}", ""]
    l.append(f"> Curso: {curso_nombre}. Fuentes: {', '.join(fuentes['usadas'])}.")
    if fuentes.get("faltan"):
        l.append(f"> Faltan: {', '.join(fuentes['faltan'])}.")
    l.append("> Las marcas de tiempo (HH:MM:SS) se refieren a la grabacion completa.")
    l += ["", "## Resumen", "", (notas.get("resumen") or "[ILEGIBLE]").strip(), ""]

    l += ["## Desarrollo cronologico", ""]
    for b in notas.get("desarrollo") or []:
        l += [f"### [{b.get('tiempo')}] {b.get('titulo', '')}".rstrip(), "", (b.get("contenido") or "").strip(), ""]

    l += ["## Comandos y codigo", ""]
    codigo = notas.get("codigo") or []
    if not codigo:
        l += ["_No se registraron comandos ni codigo._", ""]
    for c in codigo:
        l += [f"**[{c.get('tiempo')}]** {c.get('contexto', '')}".rstrip(), "",
              f"```{c.get('lenguaje', '')}", (c.get("codigo") or "").rstrip("\n"), "```", ""]

    l += ["## Pasos de configuracion", ""]
    pasos = notas.get("pasos") or []
    if not pasos:
        l += ["_No se detectaron pasos de configuracion._", ""]
    for i, p in enumerate(pasos, 1):
        plat = f" · {p['plataforma']}" if p.get("plataforma") else ""
        l.append(f"{i}. **[{p.get('tiempo')}]{plat}** — {p.get('accion', '')}")
        if p.get("valores"):
            l.append(f"   - Valores: {p['valores']}")
        l.append(f"   - {_verificacion(p)}")
        if p.get("captura"):
            l += ["", f"   ![Paso {i} ({p.get('tiempo')})](../capturas/Clase{clase}/{p['captura']})"]
        l.append("")

    l += ["## Tareas y entregables", ""]
    tareas = notas.get("tareas") or []
    l += [f"- **[{t.get('tiempo')}]** {t.get('descripcion', '')}"
          + (f" — {t['fecha_o_condicion']}" if t.get("fecha_o_condicion") else "") for t in tareas] or [
        "_No se mencionaron tareas._"]
    l.append("")

    l += ["## Materiales y enlaces", ""]
    if materiales:
        l += ["| Hora | Donde | Material | Estado | Archivo |", "|---|---|---|---|---|"]
        for m in materiales:
            arch = f"[{m['archivo']}](../materiales/Clase{clase}/{quote(m['archivo'])})" if m.get("archivo") else ""
            l.append(f"| {m.get('tiempo', '')} | {_celda(m.get('donde'))} | {_celda(m.get('material'))} "
                     f"| {_celda(m.get('estado'))} | {arch} |")
    else:
        l.append("_No se encontraron materiales ni enlaces._")
    l.append("")
    if menciones:
        l += ["<details><summary>Todas las menciones a archivos o materiales en el chat y la transcripcion "
              f"({len(menciones)})</summary>", ""]
        for m in menciones:
            fuente = "chat" if m["fuente"] == "chat" else "transcripcion"
            l.append(f"- [{m['tiempo']}] {fuente}, linea {m['linea']} — {m['tipo']} «{m['valor']}»: {_celda(m['contexto'])}")
        l += ["", "</details>", ""]

    l += ["## Dudas", ""]
    dudas = notas.get("dudas") or []
    l += [f"- **[{d.get('tiempo')}]** {d.get('detalle', '')}" for d in dudas] or ["_Sin dudas registradas._"]
    l.append("")
    return "\n".join(l)
