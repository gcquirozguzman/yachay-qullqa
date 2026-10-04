"""Orquesta el procesamiento de un curso, clase por clase y en orden numerico.

Cada etapa calcula una "huella" de sus entradas y la compara con estado.json:
si no cambio nada, se salta. Los resultados intermedios quedan en .trabajo/,
asi que un corte a mitad de camino se retoma donde quedo.
"""

import shutil
from pathlib import Path

from . import apuntes, descargas, estado as est, gemini, indice, prompts, temas, texto, video
from .curso import Curso
from .inventario import Clase, inventario
from .progreso import Indicador
from .utiles import (a_hhmmss, a_segundos, escribir_atomico, escribir_json, huella_json, leer_json,
                     sha256_archivo, sha256_texto)

TAM_LOTE_VERIFICACION = 6


class Contexto:
    """Lo que comparten las etapas: curso, estado, cliente de Gemini y herramientas."""

    def __init__(self, curso: Curso, log=print):
        self.curso = curso
        self.log = log
        self.estado = est.cargar(curso)
        self.ffmpeg = video.ffmpeg_disponible()
        self.clave = gemini.clave_disponible()
        self._cliente = None

    @property
    def cliente(self):
        if self._cliente is None:
            self._cliente = gemini.crear_cliente()
        return self._cliente

    @property
    def modelo(self) -> str:
        return self.curso.config["modelo"]

    def guardar(self):
        est.guardar(self.curso, self.estado)

    def trabajo(self, clase: Clase) -> Path:
        return self.curso.trabajo / clase.nombre


# ---------------------------------------------------------------- etapas por clase

def etapa_texto(ctx: Contexto, clase: Clase) -> dict:
    archivo = ctx.trabajo(clase) / "texto.json"
    h = huella_json([texto.VERSION_EXTRACCION] + [est.huella_archivo(p) if p else None
                                                  for p in (clase.chat, clase.transcripcion)])
    if est.etapa_al_dia(ctx.estado, clase.numero, "texto", h) and archivo.exists():
        return leer_json(archivo)
    datos = texto.extraer(clase.chat, clase.transcripcion)
    escribir_json(archivo, datos)
    est.marcar_etapa(ctx.estado, clase.numero, "texto", h)
    ctx.guardar()
    ctx.log(f"  texto: {len(datos['enlaces'])} enlaces, {len(datos['menciones'])} menciones")
    return datos


def etapa_descargas(ctx: Contexto, clase: Clase, datos_texto: dict, reintentar: bool) -> dict:
    """Cada enlace se intenta una sola vez; con reintentar=True se repiten los que fallaron."""
    archivo = ctx.trabajo(clase) / "descargas.json"
    hechas: dict = leer_json(archivo, {})
    carpeta = ctx.curso.materiales / clase.nombre
    limite = ctx.curso.config["limite_descarga_mb"]
    reintentables = {descargas.ENLACE_ROTO, descargas.SIN_PERMISO, descargas.ERROR}
    nuevas = 0
    for enlace in datos_texto["enlaces"]:
        url = enlace["valor"]
        previo = hechas.get(url)
        if previo and not (reintentar and previo["estado"] in reintentables):
            continue
        res = descargas.descargar(url, carpeta, limite)
        hechas[url] = res
        escribir_json(archivo, hechas)  # se guarda tras cada enlace: un corte no pierde lo hecho
        nuevas += 1
        detalle = f" -> {res['archivo']}" if res.get("archivo") else (f" ({res['detalle']})" if res["detalle"] else "")
        ctx.log(f"  descarga: {res['estado']}: {url}{detalle}")
    if not nuevas:
        escribir_json(archivo, hechas)
    return hechas


def _apoyos(clase: Clase, inicio: float, fin: float) -> tuple[str, list[dict]]:
    """Texto que explica los apoyos y los bloques con la transcripcion y el chat del tramo."""
    explicacion, bloques = [], []
    if clase.transcripcion:
        cues = texto.leer_vtt(clase.transcripcion)
        tramo = texto.vtt_compacto(cues, int(inicio), int(fin), restar=int(inicio))
        if tramo:
            explicacion.append(prompts.APOYO_VTT)
            bloques.append(gemini.bloque_texto("TRANSCRIPCION AUTOMATICA (tiempos relativos a este video):\n" + tramo))
    if clase.chat:
        lineas = []
        for m in texto.leer_chat(clase.chat):
            s = a_segundos(m.tiempo)
            if inicio <= s <= fin:
                lineas.append(f"[{a_hhmmss(s - inicio)}] {m.texto}")
        if lineas:
            explicacion.append(prompts.APOYO_CHAT)
            bloques.append(gemini.bloque_texto("CHAT (tiempos relativos a este video; sin autores):\n" + "\n".join(lineas)))
    if not explicacion:
        explicacion.append("No hay transcripcion ni chat de apoyo: usa solo el video.")
    return "\n\n".join(explicacion), bloques


def etapa_video(ctx: Contexto, clase: Clase) -> dict | None:
    cfg = ctx.curso.config
    trabajo = ctx.trabajo(clase) / "video"
    final = trabajo / "notas_video.json"
    h = huella_json({
        "video": est.huella_archivo(clase.video),
        "vtt": est.huella_archivo(clase.transcripcion) if clase.transcripcion else None,
        "chat": est.huella_archivo(clase.chat) if clase.chat else None,
        "curso": [ctx.curso.nombre, ctx.curso.descripcion], "modelo": ctx.modelo,
        "prompts": prompts.VERSION, "tramo": cfg["duracion_tramo_min"], "limite": cfg["limite_bytes"],
    })
    if est.etapa_al_dia(ctx.estado, clase.numero, "video", h) and final.exists():
        return leer_json(final)

    plan_ruta = trabajo / "plan.json"
    plan = leer_json(plan_ruta)
    if not plan or plan.get("huella") != h:
        # Entradas distintas: se descarta lo intermedio y se empieza de cero.
        shutil.rmtree(trabajo, ignore_errors=True)
        dur = video.duracion(clase.video)
        seg = video.segundos_por_tramo(clase.video.stat().st_size, dur, cfg["duracion_tramo_min"], cfg["limite_bytes"])
        if seg is None:
            tramos = [{"archivo": str(clase.video), "inicio": 0.0, "fin": dur}]
        else:
            ctx.log(f"  video: {a_hhmmss(dur)}; se divide en tramos de hasta {a_hhmmss(seg)}")
            with Indicador("Dividiendo el video"):
                tramos = video.dividir(clase.video, trabajo / "partes", seg)
        plan = {"huella": h, "duracion": dur, "tramos": tramos}
        escribir_json(plan_ruta, plan)

    total = len(plan["tramos"])
    for i, tramo in enumerate(plan["tramos"]):
        salida = trabajo / f"tramo_{i:02d}.json"
        if salida.exists():
            continue
        ctx.log(f"  video: tramo {i + 1}/{total} ({a_hhmmss(tramo['inicio'])} - {a_hhmmss(tramo['fin'])})")
        previo = leer_json(trabajo / f"tramo_{i - 1:02d}.json")["notas"] if i else None
        notas = gemini.con_reintentos(lambda: _procesar_tramo(ctx, clase, trabajo, i, total, tramo, previo),
                                      f"tramo {i + 1}", ctx.log)
        notas = apuntes.desplazar(notas, tramo["inicio"])
        # Lo anterior a "desde" es el solape con el tramo previo: ya esta en sus apuntes.
        notas = apuntes.recortar_antes_de(notas, tramo.get("desde", tramo["inicio"]))
        escribir_json(salida, {"inicio": tramo.get("desde", tramo["inicio"]), "notas": notas})

    unidas = apuntes.unir([leer_json(trabajo / f"tramo_{i:02d}.json") for i in range(total)])
    unidas["duracion"] = a_hhmmss(plan["duracion"])
    escribir_json(final, unidas)
    shutil.rmtree(trabajo / "partes", ignore_errors=True)
    est.marcar_etapa(ctx.estado, clase.numero, "video", h, tramos=total)
    ctx.guardar()
    return unidas


def _texto_tramo(i: int, total: int, tramo: dict, previo: dict | None) -> str:
    if total == 1:
        return ""
    texto = prompts.TRAMO.format(n=i + 1, total=total, inicio=a_hhmmss(tramo["inicio"]))
    if previo:
        desde = tramo.get("desde", tramo["inicio"]) - tramo["inicio"]
        desarrollo = previo.get("desarrollo") or []
        texto += "\n\n" + prompts.TRAMO_SOLAPE.format(
            desde=a_hhmmss(desde), resumen=(previo.get("resumen") or "[sin resumen]").strip(),
            ultimo=desarrollo[-1].get("titulo", "") if desarrollo else "[no indicado]")
    return texto


def _procesar_tramo(ctx: Contexto, clase: Clase, trabajo: Path, i: int, total: int, tramo: dict,
                    previo: dict | None) -> dict:
    cliente = ctx.cliente
    pendiente_ruta = trabajo / f"tramo_{i:02d}.pendiente.json"
    pendiente = leer_json(pendiente_ruta, {})

    archivo = gemini.archivo_activo(cliente, pendiente["archivo"]) if pendiente.get("archivo") else None
    if archivo is None:
        ruta = Path(tramo["archivo"])
        with Indicador(f"Subiendo tramo {i + 1}/{total} a Gemini ({ruta.stat().st_size / 1024**2:.0f} MB)"):
            archivo = gemini.subir_video(cliente, ruta)
        pendiente = {"archivo": archivo.name}
        escribir_json(pendiente_ruta, pendiente)

    explicacion, bloques = _apoyos(clase, tramo["inicio"], tramo["fin"])
    prompt = prompts.APUNTES.format(nombre=ctx.curso.nombre, descripcion=ctx.curso.descripcion,
                                    tramo=_texto_tramo(i, total, tramo, previo), apoyos=explicacion,
                                    reglas=prompts.REGLAS)
    entrada = [gemini.bloque_video(archivo), gemini.bloque_texto(prompt), *bloques]

    def al_crear(id_interaccion):
        pendiente["interaccion"] = id_interaccion
        escribir_json(pendiente_ruta, pendiente)

    with Indicador(f"Gemini esta analizando el tramo {i + 1}/{total}"):
        respuesta = gemini.generar(cliente, ctx.modelo, entrada, pendiente.get("interaccion"), al_crear)
    escribir_atomico(trabajo / f"tramo_{i:02d}.respuesta.txt", respuesta)
    try:
        notas = gemini.extraer_json(respuesta)
    except ValueError:
        # Respuesta sin JSON valido: se olvida la interaccion para pedirla de nuevo.
        pendiente.pop("interaccion", None)
        escribir_json(pendiente_ruta, pendiente)
        raise
    pendiente_ruta.unlink(missing_ok=True)
    gemini.borrar_archivo(cliente, archivo.name)
    return notas


def etapa_capturas(ctx: Contexto, clase: Clase, notas: dict) -> dict:
    """Extrae una captura por paso, la compara con el paso usando Gemini y corrige."""
    trabajo = ctx.trabajo(clase)
    final = trabajo / "notas_final.json"
    desfase = ctx.curso.config["desfase_captura_s"]
    h = huella_json({"notas": huella_json(notas), "video": est.huella_archivo(clase.video),
                     "desfase": desfase, "prompts": prompts.VERSION})
    carpeta = ctx.curso.capturas / clase.nombre
    if est.etapa_al_dia(ctx.estado, clase.numero, "capturas", h) and final.exists():
        return leer_json(final)

    notas = {**notas, "pasos": [dict(p) for p in notas.get("pasos") or []]}
    esperadas = set()
    for i, p in enumerate(notas["pasos"], 1):
        try:
            s = a_segundos(p.get("tiempo"))
        except (ValueError, TypeError):
            continue
        nombre = apuntes.nombre_captura(i, p["tiempo"])
        esperadas.add(nombre)
        if not (carpeta / nombre).exists():
            video.captura(clase.video, s + desfase, carpeta / nombre)
        p["captura"] = nombre
    # Capturas de una version anterior de los apuntes que ya no corresponden a ningun paso.
    if carpeta.exists():
        for viejo in carpeta.glob("paso-*.jpg"):
            if viejo.name not in esperadas:
                viejo.unlink()
    ctx.log(f"  capturas: {len(esperadas)} pasos")

    _verificar(ctx, clase, notas["pasos"], carpeta)
    escribir_json(final, notas)
    est.marcar_etapa(ctx.estado, clase.numero, "capturas", h, pasos=len(notas["pasos"]))
    ctx.guardar()
    return notas


def _verificar(ctx: Contexto, clase: Clase, pasos: list[dict], carpeta: Path) -> None:
    """Compara cada captura con su paso. Guarda cada resultado para no repetirlo."""
    cache_ruta = ctx.trabajo(clase) / "verificacion.json"
    cache = leer_json(cache_ruta, {})
    claves = {}
    por_verificar = []
    for i, p in enumerate(pasos):
        if not p.get("captura"):
            continue
        clave = sha256_texto(sha256_archivo(carpeta / p["captura"]) + p.get("accion", "") + p.get("valores", ""))
        claves[i] = clave
        if clave not in cache:
            por_verificar.append(i)

    for inicio in range(0, len(por_verificar), TAM_LOTE_VERIFICACION):
        lote = por_verificar[inicio : inicio + TAM_LOTE_VERIFICACION]
        lista = "\n".join(
            f"{n}. [{pasos[i]['tiempo']}] {pasos[i].get('plataforma', '')}: {pasos[i].get('accion', '')}"
            f" | valores: {pasos[i].get('valores', '') or '-'}" for n, i in enumerate(lote, 1))
        entrada = [gemini.bloque_texto(prompts.VERIFICAR.format(reglas=prompts.REGLAS, pasos=lista))]
        for n, i in enumerate(lote, 1):
            entrada += [gemini.bloque_texto(f"Captura del paso {n}:"), gemini.bloque_imagen(carpeta / pasos[i]["captura"])]
        def pedir():
            with Indicador(f"Gemini revisa las capturas {inicio + 1}-{inicio + len(lote)} de {len(por_verificar)}"):
                return gemini.extraer_json(gemini.generar(ctx.cliente, ctx.modelo, entrada))

        respuesta = gemini.con_reintentos(pedir, "verificacion", ctx.log)
        for r in respuesta.get("resultados", []):
            n = int(r.get("indice", 0))
            if 1 <= n <= len(lote):
                cache[claves[lote[n - 1]]] = r
        escribir_json(cache_ruta, cache)

    for i, clave in claves.items():
        r = cache.get(clave)
        if not r:
            continue
        p = pasos[i]
        p["verificacion"] = {"estado": r.get("estado", "no_visible"), "observacion": r.get("observacion", "")}
        if r.get("estado") == "corregido":
            p["accion_original"], p["valores_original"] = p.get("accion", ""), p.get("valores", "")
            p["accion"] = r.get("accion") or p.get("accion", "")
            p["valores"] = r.get("valores") or p.get("valores", "")


def materiales_de_clase(ctx: Contexto, clase: Clase, datos_texto: dict, hechas: dict, notas: dict | None) -> list[dict]:
    """Filas de materiales: enlaces (con su descarga), menciones sin enlace y
    archivos agregados a mano en materiales/ClaseNN/."""
    filas = []
    for e in datos_texto["enlaces"]:
        d = hechas.get(e["valor"], {})
        filas.append({"tiempo": e["tiempo"], "donde": f"{_fuente(e)} {e['tiempo']} (linea {e['linea']})",
                      "material": e["valor"], "estado": d.get("estado", "pendiente de descarga"),
                      "detalle": d.get("detalle", ""), "archivo": d.get("archivo")})
    for m in datos_texto["menciones"]:
        # Las palabras sueltas de la transcripcion ("archivo", "documento") son demasiadas
        # y casi siempre genericas: van al detalle de los apuntes, no a esta tabla.
        if m["fuente"] == "transcripcion" and m["tipo"] != "nombre_archivo":
            continue
        filas.append({"tiempo": m["tiempo"], "donde": f"{_fuente(m)} {m['tiempo']} (linea {m['linea']})",
                      "material": f"{m['valor']} — «{m['contexto']}»" if m["tipo"] != "nombre_archivo" else m["valor"],
                      "estado": descargas.SIN_ENLACE, "detalle": "", "archivo": None})
    for m in (notas or {}).get("materiales") or []:
        nombre = m.get("nombre_o_enlace") or ""
        if nombre.startswith(("http://", "https://")) and nombre in hechas:
            continue  # ya esta como enlace del chat
        filas.append({"tiempo": m.get("tiempo", ""), "donde": f"video {m.get('tiempo', '')}",
                      "material": f"{m.get('descripcion', '')}" + (f" ({nombre})" if nombre else ""),
                      "estado": descargas.SIN_ENLACE, "detalle": "", "archivo": None})
    bajados = {d.get("archivo") for d in hechas.values()}
    for nombre in est.huellas_carpeta(ctx.curso.materiales / clase.nombre):
        if nombre not in bajados:
            filas.append({"tiempo": "", "donde": "agregado a mano", "material": nombre,
                          "estado": "agregado a mano", "detalle": "", "archivo": nombre})
    filas.sort(key=lambda f: (f["tiempo"] == "", f["tiempo"]))
    return filas


def _fuente(h: dict) -> str:
    return "chat" if h["fuente"] == "chat" else "transcripcion"


def etapa_apuntes(ctx: Contexto, clase: Clase, notas: dict, datos_texto: dict, hechas: dict) -> None:
    fuentes = {"usadas": [f"video (Gemini, {ctx.modelo})"], "faltan": [f for f in clase.faltantes() if "video" not in f]}
    if clase.chat:
        fuentes["usadas"].append("chat de Zoom")
    if clase.transcripcion:
        fuentes["usadas"].append("transcripcion automatica de Zoom (solo como apoyo)")
    filas = materiales_de_clase(ctx, clase, datos_texto, hechas, notas)
    md = apuntes.render(clase.numero, ctx.curso.nombre, notas, fuentes, filas, datos_texto["menciones"])
    destino = ctx.curso.apuntes / f"{clase.nombre}.md"
    if not destino.exists() or destino.read_text(encoding="utf-8") != md:
        escribir_atomico(destino, md)
        ctx.log(f"  apuntes: {destino.relative_to(ctx.curso.carpeta)}")
    est.marcar_etapa(ctx.estado, clase.numero, "apuntes", huella_json(md),
                     notas=huella_json(notas), titulo=notas.get("titulo", ""), duracion=notas.get("duracion", ""))
    ctx.guardar()


# ---------------------------------------------------------------- curso completo

def procesar_clase(ctx: Contexto, clase: Clase, reintentar_descargas: bool, etiqueta: str = "") -> None:
    ctx.log(f"\n== {etiqueta}{clase.nombre}")
    c = est.clase(ctx.estado, clase.numero)
    c["archivos"] = {p.name: est.huella_archivo(p) for p in clase.archivos()}
    c["materiales"] = est.huellas_carpeta(ctx.curso.materiales / clase.nombre)
    if clase.faltantes():
        ctx.log(f"  aviso: falta {', '.join(clase.faltantes())}")

    datos_texto = etapa_texto(ctx, clase)
    hechas = etapa_descargas(ctx, clase, datos_texto, reintentar_descargas)

    if not clase.video:
        ctx.log("  sin video: no se generan apuntes")
        return
    faltan = ([] if ctx.ffmpeg else ["ffmpeg"]) + ([] if ctx.clave else ["GEMINI_API_KEY"])
    if faltan:
        c["pendiente"] = f"falta {' y '.join(faltan)}"
        ctx.guardar()
        ctx.log(f"  video, capturas y apuntes: PENDIENTES (falta {' y '.join(faltan)})")
        return
    c.pop("pendiente", None)

    notas = etapa_video(ctx, clase)
    notas = etapa_capturas(ctx, clase, notas)
    etapa_apuntes(ctx, clase, notas, datos_texto, hechas)


def procesar(curso: Curso, numero: str | None = None, reintentar_descargas: bool = False, log=print) -> int:
    ctx = Contexto(curso, log)
    clases, desconocidos = inventario(curso)
    if not clases:
        log(f"No hay clases en {curso.clases}. Copia ahi los archivos ClaseNN.mp4/.txt/.vtt.")
        return 1
    for p in desconocidos:
        log(f"aviso: no se reconoce {p.name} (se esperan nombres como Clase01.mp4)")
    if not ctx.ffmpeg:
        log("aviso: " + video.INSTRUCCIONES_FFMPEG)
    if not ctx.clave:
        log("aviso: " + gemini.INSTRUCCIONES_CLAVE)
    if numero:
        numero = f"{int(numero):02d}"
        clases_a_procesar = [c for c in clases if c.numero == numero]
        if not clases_a_procesar:
            log(f"No existe la Clase{numero} en {curso.clases}")
            return 1
    else:
        clases_a_procesar = clases

    errores = []
    for k, clase in enumerate(clases_a_procesar, 1):
        try:
            procesar_clase(ctx, clase, reintentar_descargas, f"[{k}/{len(clases_a_procesar)}] ")
        except KeyboardInterrupt:
            ctx.guardar()
            log("\nInterrumpido. Vuelve a ejecutar el mismo comando para continuar donde quedo.")
            raise
        except Exception as e:  # una clase con error no detiene a las demas
            est.clase(ctx.estado, clase.numero)["error"] = f"{type(e).__name__}: {e}"[:500]
            ctx.guardar()
            errores.append(clase.nombre)
            log(f"  ERROR en {clase.nombre}: {e}")

    if ctx.clave:
        try:
            temas.actualizar(ctx, clases)
        except Exception as e:
            errores.append("temas")
            log(f"ERROR al actualizar temas: {e}")
    indice.escribir(ctx, clases)
    log(f"\nListo. Indice: {curso.indice}. Pendientes: {curso.pendientes}.")
    if errores:
        log(f"Con errores: {', '.join(errores)}. Vuelve a ejecutar para reintentar.")
    return 1 if errores else 0
