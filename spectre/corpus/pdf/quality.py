"""Sonda de calidad del tomo (D-10 del plan): ¿tiene capa de texto o es un
escaneo sin OCR?

Un PDF digital (nativo o con OCR) devuelve, por `pdfplumber`, el texto real de
cada página. Un escaneo sin OCR no tiene capa de texto en absoluto:
`page.extract_text()` da `""` (o casi) en prácticamente todas las páginas,
aunque el PDF "se vea" igual que uno digital. Medido sobre el Tomo 348 (968
páginas, digital): mediana 2.335 caracteres/página, solo 6 páginas (0,6%) por
debajo de 200 caracteres —las de portada e índice—. Un escaneo sin OCR da 0 en
prácticamente el 100% de las páginas: la brecha entre ambos casos es enorme,
así que el umbral no necesita ser fino.

No hay todavía, en esta sesión, un tomo real anterior a 1950 para calibrar
contra un escaneo genuino (spike de red bloqueado: sin acceso a
`sjservicios.csjn.gov.ar` desde esta máquina). El caso "requiere_ocr" se
prueba con una lista de `PaginaTexto` fabricada a mano que reproduce la forma
exacta de un escaneo (texto vacío o casi en todas las páginas) — ver
`tests/test_quality.py`. Verificar contra un tomo real queda pendiente para
cuando haya red: `spectre csjn catalog` para encontrar uno de antes de 1950,
`spectre csjn download <tomo_id> data/tomos/<N>.pdf` y después `spectre pdf
quality data/tomos/<N>.pdf`.

Como el resto de `corpus/pdf`, este módulo **mide, no persiste** (llenar
`tomos.calidad` es tarea del pipeline de PR-19); `corpus/` no importa `index/`
ni `embed/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spectre.corpus.pdf.extract import PaginaTexto

#: Una página de cuerpo real tiene miles de caracteres; un escaneo sin OCR da
#: 0. 200 dista de ambos por un margen amplio (ni la portada del Tomo 348, con
#: 0 caracteres, ni su página más corta de cuerpo se acercan a la mitad).
_UMBRAL_CARACTERES = 200

#: Si menos de la mitad de las páginas superan el umbral, el tomo es un
#: escaneo: no alcanza con que UNA página falle (eso ya pasa en tomos
#: digitales, por portada/índice), tiene que fallar la mayoría.
_COBERTURA_MINIMA = 0.5


@dataclass(frozen=True, slots=True)
class ResultadoCalidad:
    """Resumen de la sonda de calidad sobre un tomo."""

    calidad: str  # 'digital' | 'requiere_ocr'
    total: int
    con_texto: int  # páginas con >= _UMBRAL_CARACTERES caracteres
    caracteres_totales: int

    @property
    def cobertura(self) -> float:
        return self.con_texto / self.total if self.total else 0.0

    @property
    def caracteres_por_pagina(self) -> float:
        return self.caracteres_totales / self.total if self.total else 0.0


def medir_calidad(paginas: list[PaginaTexto]) -> ResultadoCalidad:
    """Clasifica el tomo en `digital` o `requiere_ocr` a partir del texto
    crudo por página (el que da `extraer_texto`, antes de `limpiar`).

    D-05: no hay un tercer resultado "no sé" que se trate como éxito. Un tomo
    sin páginas es un error de `extraer_texto`, no algo que este módulo tenga
    que contemplar."""
    total = len(paginas)
    if total == 0:
        raise ValueError("no se puede medir la calidad de un tomo sin páginas")

    caracteres = [len(p.texto.strip()) for p in paginas]
    con_texto = sum(1 for c in caracteres if c >= _UMBRAL_CARACTERES)
    caracteres_totales = sum(caracteres)
    cobertura = con_texto / total

    calidad = "digital" if cobertura >= _COBERTURA_MINIMA else "requiere_ocr"
    return ResultadoCalidad(calidad, total, con_texto, caracteres_totales)
