"""Flujo completo con Gemini y ffmpeg simulados: no usa red ni cuota."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yachay_qullqa import descargas, gemini, pipeline, video
from yachay_qullqa.curso import Curso


class GeminiFalso:
    def __init__(self):
        self.llamadas = []  # (tipo, detalle)
        self.subidas = []
        self.fallar_en_tramo = None
        self.prompts_video = []
        self._resp = {}
        self.files = SimpleNamespace(upload=self._subir, get=self._get_archivo, delete=lambda name: None)
        self.interactions = SimpleNamespace(create=self._crear, get=self._get)

    def _subir(self, file, config):
        self.subidas.append(Path(file.name).name)
        return self._get_archivo(f"files/{len(self.subidas)}")

    def _get_archivo(self, name):
        uri = f"uri/{self.subidas[int(name.split('/')[1]) - 1]}"
        return SimpleNamespace(name=name, uri=uri, mime_type="video/mp4", state=SimpleNamespace(name="ACTIVE"))

    def _crear(self, model, input, background):
        textos = " ".join(b.get("text", "") for b in input if b["type"] == "text")
        if any(b["type"] == "video" for b in input):
            tramo = input[0]["uri"]
            if self.fallar_en_tramo and self.fallar_en_tramo in tramo:
                raise RuntimeError("corte simulado")
            self.llamadas.append(("video", tramo))
            self.prompts_video.append(textos)
            con_vtt = "TRANSCRIPCION AUTOMATICA" in textos
            salida = json.dumps({
                "titulo": f"Tema de {tramo}", "resumen": "Resumen con vtt." if con_vtt else "Resumen.",
                "desarrollo": [{"tiempo": "00:01:00", "titulo": "Inicio", "contenido": "Explica GCP."}],
                "codigo": [{"tiempo": "00:02:00", "lenguaje": "bash", "codigo": "gcloud init", "contexto": "configurar"}],
                "pasos": [{"tiempo": "00:03:00", "plataforma": "GCP", "accion": "Clic en IAM", "valores": ""},
                          {"tiempo": "00:04:00", "plataforma": "GCP", "accion": "Crear bucket", "valores": "nombre=x"}],
                "tareas": [], "materiales": [{"tiempo": "00:05:00", "descripcion": "PDF del caso", "nombre_o_enlace": ""}],
                "dudas": [{"tiempo": "00:06:00", "detalle": "[ILEGIBLE] nombre del servicio"}],
            })
        elif "Te paso capturas" in textos:
            self.llamadas.append(("verificar", textos.count("Captura del paso")))
            n = textos.count("Captura del paso")
            res = [{"indice": i, "estado": "coincide", "observacion": "se ve"} for i in range(1, n + 1)]
            res[-1] = {"indice": n, "estado": "corregido", "accion": "Crear bucket (boton CREAR)",
                       "valores": "nombre=y", "observacion": "el campo dice y"}
            salida = "```json\n" + json.dumps({"resultados": res}) + "\n```"
        elif "Organizas los apuntes" in textos:
            self.llamadas.append(("asignar", ""))
            existente = "configuracion-gcp" in textos
            salida = json.dumps({"temas": [{"id": "configuracion-gcp" if existente else None,
                                            "nombre": "Configuracion GCP", "descripcion": "IAM y buckets",
                                            "momentos": ["00:03:00"]}]})
        else:
            self.llamadas.append(("tema", ""))
            salida = "# Configuracion GCP\n\nSe crea un bucket (Clase01, 00:04:00)."
        id_ = f"i{len(self._resp)}"
        self._resp[id_] = salida
        return SimpleNamespace(id=id_, status="queued", output_text=None)

    def _get(self, id):
        return SimpleNamespace(id=id, status="completed", output_text=self._resp[id])

    def tipos(self):
        return [t for t, _ in self.llamadas]


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    falso = GeminiFalso()
    monkeypatch.setattr(gemini, "clave_disponible", lambda: True)
    monkeypatch.setattr(gemini, "crear_cliente", lambda: falso)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "ESPERA_REINTENTO", 0)
    monkeypatch.setattr(gemini, "REINTENTOS", 1)
    monkeypatch.setattr(video, "ffmpeg_disponible", lambda: True)
    monkeypatch.setattr(video, "duracion", lambda v: 7000.0)  # 1 h 56 min -> 2 tramos de 60 min

    def dividir(v, carpeta, seg):
        carpeta.mkdir(parents=True, exist_ok=True)
        tramos = []
        # El tramo 2 empieza en 3400 s, pero lo nuevo empieza en 3500 s (100 s de solape).
        for i, (ini, desde) in enumerate(((0.0, 0.0), (3400.0, 3500.0))):
            p = carpeta / f"{v.stem}_tramo_{i:02d}.mp4"
            p.write_bytes(b"x")
            tramos.append({"archivo": str(p), "inicio": ini, "fin": desde + 3500, "desde": desde})
        return tramos

    monkeypatch.setattr(video, "dividir", dividir)
    monkeypatch.setattr(video, "captura", lambda v, s, d: (d.parent.mkdir(parents=True, exist_ok=True),
                                                           d.write_bytes(f"{v.name}{s}".encode())))
    monkeypatch.setattr(descargas, "descargar", lambda url, carpeta, limite: {
        "url": url, "categoria": "Pagina web", "url_descarga": None, "nombre": None,
        "estado": descargas.REFERENCIA, "archivo": None, "detalle": ""})

    curso = Curso.crear("prueba", "Prueba", "Curso de prueba", raiz=tmp_path)
    curso.config["duracion_tramo_min"] = 60
    (curso.clases / "Clase01.mp4").write_bytes(b"video1")
    (curso.clases / "Clase01.txt").write_text("00:10:00\tDocente:\thttps://ejemplo.org\n", encoding="utf-8")
    (curso.clases / "Clase02.mp4").write_bytes(b"video2")
    return curso, falso


def test_flujo_completo_e_incremental(entorno):
    curso, falso = entorno
    assert pipeline.procesar(curso, log=lambda *a: None) == 0

    # 2 clases x 2 tramos, verificacion por clase, asignacion por clase, 1 tema
    assert falso.tipos().count("video") == 4
    assert falso.tipos().count("verificar") == 2
    assert falso.tipos().count("asignar") == 2
    assert falso.tipos().count("tema") == 1

    md = (curso.apuntes / "Clase01.md").read_text(encoding="utf-8")
    # 00:01:00 del tramo 2 = 3460 s: cae en el solape (antes de 3500 s) y se descarta.
    assert md.count("] Inicio") == 1 and "### [00:01:00] Inicio" in md
    assert "**[00:58:40]**" in md  # codigo 00:02:00 del tramo 2 + 3400 s
    assert "LO QUE SE VIO EN EL TRAMO ANTERIOR" in falso.prompts_video[1]
    assert "Resumen." in falso.prompts_video[1] and "hasta el 00:01:40" in falso.prompts_video[1]
    assert "TRAMO ANTERIOR" not in falso.prompts_video[0]
    assert "gcloud init" in md
    assert "![Paso 2 (00:04:00)](../capturas/Clase01/paso-02_00-04-00.jpg)" in md
    assert "Corregido segun la captura" in md and "Crear bucket (boton CREAR)" in md
    assert (curso.capturas / "Clase01" / "paso-04_01-00-40.jpg").exists()
    assert (curso.temas / "01-configuracion-gcp.md").exists()
    indice = curso.indice.read_text(encoding="utf-8")
    assert "[Configuracion GCP](temas/01-configuracion-gcp.md)" in indice
    pend = curso.pendientes.read_text(encoding="utf-8")
    assert "https://ejemplo.org" in pend and "PDF del caso" in pend and "mencionado sin enlace" in pend
    assert not (curso.trabajo / "Clase01" / "video" / "partes").exists()  # tramos borrados

    # Sin cambios: nada se vuelve a subir ni a pedir.
    antes = len(falso.llamadas)
    pipeline.procesar(curso, log=lambda *a: None)
    assert len(falso.llamadas) == antes

    # Material agregado a mano: no se reprocesa el video, si los apuntes y pendientes.
    (curso.materiales / "Clase02").mkdir(parents=True, exist_ok=True)
    (curso.materiales / "Clase02" / "caso.pdf").write_bytes(b"%PDF")
    pipeline.procesar(curso, log=lambda *a: None)
    assert len(falso.llamadas) == antes
    assert "caso.pdf" in (curso.apuntes / "Clase02.md").read_text(encoding="utf-8")
    assert "agregado a mano" in curso.pendientes.read_text(encoding="utf-8")

    # Llega el .vtt de la Clase02: solo esa clase y su tema.
    (curso.clases / "Clase02.vtt").write_text("WEBVTT\n\n00:00:05.000 --> 00:00:09.000\nhola\n", encoding="utf-8")
    pipeline.procesar(curso, log=lambda *a: None)
    nuevas = falso.llamadas[antes:]
    assert [t for t, _ in nuevas].count("video") == 2
    assert all("Clase02" in d for t, d in nuevas if t == "video")
    assert [t for t, _ in nuevas].count("asignar") == 1  # solo Clase02
    assert [t for t, _ in nuevas].count("tema") == 1
    assert [t for t, _ in nuevas].count("verificar") == 0  # mismas capturas y pasos: se reutiliza


def test_retoma_tras_corte(entorno):
    curso, falso = entorno
    falso.fallar_en_tramo = "Clase01_tramo_01"
    assert pipeline.procesar(curso, numero="01", log=lambda *a: None) == 1
    assert falso.tipos() == ["video"]  # el tramo 1 se hizo y quedo guardado

    falso.fallar_en_tramo = None
    assert pipeline.procesar(curso, numero="01", log=lambda *a: None) == 0
    videos = [d for t, d in falso.llamadas if t == "video"]
    assert videos == ["uri/Clase01_tramo_00.mp4", "uri/Clase01_tramo_01.mp4"]  # el tramo 0 no se repitio
    assert (curso.apuntes / "Clase01.md").exists()
