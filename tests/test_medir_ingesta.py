"""PR-25 — `scripts/medir_ingesta.py`: las piezas testeables sin correr una
ingesta real (eso se verifica a mano contra el fixture de referencia, ver
`docs/qa/mediciones.md` y la bitácora — igual que `arrancar.py` en PR-24, un
subproceso real de minutos no entra en la suite de todos los días)."""

from __future__ import annotations

import sqlite3

import pytest

from scripts.medir_ingesta import (
    _MARCADOR_PICO,
    _duraciones_por_etapa,
    _entrypoint_subproceso,
    _pico_propio_mb,
    _tamano_dir,
    medir_tomo,
)

# --- _tamano_dir: sin red ni base ------------------------------------------ #


def test_tamano_dir_inexistente_da_cero(tmp_path):
    assert _tamano_dir(tmp_path / "no-existe") == 0


def test_tamano_dir_archivo(tmp_path):
    archivo = tmp_path / "algo.txt"
    archivo.write_bytes(b"x" * 123)
    assert _tamano_dir(archivo) == 123


def test_tamano_dir_carpeta_suma_recursivo(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"1" * 10)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"2" * 20)
    assert _tamano_dir(tmp_path) == 30


# --- _duraciones_por_etapa: sqlite en memoria, sin depender del pipeline --- #


def _conn_con_jobs(filas):
    """`filas`: lista de (tipo, tomo_id, iniciado_at, terminado_at)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, tipo TEXT, payload TEXT, "
        "iniciado_at TEXT, terminado_at TEXT)"
    )
    for tipo, tomo_id, ini, fin in filas:
        conn.execute(
            "INSERT INTO jobs (tipo, payload, iniciado_at, terminado_at) "
            "VALUES (?, ?, ?, ?)",
            (tipo, f'{{"tomo_id": {tomo_id}}}', ini, fin),
        )
    return conn


def test_duraciones_por_etapa_calcula_el_delta():
    conn = _conn_con_jobs(
        [
            (
                "pipeline.extraer",
                1,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:10",
            ),
        ]
    )
    assert _duraciones_por_etapa(conn, 1) == {"extraer": 10.0}


def test_duraciones_por_etapa_ignora_otro_tomo():
    conn = _conn_con_jobs(
        [("pipeline.extraer", 2, "2026-01-01T00:00:00", "2026-01-01T00:00:10")]
    )
    assert _duraciones_por_etapa(conn, 1) == {}


def test_duraciones_por_etapa_sin_terminar_no_aparece():
    conn = _conn_con_jobs([("pipeline.extraer", 1, "2026-01-01T00:00:00", None)])
    assert _duraciones_por_etapa(conn, 1) == {}


def test_duraciones_por_etapa_usa_la_corrida_mas_reciente():
    # un reintento anterior (más lento) no debe pisar el resultado más nuevo
    conn = _conn_con_jobs(
        [
            (
                "pipeline.extraer",
                1,
                "2026-01-01T00:00:00",
                "2026-01-01T00:01:00",
            ),
            (
                "pipeline.extraer",
                1,
                "2026-01-01T01:00:00",
                "2026-01-01T01:00:05",
            ),
        ]
    )
    assert _duraciones_por_etapa(conn, 1) == {"extraer": 5.0}


# --- _pico_propio_mb: medición real, no mockeada --------------------------- #


def test_pico_propio_mb_sube_al_asignar_memoria():
    antes = _pico_propio_mb()
    reserva = bytearray(200 * 1024 * 1024)  # 200 MB reales
    despues = _pico_propio_mb()
    del reserva
    assert despues >= antes
    # el pico ya refleja la reserva, incluso si el intérprete la libera después
    assert despues > 150


# --- _entrypoint_subproceso: reporta el marcador por stdout ---------------- #


def test_entrypoint_subproceso_imprime_marcador(monkeypatch, capsys):
    import spectre.cli as cli_pkg

    monkeypatch.setattr(cli_pkg, "main", lambda argv: 0)
    monkeypatch.setattr("scripts.medir_ingesta._pico_propio_mb", lambda: 42.5)

    rc = _entrypoint_subproceso(348, "un.pdf")

    assert rc == 0
    assert f"{_MARCADOR_PICO}42.5" in capsys.readouterr().out


def test_entrypoint_subproceso_propaga_codigo_de_error(monkeypatch, capsys):
    import spectre.cli as cli_pkg

    monkeypatch.setattr(cli_pkg, "main", lambda argv: 1)
    monkeypatch.setattr("scripts.medir_ingesta._pico_propio_mb", lambda: 1.0)

    assert _entrypoint_subproceso(348, "un.pdf") == 1


# --- medir_tomo: falla ruidosa si el subproceso no terminó bien ----------- #


def test_medir_tomo_subproceso_fallido_revienta(monkeypatch, tmp_path):
    import subprocess

    class _Resultado:
        returncode = 1
        stdout = "algo explotó"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Resultado())

    with pytest.raises(RuntimeError, match="código 1"):
        medir_tomo(348, tmp_path / "348.pdf", tmp_path / "datos")


def test_medir_tomo_sin_marcador_de_memoria_revienta(monkeypatch, tmp_path):
    import subprocess

    class _Resultado:
        returncode = 0
        stdout = "el subproceso no imprimió nada útil"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Resultado())

    with pytest.raises(RuntimeError, match="no reportó su pico de memoria"):
        medir_tomo(348, tmp_path / "348.pdf", tmp_path / "datos")
