"""Chunker consciente de secciones: parte el texto de un fallo en fragmentos de
~400 palabras con 80 de solape, **sin cruzar nunca el borde de una sección**.

Regla D-4 del plan: un chunk no puede mezclar mayoría, voto concurrente y
disidencia — devolver una disidencia como doctrina de la Corte es un riesgo
profesional. PR-09 marcó esos bordes (`SeccionFallo`); PR-11 fragmenta **dentro**
de cada sección, así el borde se respeta por construcción.

Cada `Chunk` hereda (plan §5, tabla `chunks`):

- **cita** del fallo (`348:145`, D-3) y el orden dentro de la sección;
- **sección**: tipo (`mayoria` / `voto` / `disidencia` / `dictamen`), autor y el
  orden de la sección dentro del fallo;
- **página oficial**: se ubica el arranque del chunk en el texto por página del
  fallo (`structure.texto_del_fallo_paginado`); si no se puede (texto de sumario
  reordenado, blancos que no coinciden), cae en la página de inicio del fallo.

No toca la base (el volcado a `chunks` es PR-19). `modelo_embedding` y
`embedding_at` los pone PR-12/13.

Referencia de PR-11 (plan §6): el cuerpo del Tomo 348 des-hifenado ronda las
333.000 palabras, que a 400 con 80 de solape (paso 320) dan ~1.041 chunks si se
cuenta global. El conteo real es por sección y da algo más (cada sección redondea
para arriba). Un número *muy* lejos indica que la limpieza o la segmentación se
rompieron.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spectre.corpus.fallo.sections import SeccionFallo

#: Tamaño de ventana y solape, en palabras. Configurables desde el CLI.
OBJETIVO_PALABRAS = 400
SOLAPE_PALABRAS = 80

#: Cuántos caracteres del arranque del chunk se usan para ubicarlo en una página.
_CLAVE_LARGA = 80
_CLAVE_CORTA = 40


@dataclass(frozen=True, slots=True)
class Chunk:
    """Un fragmento listo para embeber. Mapea a una fila de `chunks` (el
    `fallo_id` / `seccion_id` los resuelve PR-19 contra la base)."""

    cita: str  # del fallo: "348:145"
    seccion_tipo: str  # "mayoria" | "voto" | "disidencia" | "dictamen"
    seccion_autor: str | None
    seccion_orden: int  # orden de la sección dentro del fallo
    orden: int  # orden del chunk dentro de la sección
    pagina_oficial: int | None
    texto: str
    n_palabras: int


def ventanas(
    palabras: list[str],
    *,
    objetivo: int = OBJETIVO_PALABRAS,
    solape: int = SOLAPE_PALABRAS,
) -> list[list[str]]:
    """Ventanas deslizantes de `objetivo` palabras con `solape` de arrastre.
    Una lista más corta que `objetivo` es una sola ventana. La última ventana
    llega hasta el final; no se abre una ventana nueva si lo que queda ya está
    entero en la anterior."""
    if objetivo <= 0 or not 0 <= solape < objetivo:
        raise ValueError(f"objetivo>0 y 0<=solape<objetivo (dan {objetivo}, {solape})")
    if not palabras:
        return []
    paso = objetivo - solape
    trozos: list[list[str]] = []
    i = 0
    while True:
        trozos.append(palabras[i : i + objetivo])
        if i + objetivo >= len(palabras):
            break
        i += paso
        if i + solape >= len(palabras):
            # lo que queda cabe entero en la ventana anterior
            break
    return trozos


def normalizar_espacios(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def ubicar_pagina(chunk_norm: str, paginas_norm: list[tuple[int, str]]) -> int | None:
    """La página oficial cuyo texto contiene el arranque del chunk, o `None` si
    no se encuentra (chunk de sumario reordenado, blancos que no coinciden)."""
    for largo in (_CLAVE_LARGA, _CLAVE_CORTA):
        clave = chunk_norm[:largo]
        if not clave:
            break
        for oficial, texto in paginas_norm:
            if clave in texto:
                return oficial
    return None


def fragmentar_seccion(
    seccion: SeccionFallo,
    *,
    cita: str,
    pagina_inicio: int,
    paginas_norm: list[tuple[int, str]],
    objetivo: int = OBJETIVO_PALABRAS,
    solape: int = SOLAPE_PALABRAS,
) -> list[Chunk]:
    """Los chunks de **una** sección. Nunca mezclan otra sección: el texto sale
    de `seccion.texto` y nada más."""
    chunks: list[Chunk] = []
    for orden, palabras in enumerate(
        ventanas(seccion.texto.split(), objetivo=objetivo, solape=solape)
    ):
        texto = " ".join(palabras)
        pagina = ubicar_pagina(normalizar_espacios(texto), paginas_norm)
        chunks.append(
            Chunk(
                cita=cita,
                seccion_tipo=seccion.tipo,
                seccion_autor=seccion.autor,
                seccion_orden=seccion.orden,
                orden=orden,
                pagina_oficial=pagina if pagina is not None else pagina_inicio,
                texto=texto,
                n_palabras=len(palabras),
            )
        )
    return chunks


def fragmentar_fallo(
    secciones: list[SeccionFallo],
    paginado: list[tuple[int, str]],
    *,
    cita: str,
    pagina_inicio: int,
    objetivo: int = OBJETIVO_PALABRAS,
    solape: int = SOLAPE_PALABRAS,
) -> list[Chunk]:
    """Todos los chunks de un fallo, sección por sección y en orden. `paginado`
    es `structure.texto_del_fallo_paginado(...)`; `secciones` es
    `sections.partir_secciones(...)` sobre el mismo texto."""
    paginas_norm = [(oficial, normalizar_espacios(t)) for oficial, t in paginado]
    chunks: list[Chunk] = []
    for seccion in secciones:
        chunks.extend(
            fragmentar_seccion(
                seccion,
                cita=cita,
                pagina_inicio=pagina_inicio,
                paginas_norm=paginas_norm,
                objetivo=objetivo,
                solape=solape,
            )
        )
    return chunks
