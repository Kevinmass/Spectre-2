"""PR-C5 — `spectre.partes.reclasificar_partes`: backfill de la clasificación
de partes sobre el corpus ya indexado, a partir de `fallos.caratula`.
"""

from __future__ import annotations

import pytest

from spectre.db import Repo, connect, migrate
from spectre.partes import reclasificar_partes


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "spectre.db")
    migrate(conn)
    yield Repo(conn)
    conn.close()


def _fallo(repo, tomo_id, cita, caratula):
    return repo.insert_fallo(
        tomo_id, caratula, cita=cita, pagina_inicio=int(cita.split(":")[1])
    )


def test_reclasificar_llena_actor_demandado_y_tipo(repo):
    tomo_id = repo.insert_tomo(348, estado="indexado")
    f1 = _fallo(repo, tomo_id, "348:1", "Pérez, Juan c/ Estado Nacional s/ daños")
    f2 = _fallo(repo, tomo_id, "348:2", "Telecom Argentina S.A. c/ AFIP s/ repetición")

    resumen = reclasificar_partes(repo.conn)
    assert resumen.fallos == 2
    assert resumen.con_actor_tipo == 2
    assert resumen.con_demandado_tipo == 2

    a1 = repo.get_fallo(f1)
    assert a1.actor == "Pérez, Juan"
    assert a1.actor_tipo == "persona_fisica"
    assert a1.demandado == "Estado Nacional"
    assert a1.demandado_tipo == "estado"

    a2 = repo.get_fallo(f2)
    assert a2.actor_tipo == "empresa"
    assert a2.demandado_tipo == "estado"

    assert resumen.por_tipo == {"persona_fisica": 1, "empresa": 1, "estado": 2}


def test_reclasificar_es_reejecutable(repo):
    tomo_id = repo.insert_tomo(348, estado="indexado")
    _fallo(repo, tomo_id, "348:1", "González, Ana c/ Provincia de Córdoba")
    reclasificar_partes(repo.conn)
    r2 = reclasificar_partes(repo.conn)
    assert r2.fallos == 1
    f = repo.get_fallo_por_cita("348:1")
    assert (f.actor_tipo, f.demandado_tipo) == ("persona_fisica", "estado")


def test_reclasificar_acota_por_tomo(repo):
    t1 = repo.insert_tomo(348, estado="indexado")
    t2 = repo.insert_tomo(349, estado="indexado")
    _fallo(repo, t1, "348:1", "Empresa X S.R.L. c/ Fisco Nacional")
    _fallo(repo, t2, "349:1", "Y S.A. c/ Z")

    resumen = reclasificar_partes(repo.conn, tomo=348)
    assert resumen.fallos == 1
    assert repo.get_fallo_por_cita("348:1").actor_tipo == "empresa"
    # el del tomo 349 no se tocó
    assert repo.get_fallo_por_cita("349:1").actor_tipo is None


def test_reclasificar_tomo_inexistente_revienta(repo):
    with pytest.raises(ValueError, match="no existe el tomo"):
        reclasificar_partes(repo.conn, tomo=999)


def test_reclasificar_carratula_sin_clasificar_deja_none(repo):
    tomo_id = repo.insert_tomo(348, estado="indexado")
    _fallo(repo, tomo_id, "348:1", "Asociación Civil X c/ Fundación Y")
    resumen = reclasificar_partes(repo.conn)
    f = repo.get_fallo_por_cita("348:1")
    assert f.actor == "Asociación Civil X"  # el string crudo sí se guarda
    assert f.actor_tipo is None
    assert resumen.con_actor_tipo == 0
