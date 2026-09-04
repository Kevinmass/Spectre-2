"""PR-14 — índice léxico FTS5 sobre `chunks.texto` (D-6 del plan).

Criterio de aceptación (plan §6): buscar "artículo 14 de la ley 48" devuelve
los fallos correctos.

`test_los_chunks_insertados_...` a `test_reconstruir_...` prueban la mecánica
(tabla virtual + triggers de la migración `0003_chunks_fts`) sobre chunks
insertados a mano, sin PDF. `test_pipeline_sobre_fixture` corre
chunker -> repo -> FTS5 sobre un recorte real del Tomo 348. `test_aceptacion`
es la medición sobre el Tomo 348 completo (`slow`, necesita
`data/tomos/348.pdf`): confirmado aparte con `spectre.corpus.pdf` que la frase
aparece 48 veces en el tomo (páginas oficiales 1, 15, 43-48, 96-97, entre
otras), así que buscarla tiene que devolver resultados reales, no vacíos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spectre.chunking import fragmentar_fallo
from spectre.corpus.fallo import (
    parsear_indice,
    partir_secciones,
    segmentar,
    texto_del_fallo_paginado,
)
from spectre.corpus.pdf import extraer_texto
from spectre.db import Repo, connect, migrate
from spectre.index.lexical import IndiceLexico

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "spectre.db")
    migrate(conn)
    r = Repo(conn)
    yield r
    conn.close()


def _insertar(repo: Repo, textos: list[str], *, cita: str = "1:1") -> int:
    tomo_id = repo.insert_tomo(1)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita=cita)
    repo.insert_chunks(fallo_id, [(None, i, t, None) for i, t in enumerate(textos)])
    return fallo_id


# --- la mecánica del índice: tabla virtual + triggers ------------------ #


def test_los_chunks_insertados_quedan_buscables(repo):
    _insertar(repo, ["el gato come pescado", "perro ladra fuerte"])
    idx = IndiceLexico(repo.conn)
    assert idx.contar() == 2
    resultados = idx.buscar("pescado")
    assert [r.chunk_id for r in resultados] == [1]


def test_orden_por_relevancia(repo):
    _insertar(repo, ["perro gato", "perro perro perro gato"])
    resultados = [r.chunk_id for r in IndiceLexico(repo.conn).buscar("perro")]
    # el chunk con más menciones de "perro" rankea primero (bm25 de FTS5)
    assert resultados[0] == 2


def test_k_limita_resultados(repo):
    _insertar(repo, [f"perro numero {i}" for i in range(5)])
    assert len(IndiceLexico(repo.conn).buscar("perro", k=2)) == 2


def test_consulta_sin_terminos_reconocibles_revienta(repo):
    with pytest.raises(ValueError):
        IndiceLexico(repo.conn).buscar("   ")


def test_diacriticos_no_importan(repo):
    _insertar(repo, ["el artículo 14 de la ley 48"])
    idx = IndiceLexico(repo.conn)
    assert idx.buscar("articulo 14 de la ley 48") != []
    assert idx.buscar("artículo 14 de la ley 48") != []


def test_caracteres_de_sintaxis_fts5_no_rompen_la_consulta(repo):
    _insertar(repo, ['texto con "comillas" y guion-medio'])
    idx = IndiceLexico(repo.conn)
    # ninguna de estas consultas debería levantar sqlite3.OperationalError,
    # aunque el usuario tipee sintaxis de FTS5 sin querer
    for consulta in ['"comillas"', "guion-medio", "texto (con) *raros*", "col:on"]:
        idx.buscar(consulta)


def test_busqueda_no_matchea_devuelve_lista_vacia(repo):
    _insertar(repo, ["texto sin relación"])
    assert IndiceLexico(repo.conn).buscar("inexistente") == []


def test_borrar_fallo_arrastra_el_chunk_del_indice(repo):
    fallo_id = _insertar(repo, ["texto único aquí"])
    idx = IndiceLexico(repo.conn)
    assert idx.contar() == 1
    repo.conn.execute("DELETE FROM fallos WHERE id = ?", (fallo_id,))
    repo.conn.commit()
    assert idx.contar() == 0
    assert idx.buscar("único") == []


def test_reconstruir_repuebla_el_indice_desincronizado(repo):
    # simula una escritura que saltea los triggers (p. ej. una carga masiva
    # con executescript que los deshabilite a propósito): dropearlos a mano
    # antes de insertar dejar el chunk fuera del índice.
    repo.conn.execute("DROP TRIGGER chunks_fts_ai")
    _insertar(repo, ["texto reconstruible"])
    idx = IndiceLexico(repo.conn)
    assert idx.contar() == 0  # el trigger que lo indexaría no corrió
    idx.reconstruir()
    assert idx.contar() == 1
    assert idx.buscar("reconstruible") != []


# --- integración: chunker -> repo -> FTS5, sobre un recorte real -------- #


def _chunks_del_fixture(pdf: Path):
    paginas = extraer_texto(pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(None, paginas, tomo_numero=348)
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin,
        )
        texto = "\n".join(t for _, t in paginado)
        secciones = partir_secciones(texto)
        chunks = fragmentar_fallo(
            secciones, paginado, cita=f.cita, pagina_inicio=f.pagina_inicio
        )
        yield f, chunks


def test_pipeline_sobre_fixture(repo):
    tomo_id = repo.insert_tomo(348)
    total = 0
    for f, chunks in _chunks_del_fixture(FIXTURE):
        fallo_id = repo.insert_fallo(tomo_id, f.caratula, cita=f.cita)
        n = repo.insert_chunks(
            fallo_id, [(None, c.orden, c.texto, c.pagina_oficial) for c in chunks]
        )
        total += n
    assert total > 3

    idx = IndiceLexico(repo.conn)
    assert idx.contar() == total
    # "Ricardo Luis Lorenzetti" firma el voto de 348:34 (ver bitácora PR-09)
    resultados = idx.buscar("Ricardo Luis Lorenzetti")
    assert resultados != []
    encontrado = repo.get_chunk(resultados[0].chunk_id)
    assert "Lorenzetti" in encontrado.texto


# --- aceptación: Tomo 348 completo --------------------------------------- #


@pytest.mark.slow
def test_aceptacion(tmp_path):
    if not TOMO_348.is_file():
        pytest.skip("falta data/tomos/348.pdf")

    conn = connect(tmp_path / "spectre.db")
    migrate(conn)
    repo = Repo(conn)

    paginas = extraer_texto(TOMO_348)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(parsear_indice(TOMO_348), paginas, tomo_numero=348)
    tomo_id = repo.insert_tomo(348)

    total = 0
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin,
        )
        texto = "\n".join(t for _, t in paginado)
        chunks = fragmentar_fallo(
            partir_secciones(texto),
            paginado,
            cita=f.cita,
            pagina_inicio=f.pagina_inicio,
        )
        fallo_id = repo.insert_fallo(tomo_id, f.caratula, cita=f.cita)
        total += repo.insert_chunks(
            fallo_id, [(None, c.orden, c.texto, c.pagina_oficial) for c in chunks]
        )

    idx = IndiceLexico(conn)
    assert idx.contar() == total  # ~1.100, ver plan PR-11

    # "artículo 14 de la ley 48" aparece 48 veces en el tomo (verificado aparte
    # con una regex sobre el texto limpio de las 968 páginas). La consulta es
    # un AND implícito de sus 6 términos (ver `_consulta_fts`): con "de"/"la"
    # tan comunes, no todo lo que matchea repite la frase textual — por eso el
    # criterio es que la frase literal esté *entre* los resultados, no que
    # todos la tengan (ese ranking más fino es RRF, PR-15).
    resultados = idx.buscar("artículo 14 de la ley 48", k=25)
    assert resultados != []
    textos = [
        " ".join(repo.get_chunk(r.chunk_id).texto.lower().split()) for r in resultados
    ]
    con_frase = [i for i, t in enumerate(textos) if "artículo 14 de la ley 48" in t]
    assert con_frase, "ningún resultado entre los primeros 25 repite la frase literal"

    conn.close()
