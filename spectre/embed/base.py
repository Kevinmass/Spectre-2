"""La interfaz de embeddings: `EmbeddingModel`.

Decisión D-7 del plan: el modelo es intercambiable. Todo lo que produzca un
vector por texto y sepa decir su nombre y su dimensión sirve. La implementación
por defecto es local y chica (`local_st.ModeloLocalST`), pero el resto del
sistema no la conoce: habla contra esta interfaz.

Decisión D-8: el embedding está separado del parseo. `EmbeddingModel.embed`
recibe texto (el de `chunks.texto`, que vive en SQLite) y devuelve vectores.
Cambiar de modelo reindexa sin volver a abrir un PDF.

**El nombre del modelo se registra por chunk** (`chunks.modelo_embedding`). Si
cambia, `Repo.chunks_pendientes_de_embedding` sabe cuáles hay que rehacer.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence


class EmbeddingModel(abc.ABC):
    """Un modelo de embeddings. Implementaciones concretas: `local_st`."""

    @property
    @abc.abstractmethod
    def nombre(self) -> str:
        """Identificador estable del modelo. Es lo que se guarda en
        `chunks.modelo_embedding` y lo que decide qué reindexar si cambia."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Cantidad de componentes de cada vector. Fija para un modelo dado."""

    @abc.abstractmethod
    def embed(self, textos: Sequence[str]) -> list[list[float]]:
        """Un vector por texto, en el mismo orden. Lista de listas de `float`
        (sin numpy: el contrato no ata a nadie a una librería)."""

    def embed_uno(self, texto: str) -> list[float]:
        """Atajo para un solo texto."""
        return self.embed([texto])[0]
