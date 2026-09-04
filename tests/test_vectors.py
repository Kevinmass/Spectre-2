"""PR-13 — índice vectorial sobre LanceDB.

Criterio de aceptación (plan §6): indexar el Tomo 348 completo y recuperar el
vecino más cercano de un chunk conocido.

`test_aceptacion` corre el pipeline entero (chunker -> embeddings reales ->
índice) sobre el Tomo 348: es `slow` y necesita `sentence-transformers`
(`[embed]`), así que se saltea si falta. `test_pipeline_con_embeddings_falsos`
verifica la misma cadena (chunker -> índice) con vectores deterministas de
juguete y corre siempre.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

pytest.importorskip("lancedb")

from spectre.chunking import fragmentar_fallo
from spectre.corpus.fallo import (
    partir_secciones,
    segmentar,
    texto_del_fallo_paginado,
)
from spectre.corpus.pdf import extraer_texto
from spectre.index import IndiceVectorial, Vecino

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"


def _vec_falso(texto: str, dim: int = 16) -> list[float]:
    """Un vector determinista y normalizado a partir del texto (sin modelo)."""
    h = hashlib.sha256(texto.encode()).digest()
    crudo = [((h[i % len(h)] * (i + 1)) % 255) - 127 for i in range(dim)]
    norma = math.sqrt(sum(x * x for x in crudo)) or 1.0
    return [x / norma for x in crudo]


# --- la mecánica del índice ---------------------------------------- #


def test_upsert_buscar_y_contar(tmp_path):
    idx = IndiceVectorial(tmp_path / "vec", dimension=3)
    idx.upsert(
        [
            (1, [1.0, 0.0, 0.0], "m"),
            (2, [0.0, 1.0, 0.0], "m"),
            (3, [0.9, 0.1, 0.0], "m"),
        ]
    )
    assert idx.contar() == 3
    vecinos = idx.buscar([1.0, 0.0, 0.0], k=2)
    assert [v.chunk_id for v in vecinos] == [1, 3]
    assert isinstance(vecinos[0], Vecino)
    assert vecinos[0].distancia == pytest.approx(0.0, abs=1e-5)


def test_buscar_indice_vacio_o_inexistente(tmp_path):
    assert IndiceVectorial(tmp_path / "nada", dimension=3).buscar([1, 0, 0]) == []


def test_upsert_es_idempotente_y_reanudable(tmp_path):
    idx = IndiceVectorial(tmp_path / "v", dimension=2)
    lote_a = [(i, [1.0, float(i)], "m") for i in range(5)]
    idx.upsert(lote_a)
    # se corta y se reanuda: se re-manda A y además B, solapados
    lote_b = [(i, [1.0, float(i)], "m") for i in range(3, 8)]
    idx.upsert(lote_a + lote_b)
    assert idx.contar() == 8
    assert idx.ids() == set(range(8))


def test_upsert_reemplaza_vector_y_modelo(tmp_path):
    idx = IndiceVectorial(tmp_path / "v", dimension=3)
    idx.upsert([(7, [1.0, 0.0, 0.0], "viejo")])
    idx.upsert([(7, [0.0, 0.0, 1.0], "nuevo")])
    assert idx.contar() == 1
    assert idx.modelos() == {"nuevo": 1}
    assert idx.buscar([0.0, 0.0, 1.0], k=1)[0].chunk_id == 7


def test_modelos_muestra_una_reindexacion_a_medias(tmp_path):
    idx = IndiceVectorial(tmp_path / "v", dimension=2)
    idx.upsert([(1, [1.0, 0.0], "a"), (2, [0.0, 1.0], "a"), (3, [1.0, 1.0], "b")])
    assert idx.modelos() == {"a": 2, "b": 1}


def test_dimension_incompatible_revienta(tmp_path):
    idx = IndiceVectorial(tmp_path / "v", dimension=3)
    with pytest.raises(ValueError):
        idx.upsert([(1, [1.0, 0.0], "m")])  # 2 != 3


def test_persistencia_entre_conexiones(tmp_path):
    ruta = tmp_path / "v"
    IndiceVectorial(ruta, dimension=4).upsert(
        [(1, [1, 0, 0, 0], "m"), (2, [0, 1, 0, 0], "m")]
    )

    otro = IndiceVectorial(ruta)  # sin pasar dimensión: la lee del esquema
    assert otro.contar() == 2
    assert otro.dimension == 4
    assert otro.buscar([1, 0, 0, 0], k=1)[0].chunk_id == 1


def test_reabrir_con_dimension_equivocada_revienta(tmp_path):
    ruta = tmp_path / "v"
    IndiceVectorial(ruta, dimension=4).upsert([(1, [1, 0, 0, 0], "m")])
    with pytest.raises(ValueError):
        IndiceVectorial(ruta, dimension=8).contar()


def test_vaciar_permite_rehacer_con_otra_dimension(tmp_path):
    ruta = tmp_path / "v"
    idx = IndiceVectorial(ruta, dimension=3)
    idx.upsert([(1, [1, 0, 0], "m")])
    idx.vaciar()
    assert idx.contar() == 0
    otro = IndiceVectorial(ruta, dimension=5)
    otro.upsert([(1, [1, 0, 0, 0, 0], "m")])
    assert otro.contar() == 1


# --- integración: chunker -> índice ------------------------------- #


def _chunks_del_fixture():
    paginas = extraer_texto(FIXTURE)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(None, paginas, tomo_numero=348)
    chunks = []
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
        chunks += fragmentar_fallo(
            secciones, paginado, cita=f.cita, pagina_inicio=f.pagina_inicio
        )
    return chunks


def test_pipeline_con_embeddings_falsos(tmp_path):
    chunks = _chunks_del_fixture()
    assert len(chunks) > 3
    idx = IndiceVectorial(tmp_path / "vec", dimension=16)
    idx.upsert((cid, _vec_falso(c.texto), "fake-1") for cid, c in enumerate(chunks))
    assert idx.contar() == len(chunks)

    # el vecino más cercano del vector de un chunk conocido es ese mismo chunk
    objetivo = 3
    vecinos = idx.buscar(_vec_falso(chunks[objetivo].texto), k=3)
    assert vecinos[0].chunk_id == objetivo
    assert vecinos[0].distancia == pytest.approx(0.0, abs=1e-5)


# --- aceptación: Tomo 348 con embeddings reales ------------------- #


@pytest.mark.slow
def test_aceptacion(tmp_path):
    pytest.importorskip("sentence_transformers", reason="falta [embed]")
    if not TOMO_348.is_file():
        pytest.skip("falta data/tomos/348.pdf")

    from spectre.embed import cargar_modelo

    modelo = cargar_modelo()
    try:
        dim = modelo.dimension
    except OSError as e:
        pytest.skip(f"no se pudo cargar el modelo: {e}")

    paginas = extraer_texto(TOMO_348)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    from spectre.corpus.fallo import parsear_indice

    r = segmentar(parsear_indice(TOMO_348), paginas, tomo_numero=348)

    todos = []
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin,
        )
        texto = "\n".join(t for _, t in paginado)
        todos += fragmentar_fallo(
            partir_secciones(texto),
            paginado,
            cita=f.cita,
            pagina_inicio=f.pagina_inicio,
        )

    idx = IndiceVectorial(tmp_path / "vec", dimension=dim)
    lote = 256
    for k in range(0, len(todos), lote):
        trozo = todos[k : k + lote]
        vectores = modelo.embed([c.texto for c in trozo])
        idx.upsert((k + j, v, modelo.nombre) for j, v in enumerate(vectores))

    assert idx.contar() == len(todos)  # ~1.100
    # el vecino más cercano del vector de un chunk conocido es ese chunk
    conocido = len(todos) // 2
    v = modelo.embed([todos[conocido].texto])[0]
    vecinos = idx.buscar(v, k=5)
    assert vecinos[0].chunk_id == conocido
    assert vecinos[0].distancia < 1e-3
