"""PR-01/02/04/06/07 — `--help` anda, `db` migra, `pdf` mide, los vacíos revientan."""

from pathlib import Path

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


def test_pdf_stats_imprime_cobertura_y_offset(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
    assert main(["pdf", "stats", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "páginas" in out
    assert "offset" in out
    assert "6" in out


def test_pdf_clean_imprime_reduccion(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
    assert main(["pdf", "clean", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "palabras crudas" in out
    assert "reducción" in out


def test_pdf_clean_muestra_una_pagina(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
    assert main(["pdf", "clean", str(fixture), "--muestra", "7"]) == 0
    out = capsys.readouterr().out
    assert "Luis Ernesto c/ Perrone" in out
    assert not out.splitlines()[-1].startswith("DE JUSTICIA")


def test_pdf_index_cuenta_caratulas(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_indice.pdf"
    assert main(["pdf", "index", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "carátulas" in out
    assert "129" in out
    assert "pdf_page 2–6" in out


def test_pdf_index_muestra_entradas(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_indice.pdf"
    assert main(["pdf", "index", str(fixture), "--muestra", "3"]) == 0
    out = capsys.readouterr().out
    assert "Acevedo, Eva María" in out
    assert "varios fallos" in out  # las 3 carátulas multi-página


def test_pdf_segment_arma_los_fallos(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_indice.pdf"
    assert main(["pdf", "segment", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "método" in out and "indice" in out
    assert "fallo más largo  57 páginas" in out
    assert "mediana          4 páginas" in out
    assert "solapamientos    0" in out


def test_pdf_segment_muestra_fallos_con_cita(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_indice.pdf"
    assert main(["pdf", "segment", str(fixture), "--muestra", "2"]) == 0
    out = capsys.readouterr().out
    assert "Fallos: 348:1" in out
    assert "Raskovsky, Luis Ernesto c/ Perrone" in out


def test_pdf_segment_sin_numero_de_tomo_inferible(capsys, tmp_path):
    pdf = tmp_path / "sin-numero.pdf"
    pdf.write_bytes(
        (Path(__file__).parent / "fixtures" / "tomo348_indice.pdf").read_bytes()
    )
    with pytest.raises(SystemExit) as exc:
        main(["pdf", "segment", str(pdf)])
    assert "--tomo" in str(exc.value)


def test_pdf_sin_accion_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["pdf"])
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
