"""PR-20/21/22/23 — servidor FastAPI: estático + `/api/estado` +
`/api/buscar` + `/api/fallos/{cita}` + `/api/tomos/{numero}/pdf` +
`POST /api/tomos/{numero}/indexar` + `POST /api/tomos/{numero}/subir`.

D-05 aplicado a la UI: `/api/estado` nunca muestra datos que no estén de
verdad en la base (desde PR-23, tampoco un progreso que en realidad está
trabado en una etapa fallida), `/api/buscar` nunca finge una búsqueda
semántica que no corrió — si `sentence-transformers` no está disponible,
`modo` en la respuesta dice `solo_lexico` en vez de fingir `hibrido`—,
`/api/fallos/...` nunca dice que un PDF está disponible si el archivo no
está realmente en disco, y `POST /api/tomos/.../indexar` no reintenta sola
una etapa que ya falló."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spectre.api import crear_app
from spectre.api.app import _extracto, _terminos
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
        {
            "numero": 348,
            "estado": "indexado",
            "calidad": "digital",
            "etapas_hechas": 8,
            "etapas_total": 8,
            "error": None,
            "sumarios": 0,
        }
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
    assert resultado["total_pasajes"] == 1
    assert len(resultado["pasajes"]) == 1
    pasaje = resultado["pasajes"][0]
    assert pasaje["seccion_tipo"] == "disidencia"
    assert pasaje["seccion_autor"] == "Rosenkrantz"
    assert "prescripci" in pasaje["extracto"].lower()


def test_buscar_agrupa_los_pasajes_de_un_fallo_en_un_solo_resultado(datos_tmp):
    """Dos secciones distintas del mismo fallo matchean: un resultado, dos
    pasajes (uno por tipo), sin repetir la cita — el defecto §2.1 del plan v2
    era que cada pasaje era un resultado y una sentencia tapaba a las demás."""
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:7")
    ids = {}
    for tipo in ("mayoria", "disidencia"):
        cur = repo.conn.execute(
            "INSERT INTO secciones (fallo_id, tipo, orden) VALUES (?, ?, 0)",
            (fallo_id, tipo),
        )
        ids[tipo] = cur.lastrowid
    repo.conn.commit()
    repo.insert_chunks(
        fallo_id,
        [
            (ids["mayoria"], 0, "el amparo procede contra el Estado", None),
            (ids["mayoria"], 1, "amparo y Estado otra vez en la mayoría", None),
            (
                ids["disidencia"],
                2,
                "en disidencia el amparo contra el Estado no procede",
                None,
            ),
        ],
    )
    conn.close()

    cuerpo = (
        _cliente()
        .get("/api/buscar", params={"q": "amparo Estado", "solo_lexico": "true"})
        .json()
    )
    assert [r["cita"] for r in cuerpo["resultados"]] == ["348:7"]
    resultado = cuerpo["resultados"][0]
    assert resultado["total_pasajes"] == 3
    tipos = {p["seccion_tipo"] for p in resultado["pasajes"]}
    assert tipos == {"mayoria", "disidencia"}


def test_buscar_filtra_por_seccion_y_tribunal_desde_la_api(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_seccion_y_chunks(
        repo,
        cita="348:1",
        textos=["voto en disidencia sobre la cuestión federal"],
        tipo="disidencia",
        tribunal_origen="Cámara Federal de La Plata",
    )
    conn.close()

    def _citas(**extra):
        params = {"q": "cuestión federal", "solo_lexico": "true", **extra}
        cuerpo = _cliente().get("/api/buscar", params=params).json()
        return [r["cita"] for r in cuerpo["resultados"]]

    assert _citas() == ["348:1"]
    assert _citas(seccion="disidencia") == ["348:1"]
    assert _citas(seccion="mayoria") == []
    assert _citas(tribunal="Cámara Federal de La Plata") == ["348:1"]
    assert _citas(tribunal="Otra Cámara") == []
    # un filtro de tribunal en blanco no restringe nada
    assert _citas(tribunal="   ") == ["348:1"]


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


def test_buscar_filtra_por_rango_de_anios(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_seccion_y_chunks(
        repo,
        cita="348:1",
        textos=["responsabilidad civil médica"],
        fecha="2018-01-01",
    )
    conn.close()

    def _buscar(**extra):
        params = {"q": "responsabilidad civil médica", "solo_lexico": "true", **extra}
        return _cliente().get("/api/buscar", params=params).json()["resultados"]

    assert len(_buscar()) == 1
    assert len(_buscar(anio_desde=2015, anio_hasta=2019)) == 1  # cae dentro
    assert _buscar(anio_desde=2020) == []  # piso por encima
    assert _buscar(anio_hasta=2017) == []  # techo por debajo


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


# --- _terminos / _extracto (PR-A4: extractos que empiecen donde corresponde) --- #


def test_terminos_saca_palabras_vacias_y_cortas():
    assert _terminos("responsabilidad del estado") == ["responsabilidad", "estado"]
    assert _terminos("el de la por") == []
    assert _terminos("daño moral") == ["daño", "moral"]


def _sin_cortar_palabra(extracto: str, fuente: str) -> bool:
    """El extracto no arranca a mitad de una palabra de `fuente`."""
    cuerpo = extracto.lstrip("…").strip()
    plano = " ".join(fuente.split())
    idx = plano.find(cuerpo.split(" ")[0])
    return idx == 0 or plano[idx - 1] == " "


def test_extracto_corto_se_devuelve_entero_sin_puntos():
    texto = "un fallo breve sobre daño moral."
    assert _extracto(texto, ["daño"]) == texto


def test_extracto_no_arranca_a_mitad_de_palabra():
    # 'responsabilidad' aparece pasada la mitad; con recorte crudo el extracto
    # empezaría dentro de 'jurisprudencia' o 'consideraciones'.
    texto = (
        "En el marco de las consideraciones generales que la jurisprudencia de "
        "esta Corte ha desarrollado a lo largo de numerosos precedentes sobre la "
        "materia, corresponde recordar que la responsabilidad del Estado por su "
        "actividad lícita exige la reunión de ciertos requisitos ineludibles que "
        "la doctrina y los fallos han precisado con el correr del tiempo."
    )
    ext = _extracto(texto, _terminos("responsabilidad del estado"))
    assert "responsabilidad" in ext
    assert _sin_cortar_palabra(ext, texto)
    # arranca en un borde: o limpio, o con "…" seguido de palabra entera
    cuerpo = ext.lstrip("…")
    assert cuerpo[:1] != " "


def test_extracto_prefiere_arrancar_en_una_oracion():
    texto = (
        "Una primera cuestión quedó resuelta en instancias anteriores y no llega "
        "discutida a esta etapa del proceso judicial. La cámara admitió el "
        "recurso extraordinario federal por hallarse en juego la interpretación "
        "de normas de naturaleza federal y su decisión ser contraria al derecho "
        "que el apelante funda en ellas de manera directa e inmediata."
    )
    ext = _extracto(texto, _terminos("recurso extraordinario federal"))
    assert ext.startswith("La cámara admitió")  # oración entera, sin "…"


def test_extracto_termino_cerca_del_inicio_no_lleva_puntos_suspensivos():
    texto = ("El amparo contra el Estado Nacional " + "palabra " * 60).strip()
    ext = _extracto(texto, _terminos("amparo contra el estado"))
    assert ext.startswith("El amparo")
    assert ext.endswith("…")


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

    # sin ningún fallo que lo cite, las entrantes son una lista vacía (no falta
    # la clave)
    assert cuerpo["citas_entrantes"] == []


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
    assert cuerpo["citas_entrantes"] == []


def test_fallo_detalle_citas_salientes_salen_de_la_tabla(datos_tmp):
    """Desde PR-C1, si la tabla `citas` tiene filas para el fallo se leen de
    ahí (no se recalculan del texto): el pipeline las persistió en `estructurar`.
    """
    conn, repo = _base_migrada()
    _tomo_id, fallo_id = _fallo_con_secciones(
        repo,
        cita="348:100",
        numero=348,
        secciones=[("mayoria", None, "Texto del fallo, sin ninguna cita literal.")],
        pagina_inicio=100,
        pagina_fin=110,
    )
    repo.insert_citas(
        fallo_id, [(311, 2478, "conf. Fallos: 311:2478, considerando 4°")]
    )
    conn.close()

    cuerpo = _cliente().get("/api/fallos/348:100").json()
    assert len(cuerpo["citas_salientes"]) == 1
    assert cuerpo["citas_salientes"][0]["tomo_citado"] == 311
    assert cuerpo["citas_salientes"][0]["pagina_citada"] == 2478


def test_fallo_detalle_muestra_quien_lo_cita(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    citado = repo.insert_fallo(
        tomo_id, "Citado c/ Estado", cita="348:100", pagina_inicio=100, pagina_fin=110
    )
    repo.conn.execute(
        "INSERT INTO secciones (fallo_id, tipo, orden, texto)"
        " VALUES (?, 'mayoria', 0, ?)",
        (citado, "Fallo citado, sin citas propias."),
    )
    citante = repo.insert_fallo(
        tomo_id, "Citante c/ Otro", cita="348:250", pagina_inicio=250, pagina_fin=260
    )
    repo.conn.execute(
        "INSERT INTO secciones (fallo_id, tipo, orden, texto)"
        " VALUES (?, 'mayoria', 0, ?)",
        (citante, "Se remite a Fallos: 348:105 por análogas razones."),
    )
    repo.conn.commit()
    repo.insert_citas(
        citante, [(348, 105, "Se remite a Fallos: 348:105 por análogas razones.")]
    )
    conn.close()

    cuerpo = _cliente().get("/api/fallos/348:100").json()
    assert len(cuerpo["citas_entrantes"]) == 1
    entrante = cuerpo["citas_entrantes"][0]
    assert entrante["cita"] == "348:250"
    assert entrante["caratula"] == "Citante c/ Otro"
    assert entrante["pagina_citada"] == 105
    assert "análogas razones" in entrante["contexto"]

    # el que cita no tiene entrantes propias
    otro = _cliente().get("/api/fallos/348:250").json()
    assert otro["citas_entrantes"] == []


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


# --- /api/estado: progreso y error por tomo (PR-23) ------------------------ #


def test_estado_muestra_progreso_a_medio_camino(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id, estado="estructurado")
    conn.close()

    r = _cliente().get("/api/estado")
    tomo = r.json()["tomos"][0]
    assert tomo["estado"] == "estructurado"
    assert tomo["etapas_hechas"] == 5  # descargar..estructurar
    assert tomo["etapas_total"] == 8
    assert tomo["error"] is None


def test_estado_muestra_el_error_de_una_etapa_fallida(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id, estado="estructurado")
    from spectre.db import ahora_iso

    conn.execute(
        "INSERT INTO jobs (tipo, payload, estado, error, creado_at)"
        " VALUES ('pipeline.fragmentar', ?, 'fallido', 'boom: algo se rompió', ?)",
        (json.dumps({"tomo_id": tomo_id}), ahora_iso()),
    )
    conn.commit()
    conn.close()

    r = _cliente().get("/api/estado")
    tomo = r.json()["tomos"][0]
    assert tomo["error"] == {"etapa": "fragmentar", "mensaje": "boom: algo se rompió"}


def test_estado_requiere_ocr_no_cuenta_como_error(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id, estado="extraido", calidad="requiere_ocr")
    conn.close()

    r = _cliente().get("/api/estado")
    tomo = r.json()["tomos"][0]
    assert tomo["error"] is None  # frenado por D-10, no por una etapa rota


# --- POST /api/tomos/{numero}/indexar (PR-23) ------------------------------ #


def test_indexar_sin_csjn_tomo_id_da_400_y_no_registra_nada(datos_tmp):
    # El PDF se baja por el id interno de la CSJN (no el número de tomo): sin
    # él no hay descarga posible. La API corta con un 400 legible en vez de
    # registrar un tomo que reventaría en la etapa `descargar` y quedaría a la
    # vista con un error de programador.
    r = _cliente().post("/api/tomos/999/indexar", json={})
    assert r.status_code == 400
    assert "csjn catalog" in r.json()["detail"]

    # y no quedó ningún tomo registrado
    assert _cliente().get("/api/estado").json()["tomos"] == []


def test_indexar_con_csjn_tomo_id_en_blanco_tambien_da_400(datos_tmp):
    for valor in ("", "   "):
        r = _cliente().post("/api/tomos/999/indexar", json={"csjn_tomo_id": valor})
        assert r.status_code == 400
    assert _cliente().get("/api/estado").json()["tomos"] == []


def test_indexar_sin_id_se_permite_si_el_tomo_ya_tiene_uno(datos_tmp):
    # Retomar una indexación: el tomo ya está registrado con su id, un POST
    # sin cuerpo lo deja seguir (no 400). Se lo deja `indexado` para que el
    # pipeline en segundo plano sea un no-op y el test no toque la red.
    conn, repo = _base_migrada()
    repo.insert_tomo(348, csjn_tomo_id="445", estado="indexado")
    conn.close()

    r = _cliente().post("/api/tomos/348/indexar", json={})
    assert r.status_code == 202
    estado = _cliente().get("/api/estado").json()
    assert len(estado["tomos"]) == 1
    assert estado["tomos"][0]["estado"] == "indexado"


def test_indexar_sin_id_se_permite_si_el_tomo_ya_tiene_pdf(datos_tmp):
    conn, repo = _base_migrada()
    repo.insert_tomo(348, pdf_path="/algun/lado/348.pdf", estado="indexado")
    conn.close()

    r = _cliente().post("/api/tomos/348/indexar", json={})
    assert r.status_code == 202


@pytest.fixture
def _modelo_falso(monkeypatch):
    from spectre.embed.base import EmbeddingModel

    class _Falso(EmbeddingModel):
        nombre = "falso-biblioteca"
        dimension = 4

        def embed(self, textos):
            return [[1.0, 0.0, 0.0, 0.0] for _ in textos]

    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", lambda nombre=None: _Falso())


def test_indexar_desde_csjn_con_descarga_falsa_termina_indexado(
    monkeypatch, datos_tmp, _modelo_falso
):
    from spectre.corpus.csjn.download import Descarga

    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"

    def descarga_falsa(csjn_tomo_id, destino, **_kwargs):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(fixture.read_bytes())
        return Descarga(
            ruta=destino,
            sha256="falso",
            bytes=destino.stat().st_size,
            reutilizada=False,
        )

    import spectre.corpus.csjn as csjn_pkg

    monkeypatch.setattr(csjn_pkg, "descargar_tomo", descarga_falsa)

    r = _cliente().post("/api/tomos/348/indexar", json={"csjn_tomo_id": "447"})
    assert r.status_code == 202
    assert r.json()["estado"] == "registrado"  # instantáneo, antes de correr

    estado = _cliente().get("/api/estado").json()
    tomo = estado["tomos"][0]
    assert tomo["estado"] == "indexado"
    assert tomo["etapas_hechas"] == 8
    assert tomo["error"] is None
    assert estado["chunks"] == 6


def test_indexar_es_idempotente_sobre_un_tomo_ya_registrado(datos_tmp):
    conn, repo = _base_migrada()
    repo.insert_tomo(999, csjn_tomo_id="123", estado="indexado")
    conn.close()

    primero = _cliente().post("/api/tomos/999/indexar", json={}).json()
    segundo = _cliente().post("/api/tomos/999/indexar", json={}).json()
    assert primero["numero"] == segundo["numero"] == 999
    # no duplica el tomo
    estado = _cliente().get("/api/estado").json()
    assert len(estado["tomos"]) == 1


# --- POST /api/tomos/{numero}/subir (PR-23) --------------------------------- #


def test_subir_pdf_no_pdf_da_400(datos_tmp):
    r = _cliente().post(
        "/api/tomos/348/subir",
        files={"archivo": ("no-es-un-pdf.txt", b"hola", "text/plain")},
    )
    assert r.status_code == 400


def test_subir_pdf_termina_indexado(datos_tmp, _modelo_falso):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    with open(fixture, "rb") as f:
        r = _cliente().post(
            "/api/tomos/348/subir",
            files={"archivo": ("348.pdf", f, "application/pdf")},
        )
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["numero"] == 348
    assert cuerpo["estado"] == "descargado"  # salta la etapa `descargar` (D-9)

    estado = _cliente().get("/api/estado").json()
    tomo = estado["tomos"][0]
    assert tomo["estado"] == "indexado"
    assert tomo["etapas_hechas"] == 8
    assert estado["chunks"] == 6

    s = get_settings()
    assert (s.tomos_dir / "348.pdf").is_file()


# --- sumarios oficiales (PR-C2b) ----------------------------------------- #


def test_fallo_detalle_incluye_sumarios(datos_tmp):
    conn, repo = _base_migrada()
    _tomo_id, fallo_id = _fallo_con_secciones(
        repo,
        cita="348:34",
        numero=348,
        secciones=[("mayoria", None, "Texto del fallo.")],
        pagina_inicio=34,
        pagina_fin=40,
    )
    texto = "El interés se devenga desde la queja."
    repo.reemplazar_sumarios_de_fallo(
        fallo_id, [(0, texto, ["DEPOSITO PREVIO"], "ADMIN", "1")]
    )
    conn.close()

    cuerpo = _cliente().get("/api/fallos/348:34").json()
    assert len(cuerpo["sumarios"]) == 1
    s = cuerpo["sumarios"][0]
    assert s["texto"].startswith("El interés se devenga")
    assert s["voces"] == ["DEPOSITO PREVIO"]
    assert s["materia"] == "ADMIN"


def test_fallo_detalle_sin_sumarios_da_lista_vacia(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_con_secciones(repo, cita="348:1", secciones=[("mayoria", None, "texto")])
    conn.close()
    assert _cliente().get("/api/fallos/348:1").json()["sumarios"] == []


def test_buscar_incluye_sumarios_y_filtra_por_voz(datos_tmp):
    conn, repo = _base_migrada()
    f1 = _fallo_con_seccion_y_chunks(
        repo, cita="348:1", textos=["prescripción de la acción penal desde el hecho"]
    )
    f2 = _fallo_con_seccion_y_chunks(
        repo, cita="348:2", textos=["prescripción de la acción penal en otro caso"]
    )
    repo.reemplazar_sumarios_de_fallo(
        f1, [(0, "Doctrina sobre la prescripción.", ["PRESCRIPCION"], "PENAL", None)]
    )
    repo.reemplazar_sumarios_de_fallo(
        f2, [(0, "Otra doctrina.", ["COSTAS"], "PROCESAL", None)]
    )
    conn.close()

    def _citas(**extra):
        params = {"q": "prescripción de la acción penal", "solo_lexico": "true"}
        params.update(extra)
        return _cliente().get("/api/buscar", params=params).json()["resultados"]

    todos = _citas()
    assert {r["cita"] for r in todos} == {"348:1", "348:2"}
    por_cita = {r["cita"]: r for r in todos}
    assert por_cita["348:1"]["sumarios"][0]["voces"] == ["PRESCRIPCION"]
    assert por_cita["348:2"]["sumarios"][0]["texto"] == "Otra doctrina."

    solo_voz = _citas(voz="prescripcion")
    assert [r["cita"] for r in solo_voz] == ["348:1"]
    solo_materia = _citas(materia="PROCESAL")
    assert [r["cita"] for r in solo_materia] == ["348:2"]
    assert _citas(voz="no existe") == []


def test_endpoint_voces_autocompleta_contra_lo_local(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1", pagina_inicio=1)
    repo.reemplazar_sumarios_de_fallo(
        fallo_id,
        [(0, "x", ["CONTRATO ADMINISTRATIVO", "CONTRATO DE TRABAJO"], None, None)],
    )
    conn.close()

    datos = _cliente().get("/api/voces", params={"q": "contrato"}).json()
    assert [v["valor"] for v in datos["voces"]] == [
        "CONTRATO ADMINISTRATIVO",
        "CONTRATO DE TRABAJO",
    ]
    assert _cliente().get("/api/voces", params={"q": "zzz"}).json() == {"voces": []}
    assert _cliente().get("/api/voces", params={"q": ""}).status_code == 422


def test_endpoint_materias_lista_las_del_corpus(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1", pagina_inicio=1)
    repo.reemplazar_sumarios_de_fallo(
        fallo_id, [(0, "x", [], "PENAL", None), (1, "y", [], "ADMIN", None)]
    )
    conn.close()
    assert _cliente().get("/api/materias").json() == {"materias": ["ADMIN", "PENAL"]}


def test_estado_incluye_conteo_de_sumarios_por_tomo(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id, estado="indexado")
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1", pagina_inicio=1)
    repo.reemplazar_sumarios_de_fallo(
        fallo_id, [(0, "a", [], None, None), (1, "b", [], None, None)]
    )
    conn.close()
    assert _cliente().get("/api/estado").json()["tomos"][0]["sumarios"] == 2


def test_sync_sumarios_tomo_inexistente_da_404(datos_tmp):
    conn, _repo = _base_migrada()
    conn.close()
    assert _cliente().post("/api/tomos/999/sumarios/sync").status_code == 404


def test_sync_sumarios_lanza_la_tarea_en_segundo_plano(monkeypatch, datos_tmp):
    conn, repo = _base_migrada()
    repo.insert_tomo(348, estado="indexado")
    conn.close()

    llamadas = []
    import spectre.api.app as app_mod

    monkeypatch.setattr(
        app_mod, "sincronizar_tomo", lambda c, n, **kw: llamadas.append(n)
    )

    r = _cliente().post("/api/tomos/348/sumarios/sync")
    assert r.status_code == 202
    assert r.json()["numero"] == 348
    assert llamadas == [348]


# --- filtro por tipo de parte (PR-C5) ---------------------------------- #


def _fallo_parte(repo, *, cita, textos, actor_tipo, demandado_tipo):
    fallo_id = _fallo_con_seccion_y_chunks(repo, cita=cita, textos=textos)
    repo.actualizar_fallo(
        fallo_id,
        actor="Actor",
        actor_tipo=actor_tipo,
        demandado="Demandado",
        demandado_tipo=demandado_tipo,
    )
    return fallo_id


def test_buscar_filtra_por_tipo_de_parte(datos_tmp):
    conn, repo = _base_migrada()
    _fallo_parte(
        repo,
        cita="348:1",
        textos=["responsabilidad del Estado por su actividad lícita"],
        actor_tipo="empresa",
        demandado_tipo="estado",
    )
    _fallo_parte(
        repo,
        cita="348:2",
        textos=["responsabilidad del Estado en otro caso distinto"],
        actor_tipo="persona_fisica",
        demandado_tipo="persona_fisica",
    )
    conn.close()

    def _citas(**extra):
        params = {"q": "responsabilidad del Estado", "solo_lexico": "true"}
        params.update(extra)
        return [
            r["cita"]
            for r in _cliente().get("/api/buscar", params=params).json()["resultados"]
        ]

    assert set(_citas()) == {"348:1", "348:2"}
    assert _citas(parte="estado") == ["348:1"]
    assert _citas(parte="empresa") == ["348:1"]
    assert _citas(parte="persona_fisica") == ["348:2"]
    assert _citas(parte="organismo") == []


def test_buscar_parte_invalida_es_error(datos_tmp):
    r = _cliente().get("/api/buscar", params={"q": "algo", "parte": "no-existe"})
    assert r.status_code == 422


def test_fallo_detalle_incluye_partes_y_tipos(datos_tmp):
    conn, repo = _base_migrada()
    _tomo_id, fallo_id = _fallo_con_secciones(
        repo, cita="348:1", secciones=[("mayoria", None, "texto")]
    )
    repo.actualizar_fallo(
        fallo_id,
        actor="Y.P.F. S.A.",
        actor_tipo="empresa",
        demandado="Provincia de Mendoza",
        demandado_tipo="estado",
    )
    conn.close()

    cuerpo = _cliente().get("/api/fallos/348:1").json()
    assert cuerpo["actor"] == "Y.P.F. S.A."
    assert cuerpo["actor_tipo"] == "empresa"
    assert cuerpo["demandado"] == "Provincia de Mendoza"
    assert cuerpo["demandado_tipo"] == "estado"


def test_reclasificar_partes_endpoint(datos_tmp):
    conn, repo = _base_migrada()
    tomo_id = repo.insert_tomo(348, estado="indexado")
    repo.insert_fallo(
        tomo_id, "Pérez, Juan c/ Estado Nacional", cita="348:1", pagina_inicio=1
    )
    repo.insert_fallo(tomo_id, "Acme S.A. c/ AFIP", cita="348:2", pagina_inicio=2)
    conn.close()

    r = _cliente().post("/api/fallos/reclasificar-partes")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["fallos"] == 2
    assert cuerpo["con_actor_tipo"] == 2
    assert cuerpo["por_tipo"]["estado"] == 2

    # y quedó persistido
    detalle = _cliente().get("/api/fallos/348:1").json()
    assert detalle["actor_tipo"] == "persona_fisica"
    assert detalle["demandado_tipo"] == "estado"
