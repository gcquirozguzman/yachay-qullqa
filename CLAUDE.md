# CLAUDE.md

Este repositorio (yachay-qullqa) contiene una herramienta que convierte clases de
Zoom en apuntes, y los apuntes de mis cursos en `cursos/<curso>/`.

## Cuando te pida ayuda con un curso (tareas, proyectos, dudas)

- Trabaja SOLO con la carpeta de ese curso: `cursos/<curso>/`. No leas ni uses
  material de otros cursos.
- Empieza por `INDICE.md` y luego `temas/`. Ve a `apuntes/ClaseNN.md` para el
  detalle (pasos, comandos, capturas) y a `materiales/ClaseNN/` para los archivos.
- Cita siempre la fuente como (ClaseNN, HH:MM:SS).
- Si algo no esta en los apuntes, dimelo explicitamente ("esto no aparece en los
  apuntes") en vez de completarlo con conocimiento general. Si luego aportas
  conocimiento general, separalo y marcalo como tal.
- Respeta las marcas `[ILEGIBLE]` y las secciones "Dudas": no las rellenes
  adivinando; avisame para que lo revise en el video.
- Un paso marcado como "la captura no muestra este paso" o "Corregido segun la
  captura" merece revisarse con la imagen en `capturas/ClaseNN/` antes de usarlo.
- Revisa `archivos_pendientes.md` si una tarea depende de un archivo que puede faltar.
- No modifiques `clases/` (son los originales) ni edites a mano `apuntes/`, `temas/`,
  `INDICE.md` o `archivos_pendientes.md`: se regeneran con la herramienta.

## Cuando trabajes en la herramienta

- Codigo en `yachay_qullqa/`; pruebas en `tests/`.
- Usa siempre el Python de `.venv` (`.venv/Scripts/python` en Windows,
  `.venv/bin/python` en Mac/Linux). No instales nada en el Python del sistema; si
  agregas dependencias, actualiza `requirements.txt`.
- Pruebas: `.venv/Scripts/python -m pytest` (simulan Gemini y ffmpeg).
- Comandos: `python -m yachay_qullqa crear|procesar|estado <curso>`.
