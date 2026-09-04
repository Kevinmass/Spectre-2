"""PR-24 — `scripts/arrancar.py`: la parte de "un comando" que ya corre
adentro del venv (bajar el modelo, indexar un tomo de muestra, levantar el
servidor). Ninguna corre `spectre serve` de verdad acá (bloquearía la
suite); `levantar_servidor`/`main` no se ejercitan, solo lo que es testeable
sin un proceso que se quede escuchando."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.arrancar import _tomo_de_muestra, bajar_modelo, indexar_tomo_de_muestra
from spectre.config import get_settings


@pytest.fixture
def datos_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _EntradaFalsa:
    def __init__(self, numero, csjn_tomo_id):
        self.numero = numero
        self.csjn_tomo_id = csjn_tomo_id


# --- _tomo_de_muestra: pura, sin red ni base ------------------------------ #


def test_tomo_de_muestra_prefiere_el_348():
    entradas = [_EntradaFalsa(1, "a"), _EntradaFalsa(348, "b"), _EntradaFalsa(2, "c")]
    assert _tomo_de_muestra(entradas).numero == 348


def test_tomo_de_muestra_sin_348_usa_el_primero():
    entradas = [_EntradaFalsa(10, "a"), _EntradaFalsa(20, "b")]
    assert _tomo_de_muestra(entradas).numero == 10


def test_tomo_de_muestra_catalogo_vacio_da_none():
    assert _tomo_de_muestra([]) is None


# --- indexar_tomo_de_muestra: catálogo/red que fallan --------------------- #


def test_indexar_tomo_de_muestra_catalogo_inalcanzable_no_revienta(
    monkeypatch, datos_tmp
):
    import spectre.corpus.csjn as csjn_pkg

    def falla(*_a, **_k):
        raise TimeoutError("sin red")

    monkeypatch.setattr(csjn_pkg, "listar_catalogo", falla)

    assert indexar_tomo_de_muestra() is False


def test_indexar_tomo_de_muestra_catalogo_vacio_no_revienta(monkeypatch, datos_tmp):
    import spectre.corpus.csjn as csjn_pkg

    monkeypatch.setattr(csjn_pkg, "listar_catalogo", lambda: [])

    assert indexar_tomo_de_muestra() is False


def test_indexar_tomo_de_muestra_etapa_fallida_no_revienta(monkeypatch, datos_tmp):
    import spectre.corpus.csjn as csjn_pkg

    monkeypatch.setattr(
        csjn_pkg, "listar_catalogo", lambda: [_EntradaFalsa(348, "447")]
    )

    def descarga_falla(*_a, **_k):
        raise RuntimeError("la CSJN devolvió 500")

    monkeypatch.setattr(csjn_pkg, "descargar_tomo", descarga_falla)

    assert indexar_tomo_de_muestra() is False
    # el tomo quedó registrado (iniciar_tomo corrió), solo no avanzó
    from spectre.db import Repo, connect

    conn = connect(get_settings().db_path)
    tomo = Repo(conn).get_tomo_por_numero(348)
    conn.close()
    assert tomo is not None
    assert tomo.estado == "registrado"


# --- indexar_tomo_de_muestra: camino feliz, con descarga y modelo falsos - #


@pytest.fixture
def _modelo_falso(monkeypatch):
    from spectre.embed.base import EmbeddingModel

    class _Falso(EmbeddingModel):
        nombre = "falso-arranque"
        dimension = 4

        def embed(self, textos):
            return [[1.0, 0.0, 0.0, 0.0] for _ in textos]

    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", lambda nombre=None: _Falso())


def test_indexar_tomo_de_muestra_termina_indexado(
    monkeypatch, datos_tmp, _modelo_falso
):
    from spectre.corpus.csjn.download import Descarga

    fixture = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"

    import spectre.corpus.csjn as csjn_pkg

    monkeypatch.setattr(
        csjn_pkg, "listar_catalogo", lambda: [_EntradaFalsa(348, "447")]
    )

    def descarga_falsa(csjn_tomo_id, destino, **_kwargs):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(fixture.read_bytes())
        return Descarga(
            ruta=destino,
            sha256="falso",
            bytes=destino.stat().st_size,
            reutilizada=False,
        )

    monkeypatch.setattr(csjn_pkg, "descargar_tomo", descarga_falsa)

    assert indexar_tomo_de_muestra() is True

    from spectre.db import Repo, connect

    conn = connect(get_settings().db_path)
    tomo = Repo(conn).get_tomo_por_numero(348)
    conn.close()
    assert tomo.estado == "indexado"


# --- bajar_modelo ----------------------------------------------------------- #


def test_bajar_modelo_carga_el_modelo_real_perezoso(monkeypatch):
    llamadas = []

    class _FalsoConDimension:
        @property
        def dimension(self):
            llamadas.append(1)
            return 4

    import spectre.embed as embed_pkg

    monkeypatch.setattr(
        embed_pkg, "cargar_modelo", lambda nombre=None: _FalsoConDimension()
    )

    bajar_modelo()
    assert llamadas == [1]
