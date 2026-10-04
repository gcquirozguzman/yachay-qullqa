# yachay-qullqa

Convierte las grabaciones de clases de Zoom en apuntes ordenados, para poder
estudiar y hacer tareas sin volver a ver horas de video.

## Qué hace

Le das las grabaciones de un curso y te devuelve:

- **Apuntes de cada clase**: resumen, lo que se explicó minuto a minuto, los
  comandos y el código que se mostraron, y los pasos de configuración con un
  pantallazo de cada uno.
- **Resúmenes por tema**: junta lo que se dijo de un mismo tema en distintas
  clases, indicando siempre la clase y el minuto de donde sale.
- **Un índice** para encontrar todo rápido.
- **Una lista de materiales**: los archivos y enlaces que se compartieron en
  clase, cuáles se pudieron descargar y cuáles tienes que conseguir tú.

Lo que no se entiende en el video queda marcado como `[ILEGIBLE]`: la
herramienta no inventa contenido.

## Cómo funciona

Para cada clase usa tres archivos que entrega Zoom:

| Archivo | Qué es |
|---|---|
| `ClaseNN.mp4` | El video de la clase |
| `ClaseNN.txt` | El chat de la clase (de aquí salen los enlaces) |
| `ClaseNN.vtt` | La transcripción automática (opcional; ayuda con nombres y términos) |

El video lo analiza **Gemini**, la inteligencia artificial de Google, que ve la
pantalla y escucha el audio. Para eso la herramienta lo envía a Google y lo
borra apenas termina.

Cada curso tiene su propia carpeta dentro de `cursos/` y nunca se mezcla con
otro.

## Qué necesitas

1. **Python** 3.11 o superior.
2. **ffmpeg**, un programa gratuito para trabajar con videos. En Windows se
   instala con `winget install Gyan.FFmpeg`; en Mac, con `brew install ffmpeg`.
3. **Una clave de Gemini**, gratuita, que se crea en
   https://aistudio.google.com/apikey. El plan gratuito tiene un límite de uso
   diario, y Google puede usar lo que envías para mejorar sus productos.

## Instalación (una sola vez)

Abre una terminal en la carpeta del proyecto y ejecuta:

**Windows**
```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**Mac / Linux**
```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Luego abre el archivo `.env` de la carpeta del proyecto (créalo si no existe) y
pega tu clave así:

```
GEMINI_API_KEY=tu_clave
```

Ese archivo es privado: no se sube a ningún repositorio.

## Uso

1. **Crea el curso** (una vez):
   `.venv\Scripts\python -m yachay_qullqa crear big-data --nombre "Big Data"`
2. **Copia las grabaciones** a `cursos/big-data/clases/`.
3. **Procesa**:
   `.venv\Scripts\python -m yachay_qullqa procesar big-data`
   (agrega `--clase 01` para procesar solo una clase).
4. **Revisa qué falta** en cualquier momento:
   `.venv\Scripts\python -m yachay_qullqa estado big-data`

En Mac o Linux, cambia `.venv\Scripts\python` por `.venv/bin/python`.

Después, abre `cursos/big-data/INDICE.md` y empieza por ahí.

## Si agregas algo después

Vuelve a ejecutar **procesar**. La herramienta solo trabaja lo nuevo:

- Una clase nueva se procesa y se actualizan los temas y el índice.
- Si agregas un archivo que faltaba (por ejemplo, la transcripción) o un
  material que descargaste a mano en `materiales/ClaseNN/`, solo se actualiza
  esa clase.
- Si se corta a mitad de camino, continúa donde quedó.

## Qué hay en la carpeta de un curso

| Carpeta o archivo | Contenido |
|---|---|
| `clases/` | Tus grabaciones originales (nunca se modifican) |
| `apuntes/` | Los apuntes de cada clase |
| `temas/` | Los resúmenes por tema |
| `capturas/` | Los pantallazos de los pasos de configuración |
| `materiales/` | Los archivos descargados o que agregues tú |
| `INDICE.md` | El índice de clases y temas |
| `archivos_pendientes.md` | Los materiales que faltan conseguir y qué hacer con cada uno |
| `curso.toml` | El nombre y la descripción del curso (Gemini usa la descripción) |
| `estado.json` y `.trabajo/` | El registro interno de lo ya procesado (no hace falta tocarlos) |
