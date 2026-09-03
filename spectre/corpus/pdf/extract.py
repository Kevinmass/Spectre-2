"""Extracción de texto por página y detección de la paginación oficial.

Un tomo de Fallos es un PDF con unas páginas de portada, el cuerpo con los
fallos y, al final, el índice general. Cada página del cuerpo lleva un
encabezado con el número de página oficial y el número de tomo. En el Tomo 348,
medido con pdfplumber, el encabezado sale así en las primeras líneas del texto:

    página impar  (derecha):   "DE JUSTICIA DE LA NACIÓN  <n>"    y luego  "<tomo>"
    página par    (izquierda):  "<n>  FALLOS DE LA CORTE SUPREMA"  y luego  "<tomo>"

De ahí sale `pagina_oficial`. El offset del tomo es `pdf_page - pagina_oficial`,
constante en el cuerpo (medido: 6 en el Tomo 348). Las páginas sin encabezado
—portada, índice, blancas— quedan con `pagina_oficial = None`: no se inventa un
número (D-05). El formato del encabezado cambia entre décadas (riesgo R-2 del
plan); estas expresiones están calibradas contra el Tomo 348 y cada tomo que
las rompa entra como caso de regresión con su fixture.

`corpus/` no importa `index/` ni `embed/` (regla de dependencias del plan). El
único cruce es `persistir()`, que escribe por `db/repo.py`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pdfplumber

if TYPE_CHECKING:
    from spectre.db import Repo

# El número de página va al final de la línea en páginas impares y al principio
# en pares; en el medio, el nombre del cuerpo ("...NACIÓN" / "FALLOS DE LA
# CORTE SUPREMA"). Se toleran una o dos variantes de acento por el OCR/encoding.
_ENC_DERECHA = re.compile(
    r"DE\s+JUSTICIA\s+DE\s+LA\s+NACI[ÓO]N\s+(\d{1,4})\b",
    re.IGNORECASE,
)
_ENC_IZQUIERDA = re.compile(
    r"\b(\d{1,4})\s+FALLOS\s+DE\s+LA\s+CORTE\s+SUPREMA",
    re.IGNORECASE,
)

#: El encabezado vive en las primeras líneas del texto de la página.
_LINEAS_ENCABEZADO = 3

#: Un tomo no se acerca a esto; corta números disparatados de un falso positivo.
_MAX_PAGINA_OFICIAL = 5000


@dataclass(frozen=True, slots=True)
class PaginaTexto:
    """Una página del PDF: su texto crudo y el número oficial si se pudo leer."""

    pdf_page: int  # 1-based, como la numera el PDF
    texto: str  # texto tal cual sale del PDF, sin limpiar (eso es PR-05)
    pagina_oficial: int | None  # número impreso en el encabezado, o None


@dataclass(frozen=True, slots=True)
class ResultadoOffset:
    """Resumen de `pdf_page - pagina_oficial` sobre un tomo."""

    offset: int | None  # el valor dominante; None si no se detectó ninguna página
    total: int
    detectadas: int
    consistentes: int  # detectadas que respetan el offset dominante
    discrepancias: tuple[int, ...]  # pdf_page de las que no lo respetan

    @property
    def cobertura(self) -> float:
        return self.detectadas / self.total if self.total else 0.0

    @property
    def consistencia(self) -> float:
        return self.consistentes / self.detectadas if self.detectadas else 0.0


def detectar_pagina_oficial(texto: str) -> int | None:
    """El número de página oficial del encabezado, o None si no aparece."""
    cabecera = "\n".join(texto.splitlines()[:_LINEAS_ENCABEZADO])
    m = _ENC_DERECHA.search(cabecera) or _ENC_IZQUIERDA.search(cabecera)
    if m is None:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= _MAX_PAGINA_OFICIAL else None


def extraer_texto(pdf_path: Path | str) -> list[PaginaTexto]:
    """Texto por página del PDF, con el número oficial detectado en cada una.

    No toca la base. Lanza si el archivo no existe o el PDF no tiene páginas
    (nada de devolver una lista vacía como si hubiera andado)."""
    ruta = Path(pdf_path)
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe el PDF: {ruta}")

    paginas: list[PaginaTexto] = []
    with pdfplumber.open(ruta) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            texto = page.extract_text() or ""
            paginas.append(
                PaginaTexto(
                    pdf_page=i,
                    texto=texto,
                    pagina_oficial=detectar_pagina_oficial(texto),
                )
            )

    if not paginas:
        raise ValueError(f"el PDF no tiene páginas: {ruta}")
    return paginas


def calcular_offset(paginas: list[PaginaTexto]) -> ResultadoOffset:
    """Deduce el offset del tomo: la moda de `pdf_page - pagina_oficial` entre
    las páginas con número detectado, más cuántas lo respetan."""
    diffs = [
        p.pdf_page - p.pagina_oficial for p in paginas if p.pagina_oficial is not None
    ]
    total = len(paginas)
    if not diffs:
        return ResultadoOffset(None, total, 0, 0, ())

    offset = Counter(diffs).most_common(1)[0][0]
    consistentes = sum(1 for d in diffs if d == offset)
    discrepancias = tuple(
        p.pdf_page
        for p in paginas
        if p.pagina_oficial is not None and p.pdf_page - p.pagina_oficial != offset
    )
    return ResultadoOffset(offset, total, len(diffs), consistentes, discrepancias)


def persistir(
    repo: Repo,
    tomo_id: int,
    paginas: list[PaginaTexto],
    offset: ResultadoOffset,
) -> None:
    """Vuelca las páginas en la tabla `paginas` y actualiza el tomo
    (`paginas`, `offset_pagina`). Reemplaza lo que hubiera: reextraer un tomo
    no acumula filas."""
    repo.borrar_paginas(tomo_id)
    repo.insert_paginas(
        tomo_id,
        ((p.pdf_page, p.pagina_oficial, p.texto) for p in paginas),
    )
    repo.actualizar_tomo(tomo_id, paginas=len(paginas), offset_pagina=offset.offset)
