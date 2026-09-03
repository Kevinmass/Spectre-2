"""PR-01/02 — `spectre --help` anda, `db` migra, los subcomandos vacíos revientan."""

import pytest

from spectre.cli import main
from spectre.config import get_settings


@pytest.fixture
def datos_tmp(tmp_path, monkeypatch):
    """Redirige `data_dir` a un tmp para que `db` no escriba en el repo."""
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_help_sale_limpio(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "spectre" in out
    assert "config" in out


def test_version_sale_limpio(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "spectre" in capsys.readouterr().out


def test_config_imprime_rutas_resueltas(capsys):
    ret = main(["config"])
    assert ret == 0
    out = capsys.readouterr().out
    assert "data_dir" in out
    assert "spectre.db" in out
    assert "embedding_model" in out


def test_db_migrate_crea_la_base(capsys, datos_tmp):
    ret = main(["db", "migrate"])
    assert ret == 0
    out = capsys.readouterr().out
    assert "0001_initial" in out
    assert get_settings().db_path.is_file()


def test_db_migrate_es_idempotente_por_cli(capsys, datos_tmp):
    assert main(["db", "migrate"]) == 0
    capsys.readouterr()
    assert main(["db", "migrate"]) == 0
    assert "sin migraciones pendientes" in capsys.readouterr().out


def test_db_status_marca_pendiente_y_aplicada(capsys, datos_tmp):
    assert main(["db", "status"]) == 0
    assert "[pendiente] 0001_initial" in capsys.readouterr().out

    main(["db", "migrate"])
    capsys.readouterr()
    assert main(["db", "status"]) == 0
    assert "[aplicada ] 0001_initial" in capsys.readouterr().out


def test_db_sin_accion_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["db"])
    assert exc.value.code != 0


@pytest.mark.parametrize("cmd", ["ingest", "serve"])
def test_subcomandos_vacios_fallan_ruidosamente(cmd):
    # Ningún stub que reporte éxito (D-05).
    with pytest.raises(SystemExit) as exc:
        main([cmd])
    assert exc.value.code != 0
    assert "no implementado" in str(exc.value)


def test_sin_subcomando_es_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_subcomando_desconocido_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["noexiste"])
    assert exc.value.code != 0
