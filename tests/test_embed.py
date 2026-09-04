"""PR-12 — interfaz de embeddings + implementación local.

Criterio de aceptación (plan §6): cambiar el modelo en la config y ver que el
sistema identifica los chunks a reindexar **sin tocar los PDFs**. Eso vive en
`Repo.chunks_pendientes_de_embedding` (ver `test_db.py`); acá se prueba la
interfaz y la implementación local.

`sentence-transformers` es opcional. Los tests de la interfaz y del contrato
"falla ruidosamente si falta" corren siempre; el que carga el modelo real es
`slow` y se saltea si el paquete no está.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence

import pytest

from spectre.config import get_settings
from spectre.embed import EmbeddingModel, ModeloLocalST, cargar_modelo

_TIENE_ST = importlib.util.find_spec("sentence_transformers") is not None


# --- la interfaz ------------------------------------------------------- #


def test_embeddingmodel_es_abstracta():
    with pytest.raises(TypeError):
        EmbeddingModel()  # type: ignore[abstract]


class _Fake(EmbeddingModel):
    @property
    def nombre(self) -> str:
        return "fake-1"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, textos: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 0.0, 1.0] for t in textos]


def test_implementacion_minima_cumple_la_interfaz():
    m = _Fake()
    assert m.nombre == "fake-1"
    assert m.dimension == 3
    assert m.embed(["ab", "abcd"]) == [[2.0, 0.0, 1.0], [4.0, 0.0, 1.0]]


def test_embed_uno_delega_en_embed():
    assert _Fake().embed_uno("hola") == [4.0, 0.0, 1.0]


# --- cargar_modelo --------------------------------------------------- #


def test_cargar_modelo_usa_la_config_por_defecto():
    m = cargar_modelo()
    assert isinstance(m, ModeloLocalST)
    assert m.nombre == get_settings().embedding_model


def test_cargar_modelo_acepta_un_nombre_explicito():
    assert cargar_modelo("otra/cosa-mini").nombre == "otra/cosa-mini"


def test_cargar_modelo_no_carga_nada_todavia():
    # construir el modelo no baja pesos ni importa torch (es perezoso)
    cargar_modelo("modelo/que-no-existe")  # no revienta


# --- contrato "sin ST, falla ruidosamente" (D-05) ------------------- #


@pytest.mark.skipif(_TIENE_ST, reason="sentence-transformers instalado")
def test_sin_sentence_transformers_dimension_revienta_claro():
    m = ModeloLocalST("cualquier/cosa")
    assert m.nombre == "cualquier/cosa"  # el nombre no necesita el paquete
    with pytest.raises(ModuleNotFoundError, match=r"\[embed\]"):
        _ = m.dimension


@pytest.mark.skipif(_TIENE_ST, reason="sentence-transformers instalado")
def test_sin_sentence_transformers_embed_revienta_claro():
    with pytest.raises(ModuleNotFoundError, match="sentence-transformers"):
        ModeloLocalST("cualquier/cosa").embed(["hola"])


# --- el modelo real (opcional, lento) ------------------------------ #


@pytest.mark.slow
@pytest.mark.skipif(not _TIENE_ST, reason="falta sentence-transformers ([embed])")
def test_modelo_local_real_embebe_y_es_determinista():
    m = cargar_modelo()
    try:
        dim = m.dimension
    except OSError as e:  # sin conexión / sin caché del modelo
        pytest.skip(f"no se pudo cargar el modelo: {e}")
    assert dim == 384  # D-7: multilingüe chico, 384 dimensiones

    v1 = m.embed(["El actor apeló la sentencia.", "La Corte revocó el fallo."])
    assert len(v1) == 2
    assert all(len(v) == dim for v in v1)
    # normalizado (norma ~1) y determinista
    assert abs(sum(x * x for x in v1[0]) ** 0.5 - 1.0) < 1e-3
    v2 = m.embed(["El actor apeló la sentencia.", "La Corte revocó el fallo."])
    assert v1 == v2

    def cos(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    par = m.embed(
        [
            "El tribunal hizo lugar al recurso extraordinario.",
            "La Corte admitió el recurso extraordinario.",
            "La factura vence el próximo martes.",
        ]
    )
    assert cos(par[0], par[1]) > cos(par[0], par[2])
