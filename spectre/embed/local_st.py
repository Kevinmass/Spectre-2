"""Implementación local de `EmbeddingModel` con sentence-transformers.

Modelo por defecto (config `embedding_model`):
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` — multilingüe,
384 dimensiones, corre en CPU (D-7).

`sentence-transformers` es una dependencia **opcional** (`pip install -e
".[embed]"`): arrastra torch, que no hace falta para parsear ni segmentar. El
import es perezoso y, si falta, revienta con un mensaje claro (D-05: nada de
fingir que embebe).

Los vectores salen **normalizados** (norma 1): así el índice vectorial (PR-13)
usa producto interno como coseno sin más cuentas.
"""

from __future__ import annotations

from collections.abc import Sequence

from spectre.embed.base import EmbeddingModel

_FALTA_ST = (
    "sentence-transformers no está instalado. Es una dependencia opcional: "
    'corré `pip install -e ".[embed]"` en el venv del repo.'
)


class ModeloLocalST(EmbeddingModel):
    """Envuelve un `SentenceTransformer`. La carga del modelo (y la descarga la
    primera vez) es perezosa: recién al pedir `dimension` o `embed`."""

    def __init__(self, nombre: str, *, device: str = "cpu") -> None:
        self._nombre = nombre
        self._device = device
        self._st = None  # SentenceTransformer, cargado a demanda
        self._dim: int | None = None

    @property
    def nombre(self) -> str:
        return self._nombre

    def _cargar(self):
        if self._st is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(_FALTA_ST) from e
            self._st = SentenceTransformer(self._nombre, device=self._device)
            self._dim = int(self._st.get_sentence_embedding_dimension())
        return self._st

    @property
    def dimension(self) -> int:
        self._cargar()
        assert self._dim is not None
        return self._dim

    def embed(self, textos: Sequence[str]) -> list[list[float]]:
        st = self._cargar()
        vectores = st.encode(
            list(textos),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [[float(x) for x in fila] for fila in vectores]
