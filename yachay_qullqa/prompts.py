"""Prompts para Gemini. Si cambias un prompt, sube VERSION: las clases ya
procesadas se marcaran como desactualizadas y se volveran a generar."""

VERSION = "1"

REGLAS = """REGLAS:
- Responde en espanol.
- No inventes nada. Si algo no se lee o no se entiende, escribe [ILEGIBLE] en
  lugar de adivinar, y registralo en "dudas".
- No incluyas nombres de estudiantes; di "un estudiante". Puedes nombrar al docente.
- Las marcas de tiempo van en formato HH:MM:SS."""

APUNTES = """Eres un asistente que convierte la grabacion de una clase universitaria en
apuntes completos y fieles.

CURSO: {nombre}
DESCRIPCION DEL CURSO: {descripcion}

{tramo}

Usa tanto el audio como lo que se ve en pantalla. En las clases el docente
muestra como configurar plataformas y donde hacer clic: lo que se ve en
pantalla importa tanto como lo que se dice.

{apoyos}

{reglas}
- Las marcas de tiempo son relativas al inicio de ESTE video (00:00:00).
- Copia comandos, consultas y codigo EXACTAMENTE como se ven en pantalla.

Responde SOLO con un objeto JSON con esta forma:
{{
  "titulo": "tema principal de la clase, en pocas palabras",
  "resumen": "tema y objetivos, en 5 a 10 lineas",
  "desarrollo": [
    {{"tiempo": "HH:MM:SS", "titulo": "subtema",
      "contenido": "Markdown fiel y detallado (sin muletillas): lo que explica el docente y todo lo que aparece en pantalla (plataforma, menus y rutas de navegacion, nombres de campos, parametros y valores, URLs, nombres de archivos, tablas y diagramas). Incluye el codigo en bloques ```."}}
  ],
  "codigo": [
    {{"tiempo": "HH:MM:SS", "lenguaje": "bash|sql|python|...", "codigo": "texto exacto", "contexto": "para que sirve"}}
  ],
  "pasos": [
    {{"tiempo": "HH:MM:SS (momento en que el paso se ve en pantalla)", "plataforma": "p. ej. Google Cloud Console",
      "accion": "que se hace y donde se hace clic (ruta de menus)", "valores": "campos y valores usados, o vacio"}}
  ],
  "tareas": [
    {{"tiempo": "HH:MM:SS", "descripcion": "tarea o entregable", "fecha_o_condicion": "si se indica, o vacio"}}
  ],
  "materiales": [
    {{"tiempo": "HH:MM:SS", "descripcion": "archivo, documento, dataset, repositorio o enlace mencionado o mostrado", "nombre_o_enlace": "si se ve o se dice, o vacio"}}
  ],
  "dudas": [
    {{"tiempo": "HH:MM:SS", "detalle": "texto ilegible, audio inentendible o algo que no queda claro"}}
  ]
}}
"pasos" debe contener CADA paso de configuracion, uno por accion visible, en orden,
de forma que se pueda reproducir."""

TRAMO = """Este video es el tramo {n} de {total} de la clase (empieza en el minuto
{inicio} de la grabacion completa). Procesa solo lo que hay en este tramo."""

APOYO_VTT = """TRANSCRIPCION AUTOMATICA DE ZOOM (apoyo): la tienes abajo. Tiene muchos errores
de reconocimiento. Usala solo para escribir bien nombres propios y terminos
tecnicos. Si discrepa con lo que se oye o se ve, prevalece el video."""

APOYO_CHAT = """CHAT DE LA CLASE (apoyo): mensajes de Zoom con su hora. Sirve para saber que
preguntaron los estudiantes y que enlaces se compartieron."""

VERIFICAR = """Te paso capturas de pantalla de una clase. Cada captura se tomo en el momento
en que, segun los apuntes, se realiza un paso de configuracion. Para cada una,
compara lo que se VE con el paso escrito.

{reglas}

PASOS:
{pasos}

Responde SOLO con JSON:
{{"resultados": [
  {{"indice": 1,
    "estado": "coincide | corregido | no_visible",
    "accion": "accion corregida segun lo que se ve (solo si estado = corregido)",
    "valores": "valores corregidos segun lo que se ve (solo si estado = corregido)",
    "observacion": "que se ve en la captura, en una linea"}}
]}}
- "coincide": la captura muestra el paso tal como esta escrito.
- "corregido": la captura muestra el paso, pero algun dato escrito no coincide
  (menu, boton, nombre de campo o valor). Corrige solo con lo que se ve.
- "no_visible": la captura no muestra este paso (otra pantalla, transicion, camara)."""

ASIGNAR_TEMAS = """Organizas los apuntes de un curso por temas.

CURSO: {nombre}
DESCRIPCION: {descripcion}

TEMAS QUE YA EXISTEN EN EL CURSO (id: nombre - descripcion):
{catalogo}

Abajo estan los apuntes de la Clase{clase}. Indica que temas trata, con las
marcas de tiempo donde se tratan. Reutiliza un tema existente siempre que sea el
mismo asunto; crea uno nuevo solo si no encaja en ninguno. Un tema es una unidad
del curso (un concepto, una tecnologia o un procedimiento), no un detalle. Lo
normal son 2 a 6 temas por clase.

Responde SOLO con JSON:
{{"temas": [
  {{"id": "id existente o null si es nuevo", "nombre": "nombre corto",
    "descripcion": "una linea", "momentos": ["HH:MM:SS", "..."]}}
]}}

APUNTES DE LA CLASE{clase}:
{apuntes}"""

TEMA = """Escribe la sintesis de un tema de un curso a partir de los apuntes de las
clases donde se trato.

CURSO: {nombre}
DESCRIPCION: {descripcion}
TEMA: {tema} - {tema_desc}

{reglas}
- Usa SOLO lo que dicen los apuntes de abajo. No completes con conocimiento general.
- Une en un solo texto lo dicho en las distintas clases, sin repetir.
- Cita SIEMPRE la fuente de cada afirmacion como (ClaseNN, HH:MM:SS).
- Copia comandos, codigo y pasos de configuracion tal como estan en los apuntes,
  con sus capturas (los enlaces ../capturas/... funcionan igual desde temas/).
- Si dos clases se contradicen, muestra ambas versiones con su cita.
- Termina con "## Dudas abiertas" con lo que quedo [ILEGIBLE] o sin aclarar.

Responde solo con el Markdown, empezando por "# {tema}".

APUNTES:
{apuntes}"""
