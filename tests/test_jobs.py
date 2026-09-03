"""PR-03 — cola de jobs durable y reanudable.

Criterio de aceptación (plan §6): matar el proceso a mitad de un job y
reanudarlo sin perder ni duplicar trabajo. Test que lo demuestre
(`test_proceso_muerto_a_mitad_reanuda_sin_perder_ni_duplicar`, con un
subproceso real al que se le manda SIGKILL / TerminateProcess).
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from spectre.db import ahora_iso, connect, migrate
from spectre.jobs import EN_PROCESO, FALLIDO, HECHO, PENDIENTE, Runner

WORKER = Path(__file__).parent / "_job_worker.py"


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "spectre.db")
    migrate(c)
    c.execute(
        "CREATE TABLE _efectos (id INTEGER PRIMARY KEY, job_id INTEGER, nota TEXT)"
    )
    c.commit()
    yield c
    c.close()


def _contar_efectos(conn) -> int:
    return conn.execute("SELECT count(*) FROM _efectos").fetchone()[0]


def _insertar_zombi(conn, *, intentos: int) -> int:
    """Un job dejado `en_proceso` por una caída anterior."""
    cur = conn.execute(
        "INSERT INTO jobs (tipo, payload, estado, intentos, iniciado_at, creado_at) "
        "VALUES ('lento', '{}', 'en_proceso', ?, ?, ?)",
        (intentos, ahora_iso(), ahora_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


# --- encolado --------------------------------------------------------- #


def test_encolar_crea_job_pendiente(conn):
    r = Runner(conn)
    jid = r.encolar("x", {"a": 1})
    job = r.get(jid)
    assert job.estado == PENDIENTE
    assert job.intentos == 0
    assert job.payload == {"a": 1}
    assert job.creado_at is not None
    assert job.iniciado_at is None
    assert job.terminado_at is None
    assert job.error is None


def test_encolar_sin_payload_es_dict_vacio(conn):
    r = Runner(conn)
    assert r.get(r.encolar("x")).payload == {}


# --- procesamiento feliz ------------------------------------------------ #


def test_procesa_en_orden_fifo(conn):
    r = Runner(conn)
    vistos: list[int] = []
    r.registrar("t", lambda c, j: vistos.append(j.payload["n"]))
    for n in (1, 2, 3):
        r.encolar("t", {"n": n})
    assert r.run() == 3
    assert vistos == [1, 2, 3]
    assert r.contar_por_estado() == {HECHO: 3}


def test_run_vacio_devuelve_cero(conn):
    assert Runner(conn).run() == 0


def test_run_no_reprocesa_lo_ya_hecho(conn):
    r = Runner(conn)
    corridas: list[int] = []
    r.registrar("t", lambda c, j: corridas.append(j.id))
    r.encolar("t")
    assert r.run() == 1
    assert r.run() == 0
    assert len(corridas) == 1


def test_efectos_del_handler_se_commitean(conn):
    r = Runner(conn)
    r.registrar(
        "t",
        lambda c, j: c.execute(
            "INSERT INTO _efectos (job_id, nota) VALUES (?, ?)", (j.id, "ok")
        ),
    )
    jid = r.encolar("t")
    r.run()
    filas = conn.execute("SELECT job_id, nota FROM _efectos").fetchall()
    assert [tuple(f) for f in filas] == [(jid, "ok")]
    assert r.get(jid).estado == HECHO


# --- fallos y reintentos --------------------------------------------- #


def test_tipo_sin_handler_queda_fallido_y_no_traba_la_cola(conn):
    r = Runner(conn)
    hechos: list[int] = []
    r.registrar("bueno", lambda c, j: hechos.append(j.id))
    malo = r.encolar("desconocido")
    bueno = r.encolar("bueno")
    assert r.run() == 2
    assert r.get(malo).estado == FALLIDO
    assert "sin handler" in r.get(malo).error
    assert r.get(bueno).estado == HECHO
    assert hechos == [bueno]


def test_reintenta_hasta_max_y_termina_fallido(conn):
    intentos_vistos: list[int] = []

    def siempre_falla(c, j):
        intentos_vistos.append(j.intentos)
        raise ValueError("no va")

    r = Runner(conn, max_intentos=3)
    r.registrar("t", siempre_falla)
    jid = r.encolar("t")

    assert r.run() == 1  # un solo job llegó a terminal (fallido)
    job = r.get(jid)
    assert job.estado == FALLIDO
    assert job.intentos == 3
    assert "ValueError: no va" in job.error
    assert intentos_vistos == [1, 2, 3]


def test_exito_despues_de_un_fallo_limpia_el_error(conn):
    llamadas: list[int] = []

    def falla_una_vez(c, j):
        llamadas.append(j.intentos)
        if j.intentos == 1:
            raise RuntimeError("primer intento")
        c.execute("INSERT INTO _efectos (job_id, nota) VALUES (?, ?)", (j.id, "al fin"))

    r = Runner(conn, max_intentos=3)
    r.registrar("t", falla_una_vez)
    jid = r.encolar("t")

    assert r.run() == 1
    job = r.get(jid)
    assert job.estado == HECHO
    assert job.intentos == 2
    assert job.error is None
    assert _contar_efectos(conn) == 1
    assert llamadas == [1, 2]


def test_los_efectos_de_un_intento_fallido_se_descartan(conn):
    def escribe_y_falla(c, j):
        c.execute(
            "INSERT INTO _efectos (job_id, nota) VALUES (?, ?)", (j.id, "fantasma")
        )
        raise ValueError("boom")

    r = Runner(conn, max_intentos=1)
    r.registrar("t", escribe_y_falla)
    jid = r.encolar("t")
    r.run()

    assert r.get(jid).estado == FALLIDO
    assert _contar_efectos(conn) == 0  # rollback: nada de lo que escribió quedó


def test_contar_por_estado(conn):
    r = Runner(conn)
    r.registrar("ok", lambda c, j: None)
    r.encolar("ok")
    r.encolar("ok")
    r.encolar("desconocido")
    r.run()
    assert r.contar_por_estado() == {HECHO: 2, FALLIDO: 1}


# --- construcción --------------------------------------------------- #


def test_max_intentos_invalido(conn):
    with pytest.raises(ValueError):
        Runner(conn, max_intentos=0)


def test_registrar_dos_veces_el_mismo_tipo_es_error(conn):
    r = Runner(conn)
    r.registrar("t", lambda c, j: None)
    with pytest.raises(ValueError):
        r.registrar("t", lambda c, j: None)


# --- recuperación de zombis ---------------------------------------- #


def test_recuperar_zombis_vuelve_a_pendiente(conn):
    jid = _insertar_zombi(conn, intentos=1)
    r = Runner(conn, max_intentos=3)
    assert r.recuperar_zombis() == 1
    job = r.get(jid)
    assert job.estado == PENDIENTE
    assert job.iniciado_at is None


def test_recuperar_zombis_falla_si_no_quedan_reintentos(conn):
    jid = _insertar_zombi(conn, intentos=2)
    r = Runner(conn, max_intentos=2)
    assert r.recuperar_zombis() == 1
    job = r.get(jid)
    assert job.estado == FALLIDO
    assert "no quedan reintentos" in job.error


def test_run_arranca_rescatando_zombis(conn):
    jid = _insertar_zombi(conn, intentos=1)
    r = Runner(conn)
    corridas: list[int] = []
    r.registrar("lento", lambda c, j: corridas.append(j.id))

    assert r.run() == 1
    assert corridas == [jid]
    job = r.get(jid)
    assert job.estado == HECHO
    assert job.intentos == 2  # 1 del intento que abortó la caída + 1 de ahora


def test_reclamo_sin_terminar_se_reanuda_una_sola_vez(conn):
    """Modela la caída del proceso justo después de reclamar el job: el reclamo
    quedó commiteado, el handler nunca corrió. Al reanudar, corre una vez y no
    duplica."""
    r1 = Runner(conn)
    r1.registrar("t", lambda c, j: None)
    jid = r1.encolar("t", {"n": "siete"})

    reclamado = r1._tomar()  # el proceso "muere" acá
    assert reclamado.id == jid
    assert reclamado.estado == EN_PROCESO
    assert reclamado.intentos == 1
    assert _contar_efectos(conn) == 0

    # proceso nuevo, mismo archivo de base
    r2 = Runner(conn)
    corridas: list[int] = []

    def handler(c, j):
        corridas.append(j.id)
        c.execute(
            "INSERT INTO _efectos (job_id, nota) VALUES (?, ?)", (j.id, j.payload["n"])
        )

    r2.registrar("t", handler)
    assert r2.run() == 1
    assert corridas == [jid]
    assert _contar_efectos(conn) == 1
    hecho = r2.get(jid)
    assert hecho.estado == HECHO
    assert hecho.intentos == 2


# --- el criterio de aceptación: caída real de proceso -------------- #


def test_proceso_muerto_a_mitad_reanuda_sin_perder_ni_duplicar(tmp_path):
    db_path = tmp_path / "spectre.db"
    marker = tmp_path / "marker.txt"
    salida = tmp_path / "worker.out"

    setup = connect(db_path)
    migrate(setup)
    setup.execute(
        "CREATE TABLE _efectos (id INTEGER PRIMARY KEY, job_id INTEGER, nota TEXT)"
    )
    setup.commit()
    jid = Runner(setup).encolar("lento", {"nota": "unico"})
    setup.close()

    with salida.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            [sys.executable, str(WORKER), str(db_path), str(marker)],
            stdout=out,
            stderr=subprocess.STDOUT,
        )
    try:
        for _ in range(100):  # hasta 10 s de margen para arrancar
            if marker.exists():
                break
            if proc.poll() is not None:
                pytest.fail(f"el worker murió antes de tiempo:\n{salida.read_text()}")
            time.sleep(0.1)
        else:
            pytest.fail(f"el worker no entró al handler:\n{salida.read_text()}")
        proc.kill()  # SIGKILL / TerminateProcess: caída sin limpieza
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    # el proceso murió con el job reclamado y los efectos SIN commitear
    c = connect(db_path)
    try:
        fila = c.execute(
            "SELECT estado, intentos FROM jobs WHERE id = ?", (jid,)
        ).fetchone()
        assert fila["estado"] == EN_PROCESO
        assert fila["intentos"] == 1
        assert c.execute("SELECT count(*) FROM _efectos").fetchone()[0] == 0

        # reanudar en este proceso
        r = Runner(c)
        corridas: list[int] = []

        def handler(conn, job):
            corridas.append(job.id)
            conn.execute(
                "INSERT INTO _efectos (job_id, nota) VALUES (?, ?)",
                (job.id, job.payload["nota"]),
            )

        r.registrar("lento", handler)
        assert r.run() == 1
        assert corridas == [jid]  # corrió una sola vez: no se duplicó
        filas = c.execute("SELECT nota FROM _efectos").fetchall()
        assert [f["nota"] for f in filas] == ["unico"]  # ni se perdió
        hecho = r.get(jid)
        assert hecho.estado == HECHO
        assert hecho.intentos == 2
    finally:
        c.close()
