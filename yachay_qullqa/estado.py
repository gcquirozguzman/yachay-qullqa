"""estado.json: registro de lo ya procesado, para no repetir trabajo y poder retomar."""

from pathlib import Path

from .curso import Curso
from .utiles import escribir_json, leer_json, sha256_archivo

VERSION_ESTADO = 1


def cargar(curso: Curso) -> dict:
    estado = leer_json(curso.estado, None) or {}
    estado.setdefault("version", VERSION_ESTADO)
    estado.setdefault("clases", {})
    estado.setdefault("temas", {"catalogo": {}, "asignadas": {}, "generados": {}})
    return estado


def guardar(curso: Curso, estado: dict) -> None:
    escribir_json(curso.estado, estado)


def huella_archivo(ruta: Path) -> str:
    """Videos: tamano + fecha (calcular el hash de 700 MB en cada ejecucion es lento).
    Textos y materiales pequenos: hash del contenido."""
    st = ruta.stat()
    if st.st_size > 50 * 1024**2:
        return f"{st.st_size}:{st.st_mtime_ns}"
    return sha256_archivo(ruta)


def huellas_carpeta(carpeta: Path) -> dict:
    if not carpeta.exists():
        return {}
    return {p.name: huella_archivo(p) for p in sorted(carpeta.iterdir())
            if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".parcial")}


def clase(estado: dict, numero: str) -> dict:
    c = estado["clases"].setdefault(numero, {})
    c.setdefault("archivos", {})
    c.setdefault("etapas", {})
    return c


def etapa_al_dia(estado: dict, numero: str, etapa: str, huella: str) -> bool:
    return clase(estado, numero)["etapas"].get(etapa, {}).get("huella") == huella


def marcar_etapa(estado: dict, numero: str, etapa: str, huella: str, **extra) -> None:
    c = clase(estado, numero)
    c["etapas"][etapa] = {"huella": huella, **extra}
    c.pop("error", None)
