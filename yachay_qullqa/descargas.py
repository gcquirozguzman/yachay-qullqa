"""Paso 3: intenta descargar cada enlace a materiales/ClaseNN/.

No pide contrasenas ni intenta saltarse permisos: si Google pide iniciar sesion
o el servidor responde 401/403, se registra como "sin permiso" y se sigue.
Las paginas web (consolas, blogs, documentacion) se registran como
"referencia" y no se descargan.
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .texto import EXTENSIONES

# Estados que aparecen en archivos_pendientes.md
DESCARGADO = "descargado"
SIN_PERMISO = "sin permiso"
ENLACE_ROTO = "enlace roto"
SIN_ENLACE = "mencionado sin enlace"
REFERENCIA = "referencia (no se descarga)"
CARPETA = "carpeta de Drive"
DEMASIADO_GRANDE = "demasiado grande"
ERROR = "error de descarga"

AGENTE = "Mozilla/5.0 (yachay-qullqa; descarga de materiales de clase)"
RE_ID_DOCS = re.compile(r"/d/([A-Za-z0-9_-]{10,})")
RE_EXT_FINAL = re.compile(rf"\.(?:{EXTENSIONES}|tar|gz|tgz|xml|html?)$", re.IGNORECASE)


def plan(url: str) -> dict:
    """Decide como descargar un enlace. Devuelve categoria, url_descarga y nombre sugerido."""
    u = urlparse(url)
    host = u.netloc.lower().removeprefix("www.")
    ruta = u.path
    m = RE_ID_DOCS.search(ruta)
    q = parse_qs(u.query)

    if host == "docs.google.com" and m:
        doc_id = m.group(1)
        if ruta.startswith("/document/"):
            return _p("Google Docs", f"https://docs.google.com/document/d/{doc_id}/export?format=docx", f"gdoc-{doc_id}.docx")
        if ruta.startswith("/spreadsheets/"):
            return _p("Google Sheets", f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=xlsx", f"gsheet-{doc_id}.xlsx")
        if ruta.startswith("/presentation/"):
            return _p("Google Slides", f"https://docs.google.com/presentation/d/{doc_id}/export/pptx", f"gslides-{doc_id}.pptx")
        if ruta.startswith("/forms/"):
            return _p("Google Forms", None, None)
    if host == "drive.google.com":
        if "/folders/" in ruta:
            return _p("Carpeta de Drive", None, None)
        drive_id = m.group(1) if m else (q.get("id") or [None])[0]
        if drive_id:
            return _p("Google Drive", _url_drive(drive_id), f"gdrive-{drive_id}")
    if host == "colab.research.google.com" and "/drive/" in ruta:
        colab_id = ruta.split("/drive/", 1)[1].split("/")[0]
        return _p("Notebook de Colab", _url_drive(colab_id), f"colab-{colab_id}.ipynb")
    if host == "github.com":
        partes = [p for p in ruta.split("/") if p]
        if len(partes) >= 5 and partes[2] == "blob":
            dueno, repo, _, ref, *resto = partes
            return _p("Archivo de GitHub", f"https://github.com/{dueno}/{repo}/raw/{ref}/{'/'.join(resto)}", resto[-1])
        if len(partes) >= 2:
            dueno, repo = partes[0], partes[1].removesuffix(".git")
            ref = partes[3] if len(partes) >= 4 and partes[2] == "tree" else "HEAD"
            return _p("Repositorio de GitHub", f"https://github.com/{dueno}/{repo}/archive/{ref}.zip", f"{dueno}-{repo}.zip")
    if RE_EXT_FINAL.search(ruta):
        return _p("Archivo", url, Path(unquote(ruta)).name)
    return _p("Pagina web", None, None)


def _p(categoria, url_descarga, nombre):
    return {"categoria": categoria, "url_descarga": url_descarga, "nombre": nombre}


def _url_drive(file_id: str) -> str:
    return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"


def _nombre_de_cabecera(cabecera: str | None) -> str | None:
    if not cabecera:
        return None
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", cabecera, re.IGNORECASE)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', cabecera, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _nombre_seguro(nombre: str) -> str:
    nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nombre).strip(" .")
    return nombre[:150] or "descarga"


def _destino_libre(carpeta: Path, nombre: str) -> Path:
    destino = carpeta / nombre
    n = 2
    while destino.exists():
        destino = carpeta / f"{Path(nombre).stem}-{n}{Path(nombre).suffix}"
        n += 1
    return destino


def _pide_login(resp: requests.Response) -> bool:
    final = urlparse(resp.url)
    return final.netloc.lower().startswith("accounts.google.com") or "ServiceLogin" in resp.url


def descargar(url: str, carpeta: Path, limite_mb: int, sesion: requests.Session | None = None) -> dict:
    """Intenta bajar un enlace. Nunca lanza excepcion: devuelve el resultado."""
    p = plan(url)
    res = {"url": url, **p, "estado": None, "archivo": None, "detalle": ""}
    if p["categoria"] == "Carpeta de Drive":
        res.update(estado=CARPETA, detalle="Las carpetas de Drive no se pueden bajar sin iniciar sesion.")
        return res
    if not p["url_descarga"]:
        res["estado"] = REFERENCIA
        return res

    sesion = sesion or requests.Session()
    try:
        with sesion.get(p["url_descarga"], stream=True, timeout=(15, 120),
                        headers={"User-Agent": AGENTE}, allow_redirects=True) as r:
            if _pide_login(r) or r.status_code in (401, 403):
                res.update(estado=SIN_PERMISO, detalle=f"HTTP {r.status_code}; pide iniciar sesion o no es publico")
                return res
            if r.status_code in (404, 410):
                res.update(estado=ENLACE_ROTO, detalle=f"HTTP {r.status_code}")
                return res
            if r.status_code >= 400:
                res.update(estado=ERROR, detalle=f"HTTP {r.status_code}")
                return res
            tipo = r.headers.get("Content-Type", "")
            google = p["categoria"].startswith(("Google", "Notebook"))
            if google and "text/html" in tipo:
                # Google devuelve una pagina HTML cuando el archivo no es publico.
                res.update(estado=SIN_PERMISO, detalle="Google devolvio una pagina en lugar del archivo")
                return res
            tam = int(r.headers.get("Content-Length") or 0)
            if tam > limite_mb * 1024**2:
                res.update(estado=DEMASIADO_GRANDE, detalle=f"{tam / 1024**2:.0f} MB (limite {limite_mb} MB)")
                return res

            nombre = _nombre_de_cabecera(r.headers.get("Content-Disposition")) or p["nombre"]
            nombre = _nombre_seguro(nombre or Path(urlparse(r.url).path).name)
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = _destino_libre(carpeta, nombre)
            parcial = destino.with_name(destino.name + ".parcial")
            leidos = 0
            with open(parcial, "wb") as f:
                for bloque in r.iter_content(1 << 16):
                    leidos += len(bloque)
                    if leidos > limite_mb * 1024**2:
                        break
                    f.write(bloque)
            if leidos > limite_mb * 1024**2:
                parcial.unlink(missing_ok=True)
                res.update(estado=DEMASIADO_GRANDE, detalle=f"supera {limite_mb} MB")
                return res
            parcial.replace(destino)
            res.update(estado=DESCARGADO, archivo=destino.name, detalle=f"{leidos / 1024:.0f} KB")
            return res
    except requests.RequestException as e:
        res.update(estado=ENLACE_ROTO, detalle=f"{type(e).__name__}: {e}"[:200])
        return res
