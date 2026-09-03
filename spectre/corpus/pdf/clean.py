"""Limpieza del texto crudo de una página.

Tres arreglos sobre lo que devuelve pdfplumber, todos con casos reales del Tomo
348 (plan §6 PR-05):

1. **Encabezado repetido.** Cada página del cuerpo arranca con el encabezado de
   tomo/página (`DE JUSTICIA DE LA NACIÓN 15` / `348`, o `14 FALLOS DE LA CORTE
   SUPREMA` / `348`). En la primera página de cada mes vienen apilados los dos.
   Se sacan las líneas de encabezado del principio.
2. **Palabra cortada por guion.** `consti-\ntuya` → `constituya`. El guion puede
   traer espacios (`rese -\nñados`). Solo se une si lo que sigue empieza en
   minúscula: `-I-\nLa Sala` (marcador de sección) o `...cas-\n348 FALLOS`
   (corte entre páginas) quedan como están.
3. **Versalita mal extraída.** Los nombres y carátulas van en versalita y salen
   con mayúsculas y minúsculas mezcladas (`Luis ERnEsto c/ PERRonE`). Se pasan
   a Capitalizado (`Luis Ernesto c/ Perrone`).

Opera **por página** y llena `paginas.texto_limpio` a partir de `texto_crudo`;
los dos conviven en la base, así reindexar no reabre el PDF (D-8). Un guion de
corte justo en el borde entre dos páginas queda sin unir: eso lo resuelve quien
arma el texto del fallo desde las páginas (PR-07 / PR-11).

`corpus/` no importa `index/` ni `embed/`; el único cruce es `limpiar_tomo()`,
que escribe por `db/repo.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spectre.db import Repo

# Líneas de encabezado que se repiten en todo el cuerpo del tomo.
_ENCABEZADOS = (
    re.compile(r"^\d{1,4}\s+FALLOS DE LA CORTE SUPREMA\s*$", re.IGNORECASE),
    re.compile(r"^FALLOS DE LA CORTE SUPREMA\s*$", re.IGNORECASE),
    re.compile(r"^DE JUSTICIA DE LA NACI[ÓO]N(?:\s+\d{1,4})?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,4}\s*$"),  # el número de tomo (o de página) suelto
)
_MAX_LINEAS_ENCABEZADO = 4

# Palabra cortada por guion al final del renglón; se une si sigue en minúscula.
_GUION_CORTE = re.compile(r"([^\W\d_])[ \t]*-[ \t]*\n[ \t]*([a-záéíóúñüïö])")

# Cualquier palabra (letras). El filtro de versalita lo hace `_es_versalita`.
_PALABRA = re.compile(r"[^\W\d_]+")


def _sin_encabezado(texto: str) -> str:
    lineas = texto.splitlines()
    k = 0
    while (
        k < len(lineas)
        and k < _MAX_LINEAS_ENCABEZADO
        and any(rx.match(lineas[k]) for rx in _ENCABEZADOS)
    ):
        k += 1
    return "\n".join(lineas[k:])


def _unir_guiones(texto: str) -> str:
    return _GUION_CORTE.sub(r"\1\2", texto)


def _es_versalita(palabra: str) -> bool:
    """True si la palabra mezcla mayúsculas y minúsculas y **no** es
    Capitalizado normal (`Raskovsky`). Cubre `ERnEsto`, `FERnando`, `caRLos`."""
    tiene_alta = any(c.isupper() for c in palabra)
    tiene_baja = any(c.islower() for c in palabra)
    if not (tiene_alta and tiene_baja):
        return False
    return not (palabra[0].isupper() and palabra[1:].islower())


def _normalizar_versalitas(texto: str) -> str:
    return _PALABRA.sub(
        lambda m: m.group(0).capitalize() if _es_versalita(m.group(0)) else m.group(0),
        texto,
    )


def limpiar(texto: str) -> str:
    """El texto de una página, listo para fragmentar: sin encabezado repetido,
    sin guiones de corte y con las versalitas normalizadas."""
    t = _sin_encabezado(texto)
    t = _unir_guiones(t)
    t = _normalizar_versalitas(t)
    return t.strip()


def contar_palabras(texto: str) -> int:
    """Palabras separadas por espacios: la métrica del criterio de aceptación
    (el des-hifenado baja el conteo ~4,5% sobre el cuerpo del Tomo 348)."""
    return len(texto.split())


def limpiar_tomo(repo: Repo, tomo_id: int) -> int:
    """Llena `paginas.texto_limpio` de cada página del tomo desde `texto_crudo`.
    Devuelve cuántas páginas limpió. Falla ruidosamente si el tomo no tiene
    páginas extraídas (sin PR-04 no hay nada que limpiar)."""
    paginas = repo.list_paginas(tomo_id)
    if not paginas:
        raise ValueError(
            f"el tomo {tomo_id} no tiene páginas extraídas; corré la extracción primero"
        )
    repo.set_texto_limpio((p.id, limpiar(p.texto_crudo or "")) for p in paginas)
    return len(paginas)
