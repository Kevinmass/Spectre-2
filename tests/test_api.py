"""PR-20/21 — servidor FastAPI: estático + `/api/estado` + `/api/buscar`.

D-05 aplicado a la UI: `/api/estado` nunca muestra datos que no estén de
verdad en la base, y `/api/buscar` nunca finge una búsqueda semántica que no
corrió — si `sentence-transformers` no está disponible, `modo` en la
respuesta dice `solo_lexico` en vez de fingir `hibrido`."""

from __future__ import annotations

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
