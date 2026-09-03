"""PR-01 — `spectre --help` anda y los subcomandos vacíos revientan."""

import pytest

from spectre.cli import main


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


@pytest.mark.parametrize("cmd", ["db", "ingest", "serve"])
def test_subcomandos_vacios_fallan_ruidosamente(cmd, capsys):
    # Ningún stub que reporte éxito (D-05).
    with pytest.raises(SystemExit) as exc:
        main([cmd])
    assert exc.value.code != 0
    assert "no implementado" in str(exc.value)


def test_sin_subcomando_es_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_subcomando_desconocido_es_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["noexiste"])
    assert exc.value.code != 0
