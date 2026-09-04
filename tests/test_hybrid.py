"""PR-15 — búsqueda híbrida: fusión RRF de léxico (FTS5) + vectorial (LanceDB).

Criterio de aceptación (plan §6): un set de 10 consultas de prueba escritas a
mano, con el resultado esperado documentado en el repo (ver
`docs/qa/consultas-PR-15.md`).

`test_rrf_*` prueban la fórmula de fusión aislada (sin DB ni índices).
`test_buscar_hibrido_*` arman una base + un índice vectorial de juguete
(vectores de mano, no un modelo real) para probar la fusión, el fallback sin
vector y los filtros de metadatos de punta a punta.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("lancedb")

from spectre.db import Repo, connect, migrate
from spectre.index import IndiceVectorial
from spectre.search import buscar_hibrido
from spectre.search.hybrid import _rrf

# --- la fórmula RRF, aislada --------------------------------------------- #


def test_rrf_suma_por_lista():
    fusion = dict(_rrf([[1, 2, 3]], k=60))
    assert fusion[1] == pytest.approx(1 / 61)
    assert fusion[2] == pytest.approx(1 / 62)
    assert fusion[3] == pytest.approx(1 / 63)


def test_rrf_aparecer_en_las_dos_listas_rankea_mas_arriba():
    # 1 aparece en las dos listas (aunque más atrás en la segunda); 2 y 3 en
    # una sola. El puntaje combinado de 1 tiene que superar al de 2 solo.
    fusion = dict(_rrf([[2, 1], [1, 3]], k=60))
    assert fusion[1] > fusion[2]
    assert fusion[1] > fusion[3]


def test_rrf_una_sola_lista_preserva_el_orden():
    orden = [cid for cid, _ in _rrf([[10, 20, 30]])]
    assert orden == [10, 20, 30]


def test_rrf_listas_simetricas_empatan_los_extremos():
    # 3 y 5 están en posiciones espejadas entre las dos listas: mismo puntaje.
    fusion = dict(_rrf([[5, 4, 3], [3, 4, 5]]))
    assert fusion[5] == pytest.approx(fusion[3])


def test_rrf_listas_vacias():
    assert _rrf([]) == []
    assert _rrf([[], []]) == []


# --- integración: DB real + índice vectorial de juguete ------------------ #


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "spectre.db")
    migrate(c)
    yield c
    c.close()


def _fallo_con_chunks(repo, textos, *, cita, fecha=None, tribunal_origen=None):
    numero = repo.conn.execute("SELECT count(*) FROM tomos").fetchone()[0] + 1
    tomo_id = repo.insert_tomo(numero)
    fallo_id = repo.insert_fallo(
        tomo_id, "A c/ B", cita=cita, fecha=fecha, tribunal_origen=tribunal_origen
    )
    repo.insert_chunks(fallo_id, [(None, i, t, None) for i, t in enumerate(textos)])
    return [c.id for c in repo.list_chunks_de_fallo(fallo_id)]


def test_buscar_hibrido_fusiona_las_dos_listas(conn, tmp_path):
    repo = Repo(conn)
    # A: matchea fuerte en los dos índices (debería rankear primero: repite la
    # frase, mayor bm25 que B, y su vector es el más cercano a la consulta).
    # B: solo lexico (matchea una sola vez, no está en el índice vectorial).
    # C: solo vectorial (texto sin relación, pero vector cercano).
    # D: ninguno de los dos (ni el texto ni el vector se acercan) — no se
    # indexa en ningún lado, así que ni aparece como candidato.
    (a,) = _fallo_con_chunks(
        repo,
        ["prescripción de la acción penal. prescripción de la acción penal."],
        cita="1:1",
    )
    (b,) = _fallo_con_chunks(repo, ["prescripción de la acción penal."], cita="1:2")
    (c,) = _fallo_con_chunks(repo, ["un texto sin relación"], cita="1:3")
    _fallo_con_chunks(repo, ["otro texto distinto"], cita="1:4")

    idx = IndiceVectorial(tmp_path / "vec", dimension=2)
    idx.upsert([(a, [1.0, 0.0], "m"), (c, [0.8, 0.6], "m")])

    resultados = buscar_hibrido(
        conn, idx, "prescripción de la acción penal", [1.0, 0.0], k=10
    )
    ids = [r.chunk_id for r in resultados]
    assert ids[0] == a  # en las dos listas: mejor puntaje combinado
    assert b in ids and c in ids  # cada uno aparece por su propio índice

    ganador = next(r for r in resultados if r.chunk_id == a)
    assert ganador.rank_lexico == 0
    assert ganador.rank_vectorial == 0
    solo_lexico = next(r for r in resultados if r.chunk_id == b)
    assert solo_lexico.rank_lexico is not None
    assert solo_lexico.rank_vectorial is None


def test_buscar_hibrido_sin_vector_es_solo_lexico(conn, tmp_path):
    repo = Repo(conn)
    (a,) = _fallo_con_chunks(repo, ["responsabilidad civil médica"], cita="1:1")
    idx = IndiceVectorial(tmp_path / "vec", dimension=2)

    resultados = buscar_hibrido(conn, idx, "responsabilidad civil médica", None)
    assert [r.chunk_id for r in resultados] == [a]
    assert resultados[0].rank_vectorial is None


def test_buscar_hibrido_k_limita_resultados(conn, tmp_path):
    repo = Repo(conn)
    ids = _fallo_con_chunks(
        repo, [f"recurso extraordinario {i}" for i in range(5)], cita="1:1"
    )
    idx = IndiceVectorial(tmp_path / "vec", dimension=2)
    idx.upsert([(cid, [1.0, 0.0], "m") for cid in ids])

    resultados = buscar_hibrido(
        conn, idx, "recurso extraordinario", [1.0, 0.0], k=2, candidatos=10
    )
    assert len(resultados) == 2


def test_buscar_hibrido_filtra_por_anio(conn, tmp_path):
    repo = Repo(conn)
    (viejo,) = _fallo_con_chunks(
        repo, ["prescripción penal"], cita="1:1", fecha="2018-01-01"
    )
    (nuevo,) = _fallo_con_chunks(
        repo, ["prescripción penal"], cita="1:2", fecha="2024-01-01"
    )
    idx = IndiceVectorial(tmp_path / "vec", dimension=2)
    idx.upsert([(viejo, [1.0, 0.0], "m"), (nuevo, [1.0, 0.0], "m")])

    resultados = buscar_hibrido(conn, idx, "prescripción penal", [1.0, 0.0], anio=2024)
    assert [r.chunk_id for r in resultados] == [nuevo]


def test_buscar_hibrido_filtra_por_tribunal_y_seccion(conn, tmp_path):
    repo = Repo(conn)
    numero = repo.conn.execute("SELECT count(*) FROM tomos").fetchone()[0] + 1
    tomo_id = repo.insert_tomo(numero)
    fallo_id = repo.insert_fallo(
        tomo_id, "A c/ B", cita="1:1", tribunal_origen="Cámara Federal"
    )
    cur = repo.conn.execute(
        "INSERT INTO secciones (fallo_id, tipo, orden) VALUES (?, 'disidencia', 0)",
        (fallo_id,),
    )
    seccion_id = cur.lastrowid
    repo.conn.commit()
    repo.insert_chunks(
        fallo_id, [(seccion_id, 0, "voto en disidencia sobre el tema", None)]
    )
    chunk_id = repo.list_chunks_de_fallo(fallo_id)[0].id

    idx = IndiceVectorial(tmp_path / "vec", dimension=2)
    idx.upsert([(chunk_id, [1.0, 0.0], "m")])

    ok = buscar_hibrido(
        conn,
        idx,
        "voto disidencia",
        [1.0, 0.0],
        tribunal_origen="Cámara Federal",
        tipo_seccion="disidencia",
    )
    assert [r.chunk_id for r in ok] == [chunk_id]

    vacio = buscar_hibrido(
        conn, idx, "voto disidencia", [1.0, 0.0], tipo_seccion="mayoria"
    )
    assert vacio == []


# --- aceptación: 10 consultas sobre el Tomo 348 completo ----------------- #

TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"

# (consulta, cita esperada, posición máxima 0-based en la lista fusionada
# con k=5) — documentado en detalle, con el porqué de cada una, en
# docs/qa/consultas-PR-15.md.
_CONSULTAS_SIN_FILTRO = [
    ("Fallos: 337:315", "348:189", 2),
    ("Zárate Pablo Federico", "348:380", 0),
    ("prescripción de la acción penal", "348:611", 4),
    ("despido injustificado", "348:834", 0),
    ("extradición de un ciudadano extranjero", "348:644", 4),
    ("medida cautelar contra el municipio", "348:95", 0),
    ("seguridad social jubilación", "348:31", 0),
    ("amparo contra el Estado Nacional", "348:895", 0),
]


@pytest.mark.slow
def test_aceptacion(tmp_path):
    pytest.importorskip("sentence_transformers", reason="falta [embed]")
    if not TOMO_348.is_file():
        pytest.skip("falta data/tomos/348.pdf")

    from spectre.chunking import fragmentar_fallo
    from spectre.corpus.fallo import (
        extraer_metadatos,
        parsear_indice,
        partir_secciones,
        segmentar,
        texto_del_fallo_paginado,
    )
    from spectre.corpus.pdf import extraer_texto
    from spectre.embed import cargar_modelo

    conn = connect(tmp_path / "spectre.db")
    migrate(conn)
    repo = Repo(conn)

    paginas = extraer_texto(TOMO_348)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(parsear_indice(TOMO_348), paginas, tomo_numero=348)
    tomo_id = repo.insert_tomo(348)

    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin,
        )
        texto = "\n".join(t for _, t in paginado)
        meta = extraer_metadatos(texto, caratula=f.caratula)
        chunks = fragmentar_fallo(
            partir_secciones(texto),
            paginado,
            cita=f.cita,
            pagina_inicio=f.pagina_inicio,
        )
        fallo_id = repo.insert_fallo(
            tomo_id,
            f.caratula,
            cita=f.cita,
            pagina_inicio=f.pagina_inicio,
            pagina_fin=f.pagina_fin,
            fecha=meta.fecha,
            tribunal_origen=meta.tribunal_origen,
            tipo_recurso=meta.tipo_recurso,
        )
        # Persistir las secciones reales (D-4): hace falta para poder filtrar
        # por tipo_seccion. Ningún PR anterior las guarda todavía (PR-19 lo
        # hará para el pipeline completo); acá se insertan directo porque el
        # criterio de aceptación pide probar justamente ese filtro.
        secciones_ids: dict[int, int] = {}
        for c in chunks:
            if c.seccion_orden not in secciones_ids:
                cur = conn.execute(
                    "INSERT INTO secciones (fallo_id, tipo, autor, orden)"
                    " VALUES (?, ?, ?, ?)",
                    (fallo_id, c.seccion_tipo, c.seccion_autor, c.seccion_orden),
                )
                secciones_ids[c.seccion_orden] = cur.lastrowid
        conn.commit()
        repo.insert_chunks(
            fallo_id,
            [
                (secciones_ids[c.seccion_orden], c.orden, c.texto, c.pagina_oficial)
                for c in chunks
            ],
        )

    modelo = cargar_modelo()
    idx = IndiceVectorial(tmp_path / "vec", dimension=modelo.dimension)
    todos = conn.execute("SELECT id, texto FROM chunks").fetchall()
    lote = 256
    for k in range(0, len(todos), lote):
        trozo = todos[k : k + lote]
        vectores = modelo.embed([row["texto"] for row in trozo])
        idx.upsert(
            (row["id"], v, modelo.nombre)
            for row, v in zip(trozo, vectores, strict=True)
        )
    assert idx.contar() == len(todos) == 1112  # ver plan PR-11

    for consulta, cita_esperada, posicion_maxima in _CONSULTAS_SIN_FILTRO:
        vector = modelo.embed_uno(consulta)
        resultados = buscar_hibrido(conn, idx, consulta, vector, k=5)
        citas = [
            repo.get_fallo(repo.get_chunk(r.chunk_id).fallo_id).cita for r in resultados
        ]
        assert cita_esperada in citas, (
            f"{consulta!r}: se esperaba {cita_esperada} entre {citas}"
        )
        posicion = citas.index(cita_esperada)
        assert posicion <= posicion_maxima, (
            f"{consulta!r}: {cita_esperada} en posición {posicion}, "
            f"se esperaba <= {posicion_maxima}"
        )

    # filtro por tribunal: "Sala L de la Cámara Nacional de Apelaciones en lo
    # Civil" la comparten solo dos fallos del tomo (348:821 y 348:834); el
    # segundo es justamente el que ya encuentra "despido injustificado" sin
    # filtrar (arriba). Filtrando por ese tribunal tiene que seguir estando.
    vector = modelo.embed_uno("despido injustificado")
    con_tribunal = buscar_hibrido(
        conn,
        idx,
        "despido injustificado",
        vector,
        k=10,
        tribunal_origen="Sala L de la Cámara Nacional de Apelaciones en lo Civil",
    )
    citas_filtradas = {
        repo.get_fallo(repo.get_chunk(r.chunk_id).fallo_id).cita for r in con_tribunal
    }
    assert citas_filtradas <= {"348:821", "348:834"}
    assert "348:834" in citas_filtradas

    # filtro por tipo_seccion: "voto en disidencia" restringido a secciones
    # tipo 'disidencia' — D-4, nunca devolver una disidencia como si fuera la
    # doctrina de la Corte. Todo lo que vuelva tiene que venir de una sección
    # marcada disidencia, no solo mencionar la palabra.
    vector = modelo.embed_uno("voto en disidencia")
    solo_disidencia = buscar_hibrido(
        conn, idx, "voto en disidencia", vector, k=10, tipo_seccion="disidencia"
    )
    assert solo_disidencia != []
    for r in solo_disidencia:
        seccion_id = repo.get_chunk(r.chunk_id).seccion_id
        tipo = conn.execute(
            "SELECT tipo FROM secciones WHERE id = ?", (seccion_id,)
        ).fetchone()[0]
        assert tipo == "disidencia"

    conn.close()
