"""PR-A6 — set de evaluación de la búsqueda.

20 consultas con el fallo esperado en `tests/fixtures/eval-busqueda.jsonl`,
más las métricas *recall@10* y *MRR* medidas sobre el índice real
(`data/spectre.db` + `data/vectors/`, los tomos que estén cargados). El
número de partida y el método están en `docs/qa/eval-busqueda.md`.

Es la vara para dos cosas del plan v2:
- ver si PR-A1 (agrupar por fallo) o cualquier cambio de ranking lo rompió;
- ver si el reranker de PR-C3 mejora algo (correr esto antes y después).

`slow` + `skipif`: necesita el índice real (no versionado) y el extra
`[embed]`. `pytest -m slow tests/test_eval_busqueda.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[1]
_DB = _RAIZ / "data" / "spectre.db"
_VECTORES = _RAIZ / "data" / "vectors"
_FIXTURE = Path(__file__).parent / "fixtures" / "eval-busqueda.jsonl"

# Piso de regresión, un poco por debajo de la línea de base documentada
# (recall@10 0,90 · MRR 0,71 sobre tomos 348+349). Si esto no da, algo del
# ranking empeoró — se investiga, no se baja el piso sin anotarlo.
_RECALL_MINIMO = 0.85
_MRR_MINIMO = 0.65


def _casos() -> list[dict]:
    return [
        json.loads(linea)
        for linea in _FIXTURE.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]


def test_fixture_tiene_20_casos_bien_formados():
    """Esto sí corre siempre: el fixture es parte del repo."""
    casos = _casos()
    assert len(casos) == 20
    for c in casos:
        assert set(c) >= {"consulta", "cita_esperada"}
        assert c["consulta"].strip()
        assert ":" in c["cita_esperada"]  # forma "tomo:pagina"
    # sin consultas duplicadas
    assert len({c["consulta"] for c in casos}) == 20


@pytest.mark.slow
def test_recall_y_mrr_sobre_el_indice_real():
    pytest.importorskip("sentence_transformers", reason="falta el extra [embed]")
    if not _DB.is_file() or not _VECTORES.is_dir():
        pytest.skip("falta el índice real (data/spectre.db + data/vectors/)")

    from spectre.db import Repo, connect
    from spectre.embed import cargar_modelo
    from spectre.index import IndiceVectorial
    from spectre.search import agrupar_por_fallo, buscar_hibrido

    conn = connect(_DB)
    repo = Repo(conn)
    idx = IndiceVectorial(_VECTORES)
    modelo = cargar_modelo()

    casos = _casos()
    aciertos = 0
    suma_rr = 0.0
    detalle = []
    for c in casos:
        vector = modelo.embed_uno(c["consulta"])
        fusionados = buscar_hibrido(
            conn, idx, c["consulta"], vector, k=60, candidatos=60
        )
        citas = [
            repo.get_fallo(g.fallo_id).cita
            for g in agrupar_por_fallo(conn, fusionados, limite=10)
        ]
        rango = (
            citas.index(c["cita_esperada"]) + 1 if c["cita_esperada"] in citas else 0
        )
        if rango:
            aciertos += 1
            suma_rr += 1 / rango
        detalle.append((c["consulta"], c["cita_esperada"], rango))

    conn.close()

    n = len(casos)
    recall = aciertos / n
    mrr = suma_rr / n
    reporte = "\n".join(
        f"  r{rango or '-':<2} {cita:9} {consulta}" for consulta, cita, rango in detalle
    )
    assert recall >= _RECALL_MINIMO, (
        f"recall@10 = {recall:.3f} (< {_RECALL_MINIMO}); revisar ranking\n{reporte}"
    )
    assert mrr >= _MRR_MINIMO, (
        f"MRR = {mrr:.4f} (< {_MRR_MINIMO}); revisar ranking\n{reporte}"
    )
