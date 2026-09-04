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


MIGRACIONES = ["0001_initial", "0002_jobs_estado_check", "0003_chunks_fts"]


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
