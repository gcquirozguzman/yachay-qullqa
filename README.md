# yachay-qullqa

Convierte grabaciones de clases de Zoom en una base de apuntes confiable,
organizada por temas. Sirve para cualquier curso: cada curso vive en su propia
carpeta y nunca se mezcla con otro.

Por cada clase usa el video (audio y lo que se ve en pantalla, con Gemini), el
chat de Zoom (`.txt`) y, si existe, la transcripcion automatica (`.vtt`). Genera
apuntes con marcas de tiempo, capturas de cada paso de configuracion, sintesis
por tema, un indice y la lista de materiales que faltan conseguir.

## Requisitos

- Python 3.11 o superior.
- ffmpeg (incluye ffprobe). Comprueba con `ffmpeg -version`. Si falta:
  - Windows: `winget install Gyan.FFmpeg` y vuelve a abrir la terminal.
  - Mac: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` (o el gestor de tu distribucion).
- Una clave de la API de Gemini (gratuita): https://aistudio.google.com/apikey

## Instalacion

Todo se instala en un entorno virtual `.venv` dentro del repositorio, nunca en
el Python del sistema.

### Windows (PowerShell)

```powershell
cd ruta\a\yachay-qullqa
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
setx GEMINI_API_KEY "tu_clave"     # permanente; luego cierra y abre la terminal
```

Si PowerShell no deja activar el entorno, ejecuta una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Tambien puedes no
activarlo y llamar siempre a `.venv\Scripts\python`.

### Mac / Linux

```bash
cd ruta/a/yachay-qullqa
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
echo 'export GEMINI_API_KEY="tu_clave"' >> ~/.zshrc   # o ~/.bashrc; luego abre otra terminal
```

## Uso

Con el entorno activado (o usando la ruta `.venv/.../python`):

```bash
# 1. Crear un curso (una vez)
python -m yachay_qullqa crear big-data --nombre "Big Data" --descripcion "De que trata el curso"

# 2. Copiar los archivos de clase a cursos/big-data/clases/
#    ClaseNN.mp4 (video), ClaseNN.txt (chat de Zoom), ClaseNN.vtt (transcripcion, opcional)

# 3. Procesar (solo lo nuevo o cambiado)
python -m yachay_qullqa procesar big-data
python -m yachay_qullqa procesar big-data --clase 01          # una sola clase
python -m yachay_qullqa procesar big-data --reintentar-descargas

# 4. Ver que esta hecho y que falta
python -m yachay_qullqa estado big-data
```

La descripcion del curso (en `curso.toml`) se usa en los prompts de Gemini:
conviene que diga de que trata el curso y que plataformas usa.

## Estructura de un curso

```
cursos/<curso>/
  curso.toml               nombre, descripcion y ajustes de procesamiento
  clases/                  originales (mp4, txt, vtt); nunca se modifican
  materiales/ClaseNN/      archivos descargados o agregados a mano
  capturas/ClaseNN/        pantallazos de cada paso de configuracion
  apuntes/ClaseNN.md       apuntes de cada clase
  temas/NN-<tema>.md       sintesis por tema, con citas (ClaseNN, HH:MM:SS)
  INDICE.md                clases y temas, con enlaces
  archivos_pendientes.md   material mencionado y su estado
  estado.json              registro de lo ya procesado
  .trabajo/                resultados intermedios (permiten retomar)
```

## Que hace, por clase y en orden numerico

1. **Inventario**: agrupa `ClaseNN.*` y avisa si falta el video, el chat o la transcripcion.
2. **Texto**: del chat y la transcripcion extrae enlaces y menciones a archivos o
   materiales (Word, PDF, Excel, presentaciones, datasets, repositorios...) con hora y linea.
3. **Descargas**: baja cada enlace a `materiales/ClaseNN/`. Google Docs, Sheets y
   Slides se exportan a .docx, .xlsx y .pptx; archivos de Drive y Colab, por su URL
   de descarga; repositorios de GitHub, como .zip. No pide contrasenas: si algo es
   privado queda como "sin permiso". Las paginas web (consolas, blogs,
   documentacion) quedan como "referencia" y no se descargan.
4. **Video**: lo sube a Gemini y pide apuntes con marcas de tiempo. El `.vtt` y el
   chat se envian como apoyo para nombres y terminos. Los videos de mas de 60 min
   (o de mas de 2 GB) se dividen con ffmpeg y los apuntes se unen con las horas
   corregidas.
5. **Capturas**: extrae un pantallazo en cada paso de configuracion y le pide a
   Gemini que compare la imagen con el paso. Si no coincide, el paso se corrige
   (y se muestra lo que decia antes) o se marca para revisar.
6. **Apuntes**: `apuntes/ClaseNN.md` con resumen, desarrollo cronologico, comandos y
   codigo, pasos con captura, tareas, materiales y dudas.
7. **Temas**: asigna cada clase a temas y escribe un archivo por tema que une lo
   dicho en todas las clases.
8. **Pendientes**: tabla con cada material, donde se menciono, su estado y que hacer.

Lo que no se lee o no se entiende queda como `[ILEGIBLE]`.

## Archivos nuevos y cortes

`procesar` compara la carpeta con `estado.json`:

- **Clase nueva**: se procesa y se actualizan temas, indice y pendientes.
- **Archivo nuevo en una clase** (un `.vtt` que faltaba): se reprocesa esa clase y
  sus temas. Un **material agregado a mano** en `materiales/ClaseNN/` solo
  actualiza los apuntes y los pendientes, sin volver a subir el video.
- **Sin cambios**: no se sube ni se pide nada.
- **Corte a mitad de camino**: vuelve a ejecutar el mismo comando. Los tramos ya
  hechos no se repiten, y si el video ya estaba subido o la respuesta estaba en
  curso, se retoma.

## Pruebas

```bash
python -m pytest
```

Las pruebas simulan Gemini y ffmpeg: no gastan cuota ni necesitan red.

## Notas

- Modelo: `gemini-3.8-flash` (se cambia en `curso.toml`). El nivel gratuito tiene
  limites diarios; si se alcanzan, el comando falla y basta con volver a
  ejecutarlo mas tarde.
- Si cambias los prompts (`yachay_qullqa/prompts.py`), sube `VERSION` para que las
  clases se regeneren.
- El `.gitignore` excluye videos, chats, materiales, capturas, `.trabajo/` y
  claves. Los apuntes y temas si se versionan.
