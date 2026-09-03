"""Segmentador de fallos: del índice (o de los delimitadores) a los rangos de
página, con la cita oficial de cada fallo.

**Plan A — el índice** (decisión D-2). Cada carátula del ÍNDICE POR LOS NOMBRES
DE LAS PARTES (PR-06) arranca un fallo en su página oficial de inicio. El fallo
llega hasta la página anterior al arranque del siguiente; el último, hasta la
última página del cuerpo. Una carátula que figura en varios fallos
(`ps. 443 y 494`) produce un fallo por página. La cita es `<tomo>:<pág. inicio>`
(D-3): `348:145`.

**Plan B — los delimitadores** (`segmentar_por_delimitadores`), para un tomo sin
índice parseable. Un fallo arranca donde una página del cuerpo trae la
**carátula en versalita** en sus primeras líneas (`acEvEdo, Eva maRía c/ ...
s/ quiEbRa`). Los delimitadores de texto que nombra el plan —`FALLO DE LA
CORTE`, `Autos y Vistos`, `Buenos Aires, <fecha>`— **no** se usan para cortar:
D-2 midió que sobre-parten (54 de 121 páginas con delimitador caen dentro de un
fallo ya empezado: dictámenes del Procurador, resoluciones intermedias). La
carátula en versalita es el único corte que no se dispara en medio de un fallo.
Aun así el resultado se marca `dudosa`: quien llama decide si confía o indexa a
nivel página (R-2). El fallback **no parte** el fallo más largo del Tomo 348
(57 páginas): sus páginas interiores no traen carátula.

No toca la base. Usa `es_versalita` de `corpus/pdf/clean` (mismo criterio que la
normalización de PR-05) y opera sobre listas ya extraídas; orquestar
extracción + parseo + segmentación es del CLI y de PR-19.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from spectre.corpus.pdf.clean import es_versalita, limpiar

if TYPE_CHECKING:
    from spectre.corpus.fallo.index_parser import EntradaIndice
    from spectre.corpus.pdf.extract import PaginaTexto

#: Palabra (solo letras); el filtro de versalita lo hace `es_versalita`.
_PALABRA = re.compile(r"[^\W\d_]+")

#: Una línea es carátula de fallo si trae `c/` o `s/` (litigio) y al menos esta
#: cantidad de palabras en versalita (así se distingue del cuerpo y de los
#: títulos de doctrina en MAYÚSCULAS).
_MIN_VERSALITAS = 2

#: La carátula va en las primeras líneas de la página; se miran estas (tras el
#: encabezado y, si está, la cola del fallo anterior).
_LINEAS_CABEZA = 8


@dataclass(frozen=True, slots=True)
class FalloSegmentado:
    """Un fallo ubicado en el tomo: carátula, cita y rango de página oficial."""

    caratula: str
    cita: str  # "<tomo>:<pág. inicio>", p. ej. "348:189"
    pagina_inicio: int  # página oficial, inclusive
    pagina_fin: int  # página oficial, inclusive
    metodo: str  # "indice" | "delimitadores"

    @property
    def paginas(self) -> int:
        return self.pagina_fin - self.pagina_inicio + 1


@dataclass(frozen=True, slots=True)
class ResumenSegmentacion:
    """Los fallos de un tomo y lo que mide el criterio de aceptación de PR-07."""

    fallos: tuple[FalloSegmentado, ...]
    metodo: str  # "indice" | "delimitadores"
    dudosa: bool  # True si vino del fallback

    @property
    def cantidad(self) -> int:
        return len(self.fallos)

    @property
    def cobertura(self) -> tuple[int, int]:
        return (self.fallos[0].pagina_inicio, self.fallos[-1].pagina_fin)

    @property
    def solapamientos(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (a.cita, b.cita)
            for a, b in zip(self.fallos, self.fallos[1:], strict=False)
            if a.pagina_fin >= b.pagina_inicio
        )

    @property
    def huecos(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (a.pagina_fin, b.pagina_inicio)
            for a, b in zip(self.fallos, self.fallos[1:], strict=False)
            if b.pagina_inicio - a.pagina_fin > 1
        )

    @property
    def pagina_mas_larga(self) -> int:
        return max(f.paginas for f in self.fallos)

    @property
    def mediana_paginas(self) -> float:
        return statistics.median(f.paginas for f in self.fallos)


def _rangos(
    inicios: list[tuple[int, str]],
    *,
    tomo_numero: int,
    pagina_fin_cuerpo: int,
    metodo: str,
) -> list[FalloSegmentado]:
    """De una lista ordenada de `(pág. inicio, carátula)` a los fallos con su
    rango: cada uno llega hasta la página anterior al siguiente; el último,
    hasta `pagina_fin_cuerpo`."""
    repetidas = sorted(p for p, n in Counter(p for p, _ in inicios).items() if n > 1)
    if repetidas:
        raise ValueError(f"páginas de inicio repetidas: {repetidas}")
    if inicios[-1][0] > pagina_fin_cuerpo:
        raise ValueError(
            f"un fallo arranca en la página {inicios[-1][0]} pero el cuerpo "
            f"termina en la {pagina_fin_cuerpo}"
        )
    fallos: list[FalloSegmentado] = []
    for i, (inicio, caratula) in enumerate(inicios):
        fin = inicios[i + 1][0] - 1 if i + 1 < len(inicios) else pagina_fin_cuerpo
        fallos.append(
            FalloSegmentado(
                caratula=caratula,
                cita=f"{tomo_numero}:{inicio}",
                pagina_inicio=inicio,
                pagina_fin=fin,
                metodo=metodo,
            )
        )
    return fallos


def segmentar_desde_indice(
    entradas: list[EntradaIndice],
    *,
    tomo_numero: int,
    pagina_fin_cuerpo: int,
) -> list[FalloSegmentado]:
    """Plan A: los rangos salen del índice de partes. Falla ruidosamente si dos
    carátulas arrancan en la misma página o si el índice cita más allá del
    cuerpo (no se inventa un rango)."""
    if not entradas:
        raise ValueError("no hay entradas de índice para segmentar")
    inicios = sorted((p, e.caratula) for e in entradas for p in e.paginas)
    return _rangos(
        inicios,
        tomo_numero=tomo_numero,
        pagina_fin_cuerpo=pagina_fin_cuerpo,
        metodo="indice",
    )


def _linea_es_caratula(linea: str) -> bool:
    con_bordes = f" {linea.strip()} "
    if " c/ " not in con_bordes and " s/ " not in con_bordes:
        return False
    palabras = _PALABRA.findall(linea)
    return sum(1 for p in palabras if es_versalita(p)) >= _MIN_VERSALITAS


def _caratula_de_pagina(texto: str) -> str | None:
    """La carátula en versalita si la página arranca un fallo, o None. Devuelve
    la línea normalizada (`limpiar` pasa las versalitas a Capitalizado)."""
    for cruda in [ln for ln in texto.splitlines() if ln.strip()][:_LINEAS_CABEZA]:
        if _linea_es_caratula(cruda):
            return limpiar(cruda).strip()
    return None


def segmentar_por_delimitadores(
    paginas: list[PaginaTexto],
    *,
    tomo_numero: int,
    pagina_fin_cuerpo: int,
) -> list[FalloSegmentado]:
    """Plan B (marcá el resultado `dudosa`): un fallo arranca donde una página
    del cuerpo trae la carátula en versalita. No corta por `FALLO DE LA CORTE` /
    `Autos y Vistos` (sobre-parten, D-2)."""
    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    if not cuerpo:
        raise ValueError("ninguna página con número oficial: nada que segmentar")
    inicios: list[tuple[int, str]] = []
    for p in cuerpo:
        caratula = _caratula_de_pagina(p.texto)
        if caratula is not None:
            inicios.append((p.pagina_oficial, caratula))
    if not inicios:
        raise ValueError("no se detectó ninguna carátula de fallo en el cuerpo")
    inicios.sort()
    return _rangos(
        inicios,
        tomo_numero=tomo_numero,
        pagina_fin_cuerpo=pagina_fin_cuerpo,
        metodo="delimitadores",
    )


def segmentar(
    entradas: list[EntradaIndice] | None,
    paginas: list[PaginaTexto],
    *,
    tomo_numero: int,
) -> ResumenSegmentacion:
    """Segmenta por índice si hay entradas; si no (el índice no parseó), por
    delimitadores y marca el resultado `dudosa`. La última página del cuerpo se
    deduce del mayor número de página oficial detectado."""
    oficiales = [p.pagina_oficial for p in paginas if p.pagina_oficial is not None]
    if not oficiales:
        raise ValueError("ninguna página con número oficial")
    pagina_fin_cuerpo = max(oficiales)
    if entradas:
        fallos = segmentar_desde_indice(
            entradas, tomo_numero=tomo_numero, pagina_fin_cuerpo=pagina_fin_cuerpo
        )
        return ResumenSegmentacion(tuple(fallos), "indice", dudosa=False)
    fallos = segmentar_por_delimitadores(
        paginas, tomo_numero=tomo_numero, pagina_fin_cuerpo=pagina_fin_cuerpo
    )
    return ResumenSegmentacion(tuple(fallos), "delimitadores", dudosa=True)
