"""PR-C2b — `spectre.sumarios.sincronizar_tomo`: bajar los sumarios oficiales
de un tomo ya segmentado y persistirlos.

El transporte HTTP se reemplaza por un doble en memoria (`_FakeTransporte`):
mapea `(tomo, pagina)` a una lista de objetos crudos como los que devuelve
`paginarSumarios`. La orquestación —iterar los fallos del tomo, reusar una
sesión, reemplazar en vez de acumular— es lo que se prueba acá; el parseo y el
bucle de paginación ya los cubre `test_sumarios.py`.
"""

from __future__ import annotations

import pytest

from spectre.db import Repo, connect, migrate
from spectre.sumarios import sincronizar_fallo, sincronizar_tomo


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "spectre.db")
    migrate(conn)
    yield Repo(conn)
    conn.close()


class _FakeTransporte:
    """Doble de `corpus.csjn.sumarios.TransporteHTTP`. `por_pagina` es
    `{(tomo, pagina): [obj, ...]}`."""

    def __init__(self, por_pagina):
        self._por_pagina = por_pagina
        self._actual: list[dict] = []
        self.sesiones = 0

    def abrir_sesion(self):
        # idempotente, como el TransporteHTTP real
        if not getattr(self, "_abierta", False):
            self._abierta = True
            self.sesiones += 1

    def buscar(self, tomo, pagina):
        self._actual = list(self._por_pagina.get((tomo, pagina), []))
        return len(self._actual)

    def paginar(self, start_index):
        return self._actual[start_index : start_index + 10]


def _obj(texto, voces, *, materia=None, id_doc=None):
    o = {"texto": texto, "voces": " - ".join(voces)}
    if materia is not None:
        o["analisisDocumental"] = {"materiaSecretaria": materia}
    if id_doc is not None:
        o["linkDocumento"] = f"/x?idDocumento={id_doc}&cache=1"
    return o


def _tomo_con_fallos(repo, numero, paginas):
    tomo_id = repo.insert_tomo(numero, estado="indexado")
    for pagina in paginas:
        repo.insert_fallo(
            tomo_id,
            f"Caso en {numero}:{pagina}",
            cita=f"{numero}:{pagina}",
            pagina_inicio=pagina,
            pagina_fin=pagina + 3,
        )
    return tomo_id


def test_sincronizar_tomo_persiste_sumarios_y_voces(repo):
    tomo_id = _tomo_con_fallos(repo, 348, [34, 36])
    tr = _FakeTransporte(
        {
            (348, 34): [
                _obj("Regla A", ["DEPOSITO PREVIO", "INTERESES"], materia="ADMIN")
            ],
            (348, 36): [
                _obj("Regla B", ["INTERESES"], materia="ADMIN"),
                _obj("Regla C", ["COMPETENCIA"], materia="PROCESAL"),
            ],
        }
    )

    resumen = sincronizar_tomo(repo.conn, 348, transporte=tr, pausa=0)

    assert resumen.fallos_consultados == 2
    assert resumen.fallos_con_sumario == 2
    assert resumen.sumarios_totales == 3
    # DEPOSITO PREVIO, INTERESES, COMPETENCIA
    assert resumen.voces_distintas == 3

    f34 = repo.get_fallo_por_cita("348:34")
    sumarios = repo.list_sumarios_de_fallo(f34.id)
    assert [s.texto for s in sumarios] == ["Regla A"]
    assert sumarios[0].voces == ("DEPOSITO PREVIO", "INTERESES")
    assert sumarios[0].materia == "ADMIN"

    assert repo.contar_sumarios_de_tomo(tomo_id) == 3
    assert sorted(repo.materias_del_corpus()) == ["ADMIN", "PROCESAL"]
    # una voz compartida entre dos fallos es una sola fila en `voces`
    assert repo.conn.execute("SELECT count(*) FROM voces").fetchone()[0] == 3


def test_sincronizar_tomo_reusa_una_sola_sesion(repo):
    _tomo_con_fallos(repo, 348, [10, 20, 30])
    tr = _FakeTransporte({(348, 10): [_obj("x", ["V"])]})
    sincronizar_tomo(repo.conn, 348, transporte=tr, pausa=0)
    # una sesión, no una por fallo (el flujo de la CSJN es stateful por cookies)
    assert tr.sesiones == 1


def test_sincronizar_tomo_es_reejecutable_sin_acumular(repo):
    _tomo_con_fallos(repo, 348, [34])
    tr1 = _FakeTransporte({(348, 34): [_obj("v1", ["A", "B"])]})
    sincronizar_tomo(repo.conn, 348, transporte=tr1, pausa=0)

    tr2 = _FakeTransporte({(348, 34): [_obj("v2", ["B", "C"])]})
    sincronizar_tomo(repo.conn, 348, transporte=tr2, pausa=0)

    f = repo.get_fallo_por_cita("348:34")
    sumarios = repo.list_sumarios_de_fallo(f.id)
    assert [s.texto for s in sumarios] == ["v2"]  # reemplazado, no dos filas
    # fallo_voces quedó con las de la 2ª corrida
    filas = repo.conn.execute(
        "SELECT v.valor FROM fallo_voces fv JOIN voces v ON v.id = fv.voz_id"
        " WHERE fv.fallo_id = ? ORDER BY v.valor",
        (f.id,),
    ).fetchall()
    assert [r[0] for r in filas] == ["B", "C"]


def test_sincronizar_tomo_fallo_sin_sumario_no_rompe(repo):
    _tomo_con_fallos(repo, 348, [100, 145])
    tr = _FakeTransporte({(348, 100): [_obj("hay", ["X"])]})  # 145 no está
    resumen = sincronizar_tomo(repo.conn, 348, transporte=tr, pausa=0)
    assert resumen.fallos_con_sumario == 1
    assert repo.list_sumarios_de_fallo(repo.get_fallo_por_cita("348:145").id) == []


def test_sincronizar_tomo_inexistente_revienta(repo):
    with pytest.raises(ValueError, match="no existe el tomo"):
        sincronizar_tomo(repo.conn, 999, transporte=_FakeTransporte({}), pausa=0)


def test_sincronizar_fallo_suelto(repo):
    _tomo_con_fallos(repo, 348, [34])
    fallo = repo.get_fallo_por_cita("348:34")
    tr = _FakeTransporte({(348, 34): [_obj("uno", ["A"]), _obj("dos", ["A", "B"])]})
    n = sincronizar_fallo(repo.conn, fallo.id, transporte=tr)
    assert n == 2
    assert len(repo.list_sumarios_de_fallo(fallo.id)) == 2


@pytest.mark.red
def test_sincronizar_fallo_real_348_36(repo):
    """Contra el sitio real: 348:36 (Municipalidad de Villa Gesell) tiene
    varios sumarios. La base es mínima (un tomo, un fallo)."""
    tomo_id = repo.insert_tomo(348, estado="indexado")
    fallo_id = repo.insert_fallo(
        tomo_id, "Villa Gesell", cita="348:36", pagina_inicio=36, pagina_fin=45
    )
    n = sincronizar_fallo(repo.conn, fallo_id)
    assert n >= 2
    sumarios = repo.list_sumarios_de_fallo(fallo_id)
    assert all(s.texto for s in sumarios)
    assert any(s.voces for s in sumarios)
