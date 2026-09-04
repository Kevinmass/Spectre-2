"""PR-20/21/22 — servidor FastAPI: estático + `/api/estado` + `/api/buscar` +
`/api/fallos/{cita}` + `/api/tomos/{numero}/pdf`.

D-05 aplicado a la UI: `/api/estado` nunca muestra datos que no estén de
verdad en la base, `/api/buscar` nunca finge una búsqueda semántica que no
corrió — si `sentence-transformers` no está disponible, `modo` en la
respuesta dice `solo_lexico` en vez de fingir `hibrido`—, y `/api/fallos/...`
nunca dice que un PDF está disponible si el archivo no está realmente en
disco."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from spectre.api import crear_app
from spectre.config import get_settings


@pytest.fixture
def datos_tmp(tmp_path, monkeypatch):
    """Redirige `data_dir` a un tmp para que ningún test toque `data/` del repo."""
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _cliente() -> TestClient:
    return TestClient(crear_app())


def _base_migrada():
    from spectre.db import Repo, connect, migrate

    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    migrate(conn)
    return conn, Repo(conn)


def _fallo_con_seccion_y_chunks(
    repo, *, cita, textos, tipo="mayoria", autor=None, **campos_fallo
):
    numero = repo.conn.execute("SELECT count(*) FROM tomos").fetchone()[0] + 1
    tomo_id = repo.insert_tomo(numero)
    fallo_id = repo.insert_fallo(
        tomo_id, "Pérez, Juan c/ Estado Nacional", cita=cita, **campos_fallo
    )
    cur = repo.conn.execute(
        "INSERT INTO secciones (fallo_id, tipo, autor, orden) VALUES (?, ?, ?, 0)",
        (fallo_id, tipo, autor),
    )
    seccion_id = cur.lastrowid
    repo.conn.commit()
    repo.insert_chunks(
        fallo_id, [(seccion_id, i, t, None) for i, t in enumerate(textos)]
    )
    return fallo_id


def _fallo_con_secciones(
    repo, *, cita, secciones, numero=None, pdf_path=None, **campos_fallo
):
    """`secciones` es una lista de `(tipo, autor, texto)`. Devuelve `(tomo_id,
    fallo_id)` — a diferencia de `_fallo_con_seccion_y_chunks`, escribe
    `secciones.texto` directamente (la vista de fallo lee eso, no `chunks`)."""
    if numero is None:
        numero = repo.conn.execute("SELECT count(*) FROM tomos").fetchone()[0] + 1
    tomo_id = repo.insert_tomo(numero, pdf_path=pdf_path)
    fallo_id = repo.insert_fallo(
        tomo_id, "Pérez, Juan c/ Estado Nacional", cita=cita, **campos_fallo
    )
    for orden, (tipo, autor, texto) in enumerate(secciones):
        repo.conn.execute(
            "INSERT INTO secciones (fallo_id, tipo, autor, orden, texto)"
            " VALUES (?, ?, ?, ?, ?)",
            (fallo_id, tipo, autor, orden, texto),
        )
    repo.conn.commit()
    return tomo_id, fallo_id


# --- /api/estado (PR-20) --------------------------------------------------- #


def test_estado_sin_base_da_todo_vacio(datos_tmp):
    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    assert r.json() == {"tomos": [], "chunks": 0}


def test_estado_con_base_vacia_da_cero(datos_tmp):
    conn, _repo = _base_migrada()
    conn.close()

    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    assert r.json() == {"tomos": [], "chunks": 0}


def test_estado_refleja_tomos_y_chunks_reales(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id, estado="indexado", calidad="digital")
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    repo.insert_chunks(fallo_id, [(None, i, f"t{i}", None) for i in range(3)])
    conn.close()

    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["chunks"] == 3
    assert cuerpo["tomos"] == [
        {"numero": 348, "estado": "indexado", "calidad": "digital"}
    ]


def test_index_sirve_el_layout():
    r = _cliente().get("/")
    assert r.status_code == 200
    assert "Spectre" in r.text
    assert "Buscar" in r.text
    assert "Biblioteca" in r.text


def test_sirve_los_estaticos():
    cliente = _cliente()
    assert cliente.get("/style.css").status_code == 200
    assert cliente.get("/app.js").status_code == 200


def test_on_startup_corre_una_vez_el_servidor_esta_listo():
    llamadas = []
    app = crear_app(on_startup=lambda: llamadas.append(True))
    with TestClient(app):
        pass
    assert llamadas == [True]


# --- /api/buscar (PR-21) --------------------------------------------------- #


def test_buscar_sin_base_da_modo_sin_datos(datos_tmp):
    r = _cliente().get("/api/buscar", params={"q": "prescripción"})
    assert r.status_code == 200
    assert r.json() == {
        "consulta": "prescripción",
        "modo": "sin_datos",
        "resultados": [],
    }


def test_buscar_q_vacio_es_error(datos_tmp):
    assert _cliente().get("/api/buscar", params={"q": ""}).status_code == 422


def test_buscar_q_solo_espacios_es_error(datos_tmp):
    assert _cliente().get("/api/buscar", params={"q": "   "}).status_code == 422


def test_buscar_seccion_invalida_es_error(datos_tmp):
    r = _cliente().get("/api/buscar", params={"q": "algo", "seccion": "no-existe"})
    assert r.status_code == 422


def test_buscar_solo_lexico_encuentra_por_texto(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_seccion_y_chunks(
        repo,
        cita="348:1",
        textos=["la prescripción de la acción penal se computa desde el hecho"],
        tipo="disidencia",
        autor="Rosenkrantz",
    )
    conn.close()

    r = _cliente().get(
        "/api/buscar",
        params={"q": "prescripción de la acción penal", "solo_lexico": "true"},
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["modo"] == "solo_lexico"
    assert len(cuerpo["resultados"]) == 1
    resultado = cuerpo["resultados"][0]
    assert resultado["cita"] == "348:1"
    assert resultado["caratula"] == "Pérez, Juan c/ Estado Nacional"
    assert resultado["seccion_tipo"] == "disidencia"
    assert resultado["seccion_autor"] == "Rosenkrantz"
    assert "prescripci" in resultado["extracto"].lower()


def test_buscar_sin_resultados_da_lista_vacia_no_error(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_seccion_y_chunks(repo, cita="348:1", textos=["un texto sin relación"])
    conn.close()

    r = _cliente().get(
        "/api/buscar",
        params={"q": "extradición ciudadano extranjero", "solo_lexico": "true"},
    )
    assert r.status_code == 200
    assert r.json()["resultados"] == []


def test_buscar_filtra_por_anio(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_seccion_y_chunks(
        repo,
        cita="348:1",
        textos=["responsabilidad civil médica"],
        fecha="2018-01-01",
    )
    conn.close()

    sin_filtro = _cliente().get(
        "/api/buscar",
        params={"q": "responsabilidad civil médica", "solo_lexico": "true"},
    )
    assert len(sin_filtro.json()["resultados"]) == 1

    con_filtro = _cliente().get(
        "/api/buscar",
        params={
            "q": "responsabilidad civil médica",
            "solo_lexico": "true",
            "anio": 2024,
        },
    )
    assert con_filtro.json()["resultados"] == []


def test_buscar_modo_hibrido_con_modelo_falso(monkeypatch, datos_tmp):
    from spectre.embed.base import EmbeddingModel
    from spectre.index import IndiceVectorial

    conn, repo = _base_migrada()
    fallo_id = _fallo_con_seccion_y_chunks(
        repo, cita="348:1", textos=["despido injustificado sin causa"]
    )
    chunk_id = repo.list_chunks_de_fallo(fallo_id)[0].id
    conn.close()

    class _Falso(EmbeddingModel):
        nombre = "falso"
        dimension = 2

        def embed(self, textos):
            return [[1.0, 0.0] for _ in textos]

    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", lambda nombre=None: _Falso())

    idx = IndiceVectorial(get_settings().vectors_dir, dimension=2)
    idx.upsert([(chunk_id, [1.0, 0.0], "falso")])

    r = _cliente().get("/api/buscar", params={"q": "despido injustificado"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["modo"] == "hibrido"
    assert cuerpo["resultados"][0]["cita"] == "348:1"


def test_buscar_sin_sentence_transformers_cae_a_solo_lexico(monkeypatch, datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_seccion_y_chunks(
        repo, cita="348:1", textos=["amparo contra el Estado Nacional"]
    )
    conn.close()

    class _Faltante:
        nombre = "falta"
        dimension = 4

        def embed(self, textos):
            raise ModuleNotFoundError("sentence-transformers no está instalado")

        def embed_uno(self, texto):
            return self.embed([texto])[0]

    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", lambda nombre=None: _Faltante())

    r = _cliente().get("/api/buscar", params={"q": "amparo contra el Estado Nacional"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["modo"] == "solo_lexico"
    assert len(cuerpo["resultados"]) == 1


def test_buscar_el_modelo_se_carga_una_sola_vez_por_app(monkeypatch, datos_tmp):
    """Cachear el modelo por instancia de app es lo que hace viable el
    criterio de PR-21 ("menos de 3 segundos"): cargarlo de nuevo en cada
    búsqueda sería demasiado lento con el modelo real."""
    from spectre.embed.base import EmbeddingModel
    from spectre.index import IndiceVectorial

    conn, repo = _base_migrada()
    fallo_id = _fallo_con_seccion_y_chunks(
        repo, cita="348:1", textos=["recurso extraordinario federal"]
    )
    chunk_id = repo.list_chunks_de_fallo(fallo_id)[0].id
    conn.close()

    llamadas = []

    class _Falso(EmbeddingModel):
        nombre = "falso"
        dimension = 2

        def embed(self, textos):
            return [[1.0, 0.0] for _ in textos]

    def cargar_modelo_falso(nombre=None):
        llamadas.append(1)
        return _Falso()

    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", cargar_modelo_falso)

    idx = IndiceVectorial(get_settings().vectors_dir, dimension=2)
    idx.upsert([(chunk_id, [1.0, 0.0], "falso")])

    cliente = _cliente()
    for _ in range(3):
        r = cliente.get("/api/buscar", params={"q": "recurso extraordinario"})
        assert r.status_code == 200

    assert len(llamadas) == 1


# --- /api/fallos/{cita} (PR-22) -------------------------------------------- #


def test_fallo_detalle_sin_base_da_404(datos_tmp):
    r = _cliente().get("/api/fallos/348:1")
    assert r.status_code == 404


def test_fallo_detalle_cita_inexistente_da_404(datos_tmp):
    conn, repo = _base_migrada()
    repo.insert_tomo(348)
    conn.close()

    r = _cliente().get("/api/fallos/348:999")
    assert r.status_code == 404
    assert "348:999" in r.json()["detail"]


def test_fallo_detalle_devuelve_metadatos_secciones_y_citas(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id, _fallo_id = _fallo_con_secciones(
        repo,
        cita="348:113",
        numero=348,
        secciones=[
            (
                "mayoria",
                None,
                "El tribunal remite a Fallos: 337:315, "
                "«Acevedo», por análogas razones.",
            ),
            ("disidencia", "Carlos Fernando Rosenkrantz", "En disidencia, voto por..."),
        ],
        fecha="2025-03-19",
        tribunal_origen="Cámara Federal de Casación Penal",
        tipo_recurso="recurso extraordinario",
        jueces=json.dumps(["Horacio Rosatti", "Ricardo Luis Lorenzetti"]),
        pagina_inicio=113,
        pagina_fin=165,
    )
    repo.actualizar_tomo(tomo_id, offset_pagina=6)
    conn.close()

    r = _cliente().get("/api/fallos/348:113")
    assert r.status_code == 200
    cuerpo = r.json()

    assert cuerpo["cita"] == "348:113"
    assert cuerpo["caratula"] == "Pérez, Juan c/ Estado Nacional"
    assert cuerpo["fecha"] == "2025-03-19"
    assert cuerpo["tribunal_origen"] == "Cámara Federal de Casación Penal"
    assert cuerpo["tipo_recurso"] == "recurso extraordinario"
    assert cuerpo["jueces"] == ["Horacio Rosatti", "Ricardo Luis Lorenzetti"]
    assert cuerpo["tomo_numero"] == 348
    assert cuerpo["pagina_inicio"] == 113
    assert cuerpo["pagina_fin"] == 165
    assert cuerpo["offset_pagina"] == 6
    assert cuerpo["pdf_disponible"] is False

    assert len(cuerpo["secciones"]) == 2
    assert cuerpo["secciones"][0]["tipo"] == "mayoria"
    assert cuerpo["secciones"][0]["autor"] is None
    assert cuerpo["secciones"][1]["tipo"] == "disidencia"
    assert cuerpo["secciones"][1]["autor"] == "Carlos Fernando Rosenkrantz"

    assert len(cuerpo["citas_salientes"]) == 1
    cita_saliente = cuerpo["citas_salientes"][0]
    assert cita_saliente["tomo_citado"] == 337
    assert cita_saliente["pagina_citada"] == 315
    assert "Acevedo" in cita_saliente["contexto"]


def test_fallo_detalle_jueces_vacios_da_lista_vacia(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_secciones(
        repo, cita="348:1", secciones=[("mayoria", None, "texto sin citas")]
    )
    conn.close()

    r = _cliente().get("/api/fallos/348:1")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["jueces"] == []
    assert cuerpo["citas_salientes"] == []


def test_fallo_detalle_pdf_disponible_si_el_archivo_existe(datos_tmp, tmp_path):
    pdf = tmp_path / "348.pdf"
    pdf.write_bytes(b"%PDF-1.4 contenido de prueba")

    conn, repo = _base_migrada()
    _fallo_con_secciones(
        repo,
        cita="348:1",
        secciones=[("mayoria", None, "texto")],
        pdf_path=str(pdf),
    )
    conn.close()

    r = _cliente().get("/api/fallos/348:1")
    assert r.status_code == 200
    assert r.json()["pdf_disponible"] is True


def test_fallo_detalle_pdf_no_disponible_si_el_archivo_no_esta_en_disco(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_secciones(
        repo,
        cita="348:1",
        secciones=[("mayoria", None, "texto")],
        pdf_path="C:/no/existe/348.pdf",
    )
    conn.close()

    r = _cliente().get("/api/fallos/348:1")
    assert r.status_code == 200
    assert r.json()["pdf_disponible"] is False


# --- /api/tomos/{numero}/pdf (PR-22) --------------------------------------- #


def test_pdf_tomo_sin_base_da_404(datos_tmp):
    assert _cliente().get("/api/tomos/348/pdf").status_code == 404


def test_pdf_tomo_inexistente_da_404(datos_tmp):
    conn, repo = _base_migrada()
    repo.insert_tomo(1)
    conn.close()

    r = _cliente().get("/api/tomos/348/pdf")
    assert r.status_code == 404
    assert "348" in r.json()["detail"]


def test_pdf_tomo_sin_archivo_en_disco_da_404(datos_tmp):
    conn, repo = _base_migrada()
    repo.insert_tomo(348, pdf_path="C:/no/existe/348.pdf")
    conn.close()

    r = _cliente().get("/api/tomos/348/pdf")
    assert r.status_code == 404
    assert "no está disponible" in r.json()["detail"]


def test_pdf_tomo_sirve_el_archivo_real(datos_tmp, tmp_path):
    pdf = tmp_path / "348.pdf"
    contenido = b"%PDF-1.4 contenido de prueba para servir"
    pdf.write_bytes(contenido)

    conn, repo = _base_migrada()
    repo.insert_tomo(348, pdf_path=str(pdf))
    conn.close()

    r = _cliente().get("/api/tomos/348/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == contenido
