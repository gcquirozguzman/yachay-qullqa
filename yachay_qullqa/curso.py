"""Un curso = una carpeta en cursos/<nombre>. Nunca se mezcla contenido entre cursos."""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_CURSOS = Path(__file__).resolve().parent.parent / "cursos"
RE_NOMBRE_CURSO = re.compile(r"^[a-z0-9][a-z0-9-]*$")

CONFIG_DEFECTO = {
    "modelo": "gemini-3.8-flash",
    # Tramos por duracion; 0 = no dividir por duracion. Con processing "agentic"
    # Gemini recorre el video completo (hasta ~3 h caben en una peticion), asi que
    # solo se divide si el archivo supera limite_bytes.
    "duracion_tramo_min": 0,
    # Tope por archivo del nivel gratuito de la API de archivos de Gemini.
    "limite_bytes": 2 * 1024**3,
    # Tope de descarga por enlace, para no bajar por error algo enorme.
    "limite_descarga_mb": 500,
    # Segundos que se suman a la marca de tiempo de un paso al tomar la captura.
    "desfase_captura_s": 2,
}

PLANTILLA_TOML = '''# Datos del curso. La descripcion se usa en los prompts de Gemini.
nombre = "{nombre}"
descripcion = "{descripcion}"

[procesamiento]
modelo = "{modelo}"
duracion_tramo_min = {duracion_tramo_min}
limite_bytes = {limite_bytes}
limite_descarga_mb = {limite_descarga_mb}
desfase_captura_s = {desfase_captura_s}
'''


@dataclass
class Curso:
    carpeta: Path
    nombre: str = ""
    descripcion: str = ""
    config: dict = field(default_factory=dict)

    # Rutas fijas dentro del curso
    @property
    def clases(self) -> Path: return self.carpeta / "clases"
    @property
    def materiales(self) -> Path: return self.carpeta / "materiales"
    @property
    def capturas(self) -> Path: return self.carpeta / "capturas"
    @property
    def apuntes(self) -> Path: return self.carpeta / "apuntes"
    @property
    def temas(self) -> Path: return self.carpeta / "temas"
    @property
    def indice(self) -> Path: return self.carpeta / "INDICE.md"
    @property
    def pendientes(self) -> Path: return self.carpeta / "archivos_pendientes.md"
    @property
    def estado(self) -> Path: return self.carpeta / "estado.json"
    @property
    def trabajo(self) -> Path:
        """Resultados intermedios (respuestas de Gemini, tramos). Permiten retomar."""
        return self.carpeta / ".trabajo"

    @property
    def id(self) -> str:
        return self.carpeta.name

    @classmethod
    def abrir(cls, nombre: str, raiz: Path = RAIZ_CURSOS) -> "Curso":
        carpeta = raiz / nombre
        toml = carpeta / "curso.toml"
        if not toml.exists():
            raise SystemExit(
                f"No existe el curso '{nombre}' ({toml}). Crealo con: crear {nombre}"
            )
        datos = tomllib.loads(toml.read_text(encoding="utf-8"))
        config = {**CONFIG_DEFECTO, **datos.get("procesamiento", {})}
        return cls(carpeta, datos.get("nombre", nombre), datos.get("descripcion", ""), config)

    @classmethod
    def crear(cls, nombre: str, titulo: str, descripcion: str, raiz: Path = RAIZ_CURSOS) -> "Curso":
        if not RE_NOMBRE_CURSO.match(nombre):
            raise SystemExit("El nombre del curso solo admite minusculas, numeros y guiones.")
        carpeta = raiz / nombre
        toml = carpeta / "curso.toml"
        if toml.exists():
            raise SystemExit(f"El curso '{nombre}' ya existe.")
        curso = cls(carpeta, titulo, descripcion, dict(CONFIG_DEFECTO))
        for sub in (curso.clases, curso.materiales, curso.capturas, curso.apuntes, curso.temas):
            sub.mkdir(parents=True, exist_ok=True)
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
        toml.write_text(
            PLANTILLA_TOML.format(nombre=esc(titulo), descripcion=esc(descripcion), **CONFIG_DEFECTO),
            encoding="utf-8",
        )
        return curso
