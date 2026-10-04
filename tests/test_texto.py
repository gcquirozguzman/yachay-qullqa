from yachay_qullqa import descargas, texto, video
from yachay_qullqa.apuntes import desplazar, unir

CHAT = (
    "00:54:59\tAnita Quevedo:\thttps://docs.google.com/document/d/1sn329T5bsZmtj7K2VUPMdlOjzmog2djoSF_u7AXyzw8/edit?usp=sharing\n"
    "01:06:08\tHouston Ramirez:\tNos podria pasar el archivo de creacion del proyecto completo?\n"
    "01:18:47\tAnita Quevedo:\tSos un asistente virtual\n"
    "Hablas con el ritmo de alguien, ver www.ejemplo.com.pe/guia.\n"
    "03:17:30\tFrancisco Meza:\tReacted to \"Screenshot2026_09_30_221715.jpg\" with 👍\n"
)

VTT_NUMERADO = """WEBVTT

401
00:49:06.000 --> 00:49:11.000
Y les a poner un nombre

402
00:49:11.000 --> 00:49:15.000
por ejemplo www.com no lo se, abran el dataset
"""


def test_chat_multilinea_y_hallazgos(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(CHAT, encoding="utf-8")
    msgs = texto.leer_chat(p)
    assert len(msgs) == 4
    assert "ritmo de alguien" in msgs[2].texto and msgs[2].linea == 3

    d = texto.extraer(p, None)
    urls = [e["valor"] for e in d["enlaces"]]
    assert urls[0].startswith("https://docs.google.com/document/d/1sn329")
    assert "https://www.ejemplo.com.pe/guia" in urls  # sin el punto final
    tipos = {(m["tipo"], m["valor"]) for m in d["menciones"]}
    assert ("Archivo", "archivo") in tipos
    assert ("nombre_archivo", "Screenshot2026_09_30_221715.jpg") in tipos


def test_vtt_y_falso_www(tmp_path):
    p = tmp_path / "c.vtt"
    p.write_text(VTT_NUMERADO, encoding="utf-8")
    cues = texto.leer_vtt(p)
    assert [c.inicio for c in cues] == [2946, 2951]
    d = texto.extraer(None, p)
    assert d["enlaces"] == []  # "www.com" no es un enlace
    assert any(m["tipo"] == "Dataset" and m["tiempo"] == "00:49:11" for m in d["menciones"])
    # El bloque que cruza el inicio del tramo se incluye, con hora 00:00:00.
    assert texto.vtt_compacto(cues, 2950, 3000, restar=2950).splitlines()[1].startswith("[00:00:01] por ejemplo")


def test_plan_descargas():
    p = descargas.plan("https://docs.google.com/spreadsheets/d/14VondvkdfuMQbb00ofZ-WUxKmbuwnhzhVOVYkVgIE7Q/edit?gid=0#gid=0")
    assert p["url_descarga"].endswith("/14VondvkdfuMQbb00ofZ-WUxKmbuwnhzhVOVYkVgIE7Q/export?format=xlsx")
    assert descargas.plan("https://docs.google.com/presentation/d/abcdefghijkl/edit")["url_descarga"].endswith("/export/pptx")
    assert "id=abcdefghijkl" in descargas.plan("https://drive.google.com/file/d/abcdefghijkl/view")["url_descarga"]
    assert "id=abcdefghijkl" in descargas.plan("https://drive.google.com/open?id=abcdefghijkl")["url_descarga"]
    assert descargas.plan("https://drive.google.com/drive/folders/abcdefghijkl")["categoria"] == "Carpeta de Drive"
    assert descargas.plan("https://github.com/google/agents-cli")["url_descarga"] == \
        "https://github.com/google/agents-cli/archive/HEAD.zip"
    assert descargas.plan("https://github.com/a/b/blob/main/x/y.ipynb")["url_descarga"] == \
        "https://github.com/a/b/raw/main/x/y.ipynb"
    assert descargas.plan("https://ces.cloud.google.com/projects?authuser=1")["url_descarga"] is None
    assert descargas.plan("https://ejemplo.org/datos/ventas.csv")["nombre"] == "ventas.csv"


def test_tramos():
    assert video.segundos_por_tramo(700 * 1024**2, 50 * 60, 60, 2 * 1024**3) is None
    assert video.segundos_por_tramo(700 * 1024**2, 3 * 3600 + 20, 60, 2 * 1024**3) == 2705  # 4 tramos parejos
    # Pesa 5 GB y dura 40 min: se divide por tamano aunque no supere la duracion.
    seg = video.segundos_por_tramo(5 * 1024**3, 2400, 60, 2 * 1024**3)
    assert seg is not None and seg < 2400 * 0.4


def test_desplazar_y_unir():
    a = desplazar({"titulo": "A", "resumen": "r1", "pasos": [{"tiempo": "00:10:00", "accion": "x"}]}, 0)
    b = desplazar({"titulo": "B", "resumen": "r2", "pasos": [{"tiempo": "00:05:00", "accion": "y"}],
                   "dudas": [{"tiempo": "??", "detalle": "z"}]}, 3600)
    u = unir([{"inicio": 0, "notas": a}, {"inicio": 3600, "notas": b}])
    assert [p["tiempo"] for p in u["pasos"]] == ["00:10:00", "01:05:00"]
    assert u["dudas"][0]["tiempo"].startswith("[ILEGIBLE]")
    assert u["titulo"] == "A · B" and "Tramo 2 (desde 01:00:00)" in u["resumen"]


def test_indicador(monkeypatch):
    import io
    import time

    from yachay_qullqa.progreso import Indicador

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    salida = Terminal()
    monkeypatch.setattr("sys.stdout", salida)
    with Indicador("Subiendo tramo 1/3"):
        time.sleep(0.6)
    texto = salida.getvalue()
    assert "Subiendo tramo 1/3... 00:00" in texto
    assert texto.endswith("Subiendo tramo 1/3: listo (00:00)" + " " * 10 + "\n")
