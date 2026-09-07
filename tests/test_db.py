"""PR-02 — esquema SQLite, migraciones idempotentes y repositorio.

Criterio de aceptación (plan §6): crear la base, insertar un tomo y leerlo;
test de idempotencia de la migración.

PR-12 agrega el registro del modelo de embedding por chunk
(`chunks_pendientes_de_embedding`, `marcar_chunks_embebidos`): ver la sección
"chunks y registro del modelo de embedding". PR-14 agrega la migración
`0003_chunks_fts` (FTS5 sobre `chunks.texto`, ver "índice léxico (FTS5,
PR-14)"); el comportamiento de búsqueda en sí se prueba en `test_lexical.py`,
acá solo que la migración deja el esquema (tabla + triggers) en su lugar y
sincronizado.
"""

import sqlite3

import pytest

from spectre.db import Repo, connect, migraciones_disponibles, migrate


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "spectre.db")
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    migrate(conn)
    return Repo(conn)


def _tablas(conn):
    return {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _dump_esquema(conn):
    return sorted(
        r[0]
        for r in conn.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
    )


# --- migraciones -------------------------------------------------------- #


MIGRACIONES = [
    "0001_initial",
    "0002_jobs_estado_check",
    "0003_chunks_fts",
    "0004_tomos_estado_check",
    "0005_sumarios",
]


def test_migrate_crea_el_esquema_completo(conn):
    aplicadas = migrate(conn)
    assert aplicadas == MIGRACIONES
    esperadas = {
        "tomos",
        "paginas",
        "fallos",
        "secciones",
        "chunks",
        "citas",
        "jobs",
        "chunks_fts",
        "sumarios",
        "voces",
        "fallo_voces",
        "_migraciones",
    }
    assert esperadas <= _tablas(conn)


def test_migrate_es_idempotente(conn):
    assert migrate(conn) == MIGRACIONES
    esquema_1 = _dump_esquema(conn)

    assert migrate(conn) == []  # nada pendiente, sin error
    assert migrate(conn) == []
    assert _dump_esquema(conn) == esquema_1

    filas = conn.execute("SELECT count(*) FROM _migraciones").fetchone()[0]
    assert filas == len(MIGRACIONES)


def test_migrate_sobre_base_ya_migrada_en_otra_conexion(tmp_path):
    ruta = tmp_path / "spectre.db"
    c1 = connect(ruta)
    assert migrate(c1) == MIGRACIONES
    c1.close()

    c2 = connect(ruta)
    assert migrate(c2) == []
    c2.close()


def test_migraciones_disponibles_en_orden():
    nombres = [p.name for p in migraciones_disponibles()]
    assert nombres == [f"{v}.sql" for v in MIGRACIONES]


def test_jobs_estado_tiene_check(conn):
    migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO jobs (tipo, estado, creado_at) "
            "VALUES ('x', 'inventado', '2026-01-01T00:00:00+00:00')"
        )


def test_tomos_estado_tiene_check(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_tomo(1, estado="inventado")


def test_tomos_estado_acepta_todo_el_vocabulario_del_pipeline(repo):
    # PR-19 congela el vocabulario en 0004_tomos_estado_check.sql; si esto
    # revienta, el CHECK y `jobs/pipeline.py` (ETAPAS) se desincronizaron.
    for i, estado in enumerate(
        (
            "registrado",
            "descargado",
            "extraido",
            "limpio",
            "segmentado",
            "estructurado",
            "fragmentado",
            "embebido",
            "indexado",
        )
    ):
        repo.insert_tomo(i + 1, estado=estado)


# --- tomos ------------------------------------------------------------ #


def test_insert_y_leer_tomo(repo):
    tomo_id = repo.insert_tomo(
        348,
        anio=2025,
        pdf_path="data/tomos/348.pdf",
        sha256="abc123",
        calidad="digital",
        paginas=968,
        offset_pagina=6,
        estado="registrado",
    )
    assert tomo_id == 1

    tomo = repo.get_tomo(tomo_id)
    assert tomo is not None
    assert tomo.numero == 348
    assert tomo.anio == 2025
    assert tomo.sha256 == "abc123"
    assert tomo.calidad == "digital"
    assert tomo.paginas == 968
    assert tomo.offset_pagina == 6
    assert tomo.estado == "registrado"
    assert tomo.indexado_at is None


def test_get_tomo_por_numero_y_defaults(repo):
    repo.insert_tomo(100)
    tomo = repo.get_tomo_por_numero(100)
    assert tomo is not None
    assert tomo.calidad == "desconocida"  # default del esquema
    assert tomo.estado == "registrado"
    assert tomo.volumen is None


def test_get_tomo_inexistente_es_none(repo):
    assert repo.get_tomo(999) is None
    assert repo.get_tomo_por_numero(999) is None


def test_numero_de_tomo_es_unico(repo):
    repo.insert_tomo(348)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_tomo(348)


def test_sha256_es_unico(repo):
    repo.insert_tomo(1, sha256="dup")
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_tomo(2, sha256="dup")


def test_calidad_invalida_es_rechazada(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_tomo(1, calidad="excelente")


def test_list_tomos_ordena_por_numero(repo):
    repo.insert_tomo(348)
    repo.insert_tomo(100)
    repo.insert_tomo(311)
    assert [t.numero for t in repo.list_tomos()] == [100, 311, 348]


def test_actualizar_tomo(repo):
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id, estado="segmentado", paginas=968, offset_pagina=6)
    tomo = repo.get_tomo(tomo_id)
    assert tomo.estado == "segmentado"
    assert tomo.paginas == 968
    assert tomo.offset_pagina == 6


def test_actualizar_tomo_rechaza_columnas_no_mutables(repo):
    tomo_id = repo.insert_tomo(348)
    with pytest.raises(ValueError):
        repo.actualizar_tomo(tomo_id, numero=999)
    with pytest.raises(ValueError):
        repo.actualizar_tomo(tomo_id, columna_fantasma=1)


def test_actualizar_tomo_sin_campos_es_noop(repo):
    tomo_id = repo.insert_tomo(348)
    repo.actualizar_tomo(tomo_id)
    assert repo.get_tomo(tomo_id).numero == 348


# --- páginas ---------------------------------------------------------- #


def test_insert_y_leer_pagina(repo):
    tomo_id = repo.insert_tomo(348)
    pid = repo.insert_pagina(
        tomo_id, 7, pagina_oficial=1, texto_crudo="FALLOS DE LA CORTE"
    )
    assert pid == 1
    pagina = repo.get_pagina(tomo_id, 7)
    assert pagina is not None
    assert pagina.pagina_oficial == 1
    assert pagina.texto_crudo == "FALLOS DE LA CORTE"
    assert pagina.texto_limpio is None


def test_pagina_pdf_page_unica_por_tomo(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_pagina(tomo_id, 7)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_pagina(tomo_id, 7)


def test_pagina_sin_tomo_viola_foreign_key(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_pagina(999, 1)


def test_list_y_contar_paginas(repo):
    tomo_id = repo.insert_tomo(348)
    for pdf_page in (3, 1, 2):
        repo.insert_pagina(tomo_id, pdf_page)
    assert [p.pdf_page for p in repo.list_paginas(tomo_id)] == [1, 2, 3]
    assert repo.contar_paginas(tomo_id) == 3


def test_borrar_tomo_arrastra_las_paginas(repo, conn):
    tomo_id = repo.insert_tomo(348)
    repo.insert_pagina(tomo_id, 1)
    conn.execute("DELETE FROM tomos WHERE id = ?", (tomo_id,))
    conn.commit()
    assert repo.contar_paginas(tomo_id) == 0


def test_insert_paginas_en_lote(repo):
    tomo_id = repo.insert_tomo(348)
    n = repo.insert_paginas(
        tomo_id,
        [(7, 1, "texto uno"), (8, 2, "texto dos"), (9, None, "sin oficial")],
    )
    assert n == 3
    assert repo.contar_paginas(tomo_id) == 3
    p9 = repo.get_pagina(tomo_id, 9)
    assert p9.pagina_oficial is None
    assert p9.texto_crudo == "sin oficial"
    assert p9.texto_limpio is None


def test_borrar_paginas(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_paginas(tomo_id, [(1, None, "a"), (2, None, "b")])
    assert repo.borrar_paginas(tomo_id) == 2
    assert repo.contar_paginas(tomo_id) == 0


def test_set_texto_limpio_en_lote(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_paginas(tomo_id, [(1, None, "CRUDO uno"), (2, None, "CRUDO dos")])
    p1, p2 = repo.list_paginas(tomo_id)
    n = repo.set_texto_limpio([(p1.id, "limpio uno"), (p2.id, "limpio dos")])
    assert n == 2
    assert repo.get_pagina(tomo_id, 1).texto_limpio == "limpio uno"
    assert repo.get_pagina(tomo_id, 1).texto_crudo == "CRUDO uno"  # el crudo queda


# --- fallos ---------------------------------------------------------- #


def test_insert_y_leer_fallo(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(
        tomo_id,
        "Zárate, Pablo Federico y otros c/ ENRE s/ diferencias de salarios",
        cita="348:380",
        pagina_inicio=380,
        pagina_fin=384,
        fecha="2025-04-15",
        jueces='["Rosenkrantz", "Rosatti"]',
    )
    fallo = repo.get_fallo(fid)
    assert fallo is not None
    assert fallo.cita == "348:380"
    assert fallo.pagina_inicio == 380
    assert fallo.jueces == '["Rosenkrantz", "Rosatti"]'

    assert repo.get_fallo_por_cita("348:380").id == fid


def test_cita_de_fallo_es_unica(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_fallo(tomo_id, "C c/ D", cita="348:1")


def test_cita_nula_no_colisiona(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_fallo(tomo_id, "A c/ B")
    repo.insert_fallo(tomo_id, "C c/ D")  # dos citas NULL conviven
    assert len(repo.list_fallos(tomo_id)) == 2


def test_list_fallos_ordena_por_pagina_inicio(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_fallo(tomo_id, "tercero", pagina_inicio=380)
    repo.insert_fallo(tomo_id, "primero", pagina_inicio=5)
    repo.insert_fallo(tomo_id, "segundo", pagina_inicio=145)
    assert [f.caratula for f in repo.list_fallos(tomo_id)] == [
        "primero",
        "segundo",
        "tercero",
    ]


def test_fallo_sin_tomo_viola_foreign_key(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_fallo(999, "huérfano")


def test_actualizar_fallo(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    repo.actualizar_fallo(
        fid,
        fecha="2025-04-15",
        jueces='["Rosatti"]',
        tribunal_origen="Cámara Federal",
        tipo_recurso="extraordinario",
    )
    fallo = repo.get_fallo(fid)
    assert fallo.fecha == "2025-04-15"
    assert fallo.jueces == '["Rosatti"]'
    assert fallo.tribunal_origen == "Cámara Federal"
    assert fallo.tipo_recurso == "extraordinario"
    assert fallo.caratula == "A c/ B"  # no tocado


def test_actualizar_fallo_rechaza_columnas_no_mutables(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B")
    with pytest.raises(ValueError):
        repo.actualizar_fallo(fid, caratula="otra cosa")
    with pytest.raises(ValueError):
        repo.actualizar_fallo(fid, columna_fantasma=1)


def test_actualizar_fallo_sin_campos_es_noop(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B")
    repo.actualizar_fallo(fid)
    assert repo.get_fallo(fid).caratula == "A c/ B"


def test_borrar_fallos(repo):
    tomo_id = repo.insert_tomo(348)
    repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    repo.insert_fallo(tomo_id, "C c/ D", cita="348:2")
    assert repo.borrar_fallos(tomo_id) == 2
    assert repo.list_fallos(tomo_id) == []


def test_borrar_fallos_arrastra_secciones_y_chunks(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    (seccion_id,) = repo.insert_secciones(fid, [("mayoria", None, 0, "texto")])
    repo.insert_chunks(fid, [(seccion_id, 0, "un chunk", None)])

    assert repo.borrar_fallos(tomo_id) == 1
    assert repo.list_secciones_de_fallo(fid) == []
    assert repo.contar_chunks() == 0


# --- secciones (PR-19) -------------------------------------------------- #


def test_insert_secciones_devuelve_ids_en_orden(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    ids = repo.insert_secciones(
        fid,
        [
            ("dictamen", None, 0, "texto dictamen"),
            ("mayoria", None, 1, "texto mayoria"),
            ("voto", "Rosatti", 2, "texto voto"),
        ],
    )
    assert len(ids) == 3
    assert ids == sorted(set(ids))  # tres ids distintos, sin repetir

    secciones = repo.list_secciones_de_fallo(fid)
    assert [s.tipo for s in secciones] == ["dictamen", "mayoria", "voto"]
    assert secciones[2].autor == "Rosatti"
    assert repo.get_seccion(ids[1]).texto == "texto mayoria"


def test_seccion_tipo_invalido_es_rechazado(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_secciones(fid, [("inventado", None, 0, "x")])


def test_seccion_sin_fallo_viola_foreign_key(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_secciones(999, [("mayoria", None, 0, "x")])


def test_borrar_secciones_de_fallo_arrastra_chunks(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    (seccion_id,) = repo.insert_secciones(fid, [("mayoria", None, 0, "texto")])
    repo.insert_chunks(fid, [(seccion_id, 0, "un chunk", None)])

    assert repo.borrar_secciones_de_fallo(fid) == 1
    assert repo.list_secciones_de_fallo(fid) == []
    assert repo.contar_chunks() == 0


def test_get_seccion_inexistente_es_none(repo):
    assert repo.get_seccion(999) is None


# --- chunks y registro del modelo de embedding (PR-12) ---------------- #


def _fallo_con_chunks(repo, cuantos=3):
    tomo_id = repo.insert_tomo(348)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    repo.insert_chunks(
        fallo_id,
        [(None, i, f"chunk numero {i}", 1 + i) for i in range(cuantos)],
    )
    return fallo_id


def test_insert_chunks_y_listar(repo):
    fallo_id = _fallo_con_chunks(repo, 3)
    chunks = repo.list_chunks_de_fallo(fallo_id)
    assert [c.orden for c in chunks] == [0, 1, 2]
    assert chunks[0].texto == "chunk numero 0"
    assert chunks[0].pagina_oficial == 1
    # recién insertados: sin embedding
    assert all(c.modelo_embedding is None and c.embedding_at is None for c in chunks)
    assert repo.contar_chunks() == 3


def test_chunk_sin_fallo_viola_foreign_key(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_chunks(999, [(None, 0, "huérfano", None)])


def test_chunks_pendientes_son_todos_cuando_nunca_se_embebieron(repo):
    _fallo_con_chunks(repo, 3)
    assert len(repo.chunks_pendientes_de_embedding("modelo-a")) == 3
    assert repo.contar_chunks_pendientes("modelo-a") == 3


def test_marcar_embebidos_baja_los_pendientes_y_sella_la_fecha(repo):
    fallo_id = _fallo_con_chunks(repo, 3)
    ids = [c.id for c in repo.list_chunks_de_fallo(fallo_id)]
    tocados = repo.marcar_chunks_embebidos(ids[:2], "modelo-a")
    assert tocados == 2

    pendientes = repo.chunks_pendientes_de_embedding("modelo-a")
    assert [c.id for c in pendientes] == [ids[2]]
    embebido = repo.list_chunks_de_fallo(fallo_id)[0]
    assert embebido.modelo_embedding == "modelo-a"
    assert embebido.embedding_at is not None


def test_cambiar_de_modelo_vuelve_a_marcar_todo_pendiente(repo):
    # el criterio de aceptación de PR-12: cambiar el modelo -> el sistema sabe
    # qué reindexar, sin abrir ningún PDF.
    fallo_id = _fallo_con_chunks(repo, 3)
    ids = [c.id for c in repo.list_chunks_de_fallo(fallo_id)]
    repo.marcar_chunks_embebidos(ids, "modelo-viejo")
    assert repo.chunks_pendientes_de_embedding("modelo-viejo") == []

    # config apunta ahora a otro modelo:
    pendientes = repo.chunks_pendientes_de_embedding("modelo-nuevo")
    assert [c.id for c in pendientes] == ids
    assert repo.contar_chunks_pendientes("modelo-nuevo") == 3


def test_chunks_pendientes_respeta_el_limite(repo):
    _fallo_con_chunks(repo, 5)
    assert len(repo.chunks_pendientes_de_embedding("m", limite=2)) == 2


def test_borrar_tomo_arrastra_los_chunks(repo, conn):
    fallo_id = _fallo_con_chunks(repo, 2)
    tomo_id = repo.get_fallo(fallo_id).tomo_id
    conn.execute("DELETE FROM tomos WHERE id = ?", (tomo_id,))
    conn.commit()
    assert repo.contar_chunks() == 0


def test_get_chunk(repo):
    fallo_id = _fallo_con_chunks(repo, 2)
    id_esperado = repo.list_chunks_de_fallo(fallo_id)[0].id
    assert repo.get_chunk(id_esperado).texto == "chunk numero 0"


def test_get_chunk_inexistente_es_none(repo):
    assert repo.get_chunk(999) is None


def test_list_chunks_de_tomo_junta_varios_fallos(repo):
    tomo_id = repo.insert_tomo(348)
    f1 = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    f2 = repo.insert_fallo(tomo_id, "C c/ D", cita="348:2")
    otro_tomo = repo.insert_tomo(349)
    f3 = repo.insert_fallo(otro_tomo, "E c/ F", cita="349:1")
    repo.insert_chunks(f1, [(None, 0, "chunk f1", None)])
    repo.insert_chunks(f2, [(None, 0, "chunk f2a", None), (None, 1, "chunk f2b", None)])
    repo.insert_chunks(f3, [(None, 0, "chunk de otro tomo", None)])

    chunks = repo.list_chunks_de_tomo(tomo_id)
    assert len(chunks) == 3
    assert {c.texto for c in chunks} == {"chunk f1", "chunk f2a", "chunk f2b"}


def test_list_chunks_de_tomo_sin_chunks_es_vacio(repo):
    tomo_id = repo.insert_tomo(348)
    assert repo.list_chunks_de_tomo(tomo_id) == []


# --- filtrar_chunks (PR-15: filtros de la búsqueda híbrida) ------------- #


def _fallo_con_metadatos(repo, *, fecha, tribunal_origen, secciones):
    """`secciones` es una lista de tipos; un chunk por sección, en orden."""
    numero = repo.conn.execute("SELECT count(*) FROM tomos").fetchone()[0] + 1
    tomo_id = repo.insert_tomo(numero)
    fallo_id = repo.insert_fallo(
        tomo_id,
        "A c/ B",
        cita=f"{numero}:1",
        fecha=fecha,
        tribunal_origen=tribunal_origen,
    )
    ids_chunks = []
    for i, tipo in enumerate(secciones):
        cur = repo.conn.execute(
            "INSERT INTO secciones (fallo_id, tipo, orden) VALUES (?, ?, ?)",
            (fallo_id, tipo, i),
        )
        seccion_id = cur.lastrowid
        repo.conn.commit()
        n = repo.insert_chunks(fallo_id, [(seccion_id, i, f"texto {tipo}", None)])
        assert n == 1
        ids_chunks.append(repo.list_chunks_de_fallo(fallo_id)[-1].id)
    return ids_chunks


def test_filtrar_chunks_sin_filtros_devuelve_todo(repo):
    ids = _fallo_con_metadatos(
        repo, fecha="2020-01-01", tribunal_origen="Cámara X", secciones=["mayoria"]
    )
    assert repo.filtrar_chunks(ids) == set(ids)


def test_filtrar_chunks_lista_vacia(repo):
    assert repo.filtrar_chunks([]) == set()


def test_filtrar_chunks_por_rango_de_anios(repo):
    v2018 = _fallo_con_metadatos(
        repo, fecha="2018-06-01", tribunal_origen=None, secciones=["mayoria"]
    )
    v2020 = _fallo_con_metadatos(
        repo, fecha="2020-06-01", tribunal_origen=None, secciones=["mayoria"]
    )
    v2022 = _fallo_con_metadatos(
        repo, fecha="2022-06-01", tribunal_origen=None, secciones=["mayoria"]
    )
    todos = v2018 + v2020 + v2022

    # un solo año: desde == hasta
    assert repo.filtrar_chunks(todos, anio_desde=2020, anio_hasta=2020) == set(v2020)
    # rango cerrado, inclusivo en las dos puntas
    assert repo.filtrar_chunks(todos, anio_desde=2018, anio_hasta=2020) == set(
        v2018 + v2020
    )
    # solo piso
    assert repo.filtrar_chunks(todos, anio_desde=2020) == set(v2020 + v2022)
    # solo techo
    assert repo.filtrar_chunks(todos, anio_hasta=2020) == set(v2018 + v2020)


def test_filtrar_chunks_por_anio_ignora_fallos_sin_fecha(repo):
    con_fecha = _fallo_con_metadatos(
        repo, fecha="2020-06-01", tribunal_origen=None, secciones=["mayoria"]
    )
    sin_fecha = _fallo_con_metadatos(
        repo, fecha=None, tribunal_origen=None, secciones=["mayoria"]
    )
    obtenido = repo.filtrar_chunks(
        con_fecha + sin_fecha, anio_desde=2019, anio_hasta=2021
    )
    assert obtenido == set(con_fecha)


def test_filtrar_chunks_por_tribunal(repo):
    a = _fallo_con_metadatos(
        repo, fecha=None, tribunal_origen="Cámara Federal", secciones=["mayoria"]
    )
    b = _fallo_con_metadatos(
        repo, fecha=None, tribunal_origen="Cámara Civil", secciones=["mayoria"]
    )
    assert repo.filtrar_chunks(a + b, tribunal_origen="Cámara Federal") == set(a)


def test_filtrar_chunks_por_tipo_seccion(repo):
    ids = _fallo_con_metadatos(
        repo, fecha=None, tribunal_origen=None, secciones=["mayoria", "disidencia"]
    )
    assert repo.filtrar_chunks(ids, tipo_seccion="disidencia") == {ids[1]}


def test_filtrar_chunks_combina_filtros(repo):
    a = _fallo_con_metadatos(
        repo,
        fecha="2020-01-01",
        tribunal_origen="Cámara X",
        secciones=["mayoria", "voto"],
    )
    b = _fallo_con_metadatos(
        repo,
        fecha="2020-01-01",
        tribunal_origen="Cámara Y",
        secciones=["mayoria", "voto"],
    )
    esperado = {a[1]}
    obtenido = repo.filtrar_chunks(
        a + b,
        anio_desde=2020,
        anio_hasta=2020,
        tribunal_origen="Cámara X",
        tipo_seccion="voto",
    )
    assert obtenido == esperado


def test_filtrar_chunks_sin_seccion_no_matchea_filtro_de_tipo(repo):
    fallo_id = _fallo_con_chunks(repo, 1)  # seccion_id NULL
    chunk_id = repo.list_chunks_de_fallo(fallo_id)[0].id
    assert repo.filtrar_chunks([chunk_id], tipo_seccion="mayoria") == set()


# --- citas (PR-C1: persistir las citas salientes y leer las entrantes) - #


def test_insert_y_listar_citas_de_fallo(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:100")
    n = repo.insert_citas(
        fid,
        [(311, 2478, "cf. Fallos: 311:2478 ..."), (340, 1084, "... Fallos: 340:1084")],
    )
    assert n == 2
    citas = repo.list_citas_de_fallo(fid)
    assert [(c.tomo_citado, c.pagina_citada) for c in citas] == [
        (311, 2478),
        (340, 1084),
    ]
    assert citas[0].contexto.startswith("cf. Fallos")
    assert repo.contar_citas_de_tomo(tomo_id) == 2


def test_borrar_citas_de_fallo_es_idempotente(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:100")
    repo.insert_citas(fid, [(311, 2478, "x")])
    assert repo.borrar_citas_de_fallo(fid) == 1
    assert repo.list_citas_de_fallo(fid) == []
    assert repo.borrar_citas_de_fallo(fid) == 0  # nada que borrar, sin error


def test_borrar_fallos_arrastra_las_citas(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:100")
    repo.insert_citas(fid, [(311, 2478, "x"), (340, 1084, "y")])
    assert repo.borrar_fallos(tomo_id) == 1
    assert repo.contar_citas_de_tomo(tomo_id) == 0  # cascada de la FK


def test_citas_entrantes_encuentra_quien_cita_dentro_del_corpus(repo):
    tomo_id = repo.insert_tomo(348)
    citado = repo.insert_fallo(
        tomo_id, "Citado c/ Estado", cita="348:100", pagina_inicio=100, pagina_fin=110
    )
    citante = repo.insert_fallo(
        tomo_id, "Citante c/ Otro", cita="348:200", pagina_inicio=200, pagina_fin=205
    )
    # el citante apunta a una página del medio del citado (no a su inicio)
    repo.insert_citas(citante, [(348, 105, "... conf. Fallos: 348:105 ...")])

    entrantes = repo.citas_entrantes(citado)
    assert len(entrantes) == 1
    assert entrantes[0].cita == "348:200"
    assert entrantes[0].caratula == "Citante c/ Otro"
    assert entrantes[0].pagina_citada == 105

    # y el citante no tiene entrantes
    assert repo.citas_entrantes(citante) == []


def test_citas_entrantes_excluye_la_auto_cita(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(
        tomo_id, "A c/ B", cita="348:100", pagina_inicio=100, pagina_fin=110
    )
    repo.insert_citas(fid, [(348, 100, "se remite a Fallos: 348:100")])
    assert repo.citas_entrantes(fid) == []


def test_citas_entrantes_ignora_otro_tomo(repo):
    t348 = repo.insert_tomo(348)
    t349 = repo.insert_tomo(349)
    citado = repo.insert_fallo(
        t348, "Citado", cita="348:100", pagina_inicio=100, pagina_fin=110
    )
    # un fallo del 349 que cita 349:105 (mismo número de página, otro tomo)
    otro = repo.insert_fallo(
        t349, "Otro", cita="349:200", pagina_inicio=200, pagina_fin=210
    )
    repo.insert_citas(otro, [(349, 105, "Fallos: 349:105")])
    assert repo.citas_entrantes(citado) == []


def test_citas_entrantes_sin_pagina_inicio_es_vacio(repo):
    tomo_id = repo.insert_tomo(348)
    fid = repo.insert_fallo(tomo_id, "A c/ B", cita="348:100")  # sin páginas
    assert repo.citas_entrantes(fid) == []


# --- sumarios / voces (PR-C2b) --------------------------------------------- #


def _fallo_para_sumarios(repo, numero=348, pagina=34):
    tomo_id = repo.insert_tomo(numero, estado="indexado")
    fallo_id = repo.insert_fallo(
        tomo_id,
        "A c/ B",
        cita=f"{numero}:{pagina}",
        pagina_inicio=pagina,
        pagina_fin=pagina + 3,
    )
    return tomo_id, fallo_id


def test_upsert_voz_dedup_y_backfill_de_codigo(repo):
    a = repo.upsert_voz("CONTRATO ADMINISTRATIVO")
    b = repo.upsert_voz("CONTRATO ADMINISTRATIVO", 1144)
    assert a == b
    fila = repo.conn.execute(
        "SELECT valor, codigo FROM voces WHERE id = ?", (a,)
    ).fetchone()
    assert fila["valor"] == "CONTRATO ADMINISTRATIVO"
    assert fila["codigo"] == 1144
    # un segundo upsert sin código no pisa el que ya está
    repo.upsert_voz("CONTRATO ADMINISTRATIVO")
    assert (
        repo.conn.execute("SELECT codigo FROM voces WHERE id = ?", (a,)).fetchone()[0]
        == 1144
    )
    assert repo.conn.execute("SELECT count(*) FROM voces").fetchone()[0] == 1


def test_reemplazar_sumarios_persiste_texto_voces_y_fallo_voces(repo):
    _tomo_id, fallo_id = _fallo_para_sumarios(repo)
    n = repo.reemplazar_sumarios_de_fallo(
        fallo_id,
        [
            (0, "Regla A", ["DEPOSITO PREVIO", "INTERESES"], "ADMIN", "8059511"),
            (1, "Regla B", ["INTERESES"], "ADMIN", None),
        ],
    )
    assert n == 2
    sumarios = repo.list_sumarios_de_fallo(fallo_id)
    assert [s.texto for s in sumarios] == ["Regla A", "Regla B"]
    assert sumarios[0].voces == ("DEPOSITO PREVIO", "INTERESES")
    assert sumarios[0].materia == "ADMIN"
    assert sumarios[0].id_documento == "8059511"
    # fallo_voces: una fila por voz distinta del fallo (INTERESES no se duplica)
    filas = repo.conn.execute(
        "SELECT count(*) FROM fallo_voces WHERE fallo_id = ?", (fallo_id,)
    ).fetchone()[0]
    assert filas == 2


def test_reemplazar_sumarios_es_idempotente(repo):
    _tomo_id, fallo_id = _fallo_para_sumarios(repo)
    repo.reemplazar_sumarios_de_fallo(fallo_id, [(0, "v1", ["A", "B"], None, None)])
    repo.reemplazar_sumarios_de_fallo(fallo_id, [(0, "v2", ["B", "C"], None, None)])
    sumarios = repo.list_sumarios_de_fallo(fallo_id)
    assert [s.texto for s in sumarios] == ["v2"]
    voces = repo.conn.execute(
        "SELECT v.valor FROM fallo_voces fv JOIN voces v ON v.id = fv.voz_id"
        " WHERE fv.fallo_id = ? ORDER BY v.valor",
        (fallo_id,),
    ).fetchall()
    assert [r[0] for r in voces] == ["B", "C"]
    # "A" quedó en `voces` (no se borra el catálogo) pero sin fallo que la use
    assert (
        repo.conn.execute("SELECT count(*) FROM voces WHERE valor = 'A'").fetchone()[0]
        == 1
    )


def test_borrar_fallo_arrastra_sumarios_y_fallo_voces(repo):
    _tomo_id, fallo_id = _fallo_para_sumarios(repo)
    repo.reemplazar_sumarios_de_fallo(fallo_id, [(0, "x", ["A"], None, None)])
    repo.conn.execute("DELETE FROM fallos WHERE id = ?", (fallo_id,))
    repo.conn.commit()
    assert repo.conn.execute("SELECT count(*) FROM sumarios").fetchone()[0] == 0
    assert repo.conn.execute("SELECT count(*) FROM fallo_voces").fetchone()[0] == 0


def test_buscar_voces_locales_por_substring_case_insensitive(repo):
    _tomo_id, fallo_id = _fallo_para_sumarios(repo)
    repo.reemplazar_sumarios_de_fallo(
        fallo_id,
        [(0, "x", ["CONTRATO ADMINISTRATIVO", "CONTRATO DE TRABAJO"], None, None)],
    )
    valores = [v for v, _ in repo.buscar_voces_locales("contrato")]
    assert valores == ["CONTRATO ADMINISTRATIVO", "CONTRATO DE TRABAJO"]
    assert repo.buscar_voces_locales("zzz") == []


def test_materias_del_corpus_distintas_y_ordenadas(repo):
    _t1, f1 = _fallo_para_sumarios(repo, numero=348, pagina=10)
    _t2, f2 = _fallo_para_sumarios(repo, numero=349, pagina=20)
    repo.reemplazar_sumarios_de_fallo(f1, [(0, "x", [], "PENAL", None)])
    repo.reemplazar_sumarios_de_fallo(
        f2, [(0, "y", [], "ADMIN", None), (1, "z", [], "PENAL", None)]
    )
    assert repo.materias_del_corpus() == ["ADMIN", "PENAL"]


def test_filtrar_chunks_por_voz_y_por_materia(repo):
    tomo_id = repo.insert_tomo(348, estado="indexado")
    ids = []
    for i, (voz, materia) in enumerate(
        [("DEPOSITO PREVIO", "ADMIN"), ("OTRA VOZ", "PENAL")]
    ):
        fallo_id = repo.insert_fallo(
            tomo_id, "A c/ B", cita=f"348:{i + 1}", pagina_inicio=i + 1
        )
        cur = repo.conn.execute(
            "INSERT INTO secciones (fallo_id, tipo, orden) VALUES (?, 'mayoria', 0)",
            (fallo_id,),
        )
        repo.conn.commit()
        repo.insert_chunks(fallo_id, [(cur.lastrowid, 0, f"texto {i}", None)])
        repo.reemplazar_sumarios_de_fallo(fallo_id, [(0, "s", [voz], materia, None)])
        ids.append(repo.list_chunks_de_fallo(fallo_id)[0].id)

    assert repo.filtrar_chunks(ids, voz="deposito previo") == {ids[0]}
    assert repo.filtrar_chunks(ids, voz="DEPOSITO PREVIO") == {ids[0]}
    assert repo.filtrar_chunks(ids, materia="PENAL") == {ids[1]}
    assert repo.filtrar_chunks(ids, voz="OTRA VOZ", materia="ADMIN") == set()
    assert repo.filtrar_chunks(ids, voz="no existe") == set()


def test_contar_sumarios_de_tomo(repo):
    tomo_id, fallo_id = _fallo_para_sumarios(repo)
    assert repo.contar_sumarios_de_tomo(tomo_id) == 0
    repo.reemplazar_sumarios_de_fallo(
        fallo_id, [(0, "a", [], None, None), (1, "b", [], None, None)]
    )
    assert repo.contar_sumarios_de_tomo(tomo_id) == 2


# --- auto_commit=False (PR-19: uso dentro de un handler del job runner) - #


def test_auto_commit_false_no_commitea_las_escrituras(conn):
    migrate(conn)
    repo = Repo(conn, auto_commit=False)
    repo.insert_tomo(348)

    # otra conexión al mismo archivo no ve nada: nadie commiteó todavía.
    otra = connect(conn.execute("PRAGMA database_list").fetchone()["file"])
    try:
        assert otra.execute("SELECT count(*) FROM tomos").fetchone()[0] == 0
    finally:
        otra.close()

    conn.commit()  # lo que sí commitea, acá, es quien orquesta (el Runner)
    otra = connect(conn.execute("PRAGMA database_list").fetchone()["file"])
    try:
        assert otra.execute("SELECT count(*) FROM tomos").fetchone()[0] == 1
    finally:
        otra.close()


def test_auto_commit_false_se_puede_revertir_con_rollback(conn):
    migrate(conn)
    repo = Repo(conn, auto_commit=False)
    tomo_id = repo.insert_tomo(348)
    repo.insert_pagina(tomo_id, 1, texto_crudo="x")
    conn.rollback()
    assert repo.get_tomo(tomo_id) is None  # todo lo pendiente se descartó


def test_auto_commit_true_por_default(conn):
    migrate(conn)
    repo = Repo(conn)  # sin auto_commit: el modo cómodo de siempre
    assert repo.auto_commit is True
    repo.insert_tomo(348)

    otra = connect(conn.execute("PRAGMA database_list").fetchone()["file"])
    try:
        assert otra.execute("SELECT count(*) FROM tomos").fetchone()[0] == 1
    finally:
        otra.close()


# --- conexión ------------------------------------------------------------ #


def test_connect_activa_foreign_keys_y_wal(tmp_path):
    c = connect(tmp_path / "x.db")
    try:
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        c.close()


def test_connect_crea_la_carpeta_contenedora(tmp_path):
    destino = tmp_path / "no" / "existe" / "todavia" / "spectre.db"
    c = connect(destino)
    try:
        assert destino.parent.is_dir()
    finally:
        c.close()
