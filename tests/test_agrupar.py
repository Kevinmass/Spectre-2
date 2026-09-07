"""PR-A1 — `search.agrupar_por_fallo`: colapsar la lista de chunks ranqueados
a una lista de fallos con sus pasajes.

No necesita índices: `agrupar_por_fallo` toma una `Sequence[ResultadoHibrido]`
ya ordenada (mejor primero) más la conexión, y resuelve fallo/sección contra
`db/repo.py`. Los `ResultadoHibrido` se arman a mano.
"""

from __future__ import annotations

import pytest

from spectre.db import Repo, connect, migrate
from spectre.search import agrupar_por_fallo
from spectre.search.hybrid import ResultadoHibrido


@pytest.fixture
def repo(tmp_path):
    c = connect(tmp_path / "spectre.db")
    migrate(c)
    yield Repo(c)
    c.close()


def _seccion(repo, fallo_id, tipo, *, autor=None, orden=0):
    cur = repo.conn.execute(
        "INSERT INTO secciones (fallo_id, tipo, autor, orden) VALUES (?, ?, ?, ?)",
        (fallo_id, tipo, autor, orden),
    )
    repo.conn.commit()
    return cur.lastrowid


def _fallo(repo, *, cita, **campos):
    numero = repo.conn.execute("SELECT count(*) FROM tomos").fetchone()[0] + 1
    tomo_id = repo.insert_tomo(numero)
    return repo.insert_fallo(tomo_id, "A c/ B", cita=cita, **campos)


def _chunks(repo, fallo_id, filas):
    """`filas`: lista de `(seccion_id, texto, pagina_oficial)`. Devuelve los
    chunk_id en orden."""
    repo.insert_chunks(
        fallo_id, [(sid, i, t, pag) for i, (sid, t, pag) in enumerate(filas)]
    )
    return [c.id for c in repo.list_chunks_de_fallo(fallo_id)]


def _res(*pares):
    """`pares`: `(chunk_id, score)`. Un `ResultadoHibrido` por cada uno, ya en
    orden (el llamador los pasa de mejor a peor, como hace `buscar_hibrido`)."""
    return [ResultadoHibrido(cid, score, None, None) for cid, score in pares]


def test_agrupa_los_chunks_de_un_fallo_en_un_resultado(repo):
    f = _fallo(repo, cita="1:1")
    sec = _seccion(repo, f, "mayoria")
    c0, c1, c2 = _chunks(
        repo, f, [(sec, "uno", 10), (sec, "dos", 11), (sec, "tres", 12)]
    )

    agrupados = agrupar_por_fallo(
        repo.conn, _res((c0, 0.9), (c1, 0.5), (c2, 0.3)), limite=10
    )

    assert len(agrupados) == 1
    g = agrupados[0]
    assert g.cita == "1:1"
    assert g.total_pasajes == 3
    assert len(g.pasajes) == 1  # un solo tipo de sección
    assert g.pasajes[0].chunk_id == c0  # el de más puntaje
    assert g.score == pytest.approx(0.9)


def test_conserva_el_mejor_pasaje_por_tipo_de_seccion(repo):
    f = _fallo(repo, cita="1:1")
    may = _seccion(repo, f, "mayoria", orden=0)
    dis = _seccion(repo, f, "disidencia", autor="Rosenkrantz", orden=1)
    cm0, cm1, cd0 = _chunks(
        repo, f, [(may, "may fuerte", 1), (may, "may floja", 2), (dis, "disidencia", 3)]
    )

    # orden de llegada: may fuerte, disidencia, may floja
    agrupados = agrupar_por_fallo(
        repo.conn, _res((cm0, 0.9), (cd0, 0.7), (cm1, 0.4)), limite=10
    )

    (g,) = agrupados
    assert g.total_pasajes == 3
    assert [p.seccion_tipo for p in g.pasajes] == ["mayoria", "disidencia"]
    # el 2º chunk de mayoría ("may floja") se descartó: uno por tipo
    assert [p.chunk_id for p in g.pasajes] == [cm0, cd0]
    assert g.pasajes[1].seccion_autor == "Rosenkrantz"


def test_pasajes_ordenados_por_puntaje_aunque_lleguen_al_reves(repo):
    f = _fallo(repo, cita="1:1")
    may = _seccion(repo, f, "mayoria", orden=0)
    dis = _seccion(repo, f, "disidencia", orden=1)
    cm, cd = _chunks(repo, f, [(may, "mayoria", 1), (dis, "disidencia", 2)])

    # llega primero la disidencia (mejor puntaje), después la mayoría
    (g,) = agrupar_por_fallo(repo.conn, _res((cd, 0.8), (cm, 0.6)), limite=10)
    assert [p.seccion_tipo for p in g.pasajes] == ["disidencia", "mayoria"]
    assert g.score == pytest.approx(0.8)


def test_orden_de_los_fallos_sigue_al_primer_chunk_de_cada_uno(repo):
    fa = _fallo(repo, cita="1:1")
    fb = _fallo(repo, cita="1:2")
    (ca,) = _chunks(repo, fa, [(None, "alfa", 1)])
    (cb,) = _chunks(repo, fb, [(None, "beta", 1)])

    # B aparece antes que A en la lista fusionada
    agrupados = agrupar_por_fallo(repo.conn, _res((cb, 0.9), (ca, 0.8)), limite=10)
    assert [g.cita for g in agrupados] == ["1:2", "1:1"]


def test_limite_recorta_la_cantidad_de_fallos_no_de_pasajes(repo):
    ids = []
    for n in range(4):
        f = _fallo(repo, cita=f"1:{n}")
        (c,) = _chunks(repo, f, [(None, f"texto {n}", 1)])
        ids.append(c)

    agrupados = agrupar_por_fallo(
        repo.conn, _res(*[(c, 1.0 - i * 0.1) for i, c in enumerate(ids)]), limite=2
    )
    assert [g.cita for g in agrupados] == ["1:0", "1:1"]


def test_chunk_sin_seccion_es_un_pasaje_con_tipo_none(repo):
    f = _fallo(repo, cita="1:1")
    (c,) = _chunks(repo, f, [(None, "sin sección", 5)])

    (g,) = agrupar_por_fallo(repo.conn, _res((c, 0.5)), limite=10)
    assert g.pasajes[0].seccion_tipo is None
    assert g.pasajes[0].seccion_autor is None
    assert g.pasajes[0].pagina_oficial == 5


def test_chunk_inexistente_se_saltea(repo):
    f = _fallo(repo, cita="1:1")
    (c,) = _chunks(repo, f, [(None, "existe", 1)])

    agrupados = agrupar_por_fallo(repo.conn, _res((999999, 0.9), (c, 0.5)), limite=10)
    assert [g.cita for g in agrupados] == ["1:1"]
    assert agrupados[0].total_pasajes == 1


def test_lista_vacia_da_lista_vacia(repo):
    assert agrupar_por_fallo(repo.conn, [], limite=10) == []
