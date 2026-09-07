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


# --- sumarios sync / status (PR-C2b) ----------------------------------- #


def test_sumarios_sync_llama_al_sincronizador_e_imprime_el_resumen(
    capsys, datos_tmp, monkeypatch
):
    from spectre.db import Repo, connect, migrate
    from spectre.sumarios import ResumenSync

    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    migrate(conn)
    Repo(conn).insert_tomo(348, estado="indexado")
    conn.close()

    import spectre.sumarios as sumarios_mod

    monkeypatch.setattr(
        sumarios_mod,
        "sincronizar_tomo",
        lambda *a, **k: ResumenSync(
            tomo=348,
            fallos_consultados=3,
            fallos_con_sumario=2,
            sumarios_totales=5,
            voces_distintas=7,
        ),
    )

    assert main(["sumarios", "sync", "348"]) == 0
    out = capsys.readouterr().out
    assert "fallos con sumario  2" in out
    assert "voces distintas     7" in out


def test_sumarios_sync_tomo_no_indexado_revienta(datos_tmp):
    from spectre.db import connect, migrate

    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    migrate(conn)
    conn.close()

    with pytest.raises(SystemExit) as exc:
        main(["sumarios", "sync", "500"])
    assert "no existe el tomo 500" in str(exc.value)


def test_sumarios_status_lista_conteos(capsys, datos_tmp):
    from spectre.db import Repo, connect, migrate

    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    migrate(conn)
    repo = Repo(conn)
    tomo_id = repo.insert_tomo(348, estado="indexado")
    fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1", pagina_inicio=1)
    repo.reemplazar_sumarios_de_fallo(fallo_id, [(0, "x", ["V"], None, None)])
    conn.close()

    assert main(["sumarios", "status"]) == 0
    out = capsys.readouterr().out
    assert "sumarios: 1" in out
    assert "tomo 348: 1 sumario(s)" in out


# --- ingest (PR-19) ------------------------------------------------------- #


@pytest.fixture
def _modelo_falso_cli(monkeypatch):
    """`ingest` corre la etapa `embeber` de verdad; un modelo falso evita
    depender de `[embed]` (torch) para probar el CLI."""
    from spectre.embed.base import EmbeddingModel

    class _Falso(EmbeddingModel):
        nombre = "falso-cli"
        dimension = 4

        def embed(self, textos):
            return [[1.0, 0.0, 0.0, 0.0] for _ in textos]

    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", lambda nombre=None: _Falso())


def test_ingest_pdf_local_corre_las_ocho_etapas(capsys, datos_tmp, _modelo_falso_cli):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    assert main(["ingest", "348", "--pdf", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "estado   indexado" in out
    assert "etapas   8/8" in out
    assert "fallos   3" in out
    assert "chunks" in out


def test_ingest_es_reanudable_sin_reprocesar(capsys, datos_tmp, _modelo_falso_cli):
    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
    assert main(["ingest", "348", "--pdf", str(fixture)]) == 0
    capsys.readouterr()
    assert main(["ingest", "348"]) == 0  # sin --pdf: ya lo tiene guardado
    out = capsys.readouterr().out
    assert "estado   indexado" in out


def test_ingest_sin_pdf_ni_csjn_id_revienta_en_descargar(capsys, datos_tmp):
    with pytest.raises(SystemExit) as exc:
        main(["ingest", "999"])
    assert "descargar" in str(exc.value)
    assert "csjn_tomo_id" in str(exc.value)
    out = capsys.readouterr().out
    assert "estado   registrado" in out  # no avanzó ni una etapa


# --- serve (PR-20) ------------------------------------------------------- #


def test_serve_migra_y_levanta_uvicorn_en_host_y_puerto(monkeypatch, datos_tmp):
    llamadas: dict[str, object] = {}

    def uvicorn_run_falso(app, host, port, log_level=None):
        llamadas["host"] = host
        llamadas["port"] = port

    monkeypatch.setattr("uvicorn.run", uvicorn_run_falso)
    monkeypatch.setattr("webbrowser.open", lambda url: None)

    assert main(["serve", "--port", "8123"]) == 0

    assert llamadas == {"host": "127.0.0.1", "port": 8123}
    assert get_settings().db_path.is_file()  # migró antes de levantar


def test_serve_arma_el_hook_que_abre_el_navegador(monkeypatch, datos_tmp):
    capturado: dict[str, object] = {}

    def crear_app_falsa(*, on_startup=None):
        capturado["on_startup"] = on_startup
        return "app-falsa"

    monkeypatch.setattr("spectre.api.crear_app", crear_app_falsa)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    abiertas = []
    monkeypatch.setattr("webbrowser.open", abiertas.append)

    assert main(["serve", "--port", "8123"]) == 0

    capturado["on_startup"]()
    assert abiertas == ["http://127.0.0.1:8123/"]


def test_serve_con_no_browser_no_registra_hook(monkeypatch, datos_tmp):
    capturado: dict[str, object] = {}
    monkeypatch.setattr(
        "spectre.api.crear_app",
        lambda *, on_startup=None: capturado.setdefault("on_startup", on_startup),
    )
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)

    assert main(["serve", "--no-browser"]) == 0
    assert capturado["on_startup"] is None


def test_sin_subcomando_es_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_subcomando_desconocido_es_error():
    with pytest.raises(SystemExit) as exc:
        main(["noexiste"])
    assert exc.value.code != 0
