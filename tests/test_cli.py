"""PR-01/02/04/06-13 — `--help` anda, `db` migra, `pdf` mide, `embed` e `index`
reportan, los vacíos revientan."""

import importlib.util
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


def test_pdf_quality_clasifica_digital(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
    assert main(["pdf", "quality", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "calidad" in out
    assert "digital" in out
    assert "caracteres/página" in out


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


def test_pdf_sections_resume_el_tomo(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    assert main(["pdf", "sections", str(fixture), "--tomo", "348"]) == 0
    out = capsys.readouterr().out
    assert "con >=1 voto" in out
    assert "líneas de contenido huérfanas" in out


def test_pdf_sections_detalla_una_cita(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    assert (
        main(["pdf", "sections", str(fixture), "--tomo", "348", "--cita", "348:34"])
        == 0
    )
    out = capsys.readouterr().out
    assert "mayoria" in out
    assert "voto" in out
    assert "Ricardo Luis Lorenzetti" in out


def test_pdf_citations_resume_el_tomo(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p189-246.pdf"
    assert main(["pdf", "citations", str(fixture), "--tomo", "348"]) == 0
    out = capsys.readouterr().out
    assert "referencias Fallos: N:N" in out
    assert "citas (fallo a fallo)" in out
    assert "tomos citados distintos" in out


def test_pdf_citations_detalla_una_cita(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p189-246.pdf"
    assert (
        main(["pdf", "citations", str(fixture), "--tomo", "348", "--cita", "348:189"])
        == 0
    )
    out = capsys.readouterr().out
    assert "Fallos: 337:315" in out  # cita real del fallo "Acevedo"
    assert "referencias" in out


def test_pdf_citations_cita_inexistente_es_error():
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p189-246.pdf"
    with pytest.raises(SystemExit) as exc:
        main(["pdf", "citations", str(fixture), "--tomo", "348", "--cita", "999:1"])
    assert "999:1" in str(exc.value)


def test_pdf_chunks_resume_el_tomo(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    assert main(["pdf", "chunks", str(fixture), "--tomo", "348"]) == 0
    out = capsys.readouterr().out
    assert "chunks" in out
    assert "chunks fuera de su secci" in out
    assert "referencia global" in out


def test_pdf_chunks_detalla_un_fallo(capsys):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    assert (
        main(["pdf", "chunks", str(fixture), "--tomo", "348", "--cita", "348:34"]) == 0
    )
    out = capsys.readouterr().out
    assert "mayoria" in out
    assert "voto" in out
    assert "Ricardo Luis Lorenzetti" in out


def test_pdf_chunks_solape_invalido_es_error():
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    with pytest.raises(SystemExit) as exc:
        main(["pdf", "chunks", str(fixture), "--tomo", "348", "--solape", "400"])
    assert exc.value.code != 0


def test_pdf_sin_accion_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["pdf"])
    assert exc.value.code != 0


# --- embed (PR-12) ------------------------------------------------------ #

_TIENE_ST = importlib.util.find_spec("sentence_transformers") is not None


def test_embed_status_sin_base(capsys, datos_tmp):
    assert main(["embed", "status"]) == 0
    out = capsys.readouterr().out
    assert "modelo (config)" in out
    assert "no existe" in out


def test_embed_status_con_chunks(capsys, datos_tmp):
    main(["db", "migrate"])
    capsys.readouterr()
    from spectre.db import Repo, connect

    conn = connect(get_settings().db_path)
    repo = Repo(conn)
    tomo_id = repo.insert_tomo(348)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    repo.insert_chunks(fallo_id, [(None, i, f"t{i}", None) for i in range(4)])
    conn.close()

    assert main(["embed", "status"]) == 0
    out = capsys.readouterr().out
    assert "chunks" in out
    assert "4" in out  # 4 chunks, 4 pendientes
    assert "pendientes de embedding" in out


@pytest.mark.skipif(
    _TIENE_ST, reason="sentence-transformers instalado: probe cargaría el modelo real"
)
def test_embed_probe_sin_sentence_transformers_falla_claro():
    with pytest.raises(SystemExit) as exc:
        main(["embed", "probe", "un texto de prueba"])
    assert ".[embed]" in str(exc.value)


def test_embed_sin_accion_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["embed"])
    assert exc.value.code != 0


# --- index (PR-13) ---------------------------------------------------- #


def test_index_status_indice_vacio_sin_base(capsys, datos_tmp):
    assert main(["index", "status"]) == 0
    out = capsys.readouterr().out
    assert "índice vectorial" in out
    assert "sin crear" in out
    assert "no existe" in out


def test_index_status_cuenta_vectores_y_chunks(capsys, datos_tmp):
    main(["db", "migrate"])
    capsys.readouterr()
    from spectre.db import Repo, connect
    from spectre.index import IndiceVectorial

    s = get_settings()
    conn = connect(s.db_path)
    repo = Repo(conn)
    tomo_id = repo.insert_tomo(348)
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
    repo.insert_chunks(fallo_id, [(None, i, f"t{i}", None) for i in range(3)])
    conn.close()

    idx = IndiceVectorial(s.vectors_dir, dimension=4)
    idx.upsert([(1, [1, 0, 0, 0], "m"), (2, [0, 1, 0, 0], "m")])

    assert main(["index", "status"]) == 0
    out = capsys.readouterr().out
    assert "2 vectores" in out
    assert "chunks en SQLite" in out
    assert "chunks en el índice vectorial" in out


def test_index_sin_accion_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["index"])
    assert exc.value.code != 0


# --- csjn (PR-16) -------------------------------------------------------- #


@pytest.mark.red
def test_csjn_catalog_imprime_el_resumen(capsys):
    # El sitio real crece con el tiempo (la CSJN publica tomos nuevos); no se
    # fija un total exacto, ver test_catalog.py::test_listar_catalogo_real.
    assert main(["csjn", "catalog"]) == 0
    out = capsys.readouterr().out
    assert "filas del catálogo" in out
    assert "números de tomo distintos" in out
    assert "con más de un volumen" in out


@pytest.mark.red
def test_csjn_catalog_muestra_filas(capsys):
    assert main(["csjn", "catalog", "--muestra", "2"]) == 0
    out = capsys.readouterr().out
    assert "tomoId=" in out


# --- csjn download (PR-17) ----------------------------------------------- #


@pytest.mark.red
def test_csjn_download_baja_y_despues_usa_cache(capsys, tmp_path):
    destino = tmp_path / "349.pdf"

    assert main(["csjn", "download", "447", str(destino)]) == 0
    out = capsys.readouterr().out
    assert "sha256" in out
    assert "no (se descargó ahora)" in out
    assert destino.is_file()

    assert main(["csjn", "download", "447", str(destino)]) == 0
    assert "sí" in capsys.readouterr().out


def test_csjn_sin_accion_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["csjn"])
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
