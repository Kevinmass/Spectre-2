"""Parser del índice por nombres de las partes de un tomo de Fallos.

Al final de cada volumen, antes del índice general por meses, va el
**ÍNDICE POR LOS NOMBRES DE LAS PARTES**: una lista alfabética que mapea cada
carátula a la página oficial donde arranca el fallo
(`"Zárate, Pablo Federico y otros c/ ENRE s/ diferencias de salarios: p. 380"`).
Es el plan A de la segmentación (decisión D-2 del plan): el plan B —delimitar
por texto— sobre-parte.

Cómo se lee, medido sobre el Tomo 348:

- La sección son las páginas `pdf_page` 963–967. `localizar_indice_partes` la
  encuentra buscando desde el final del PDF la marca `NOMBRES DE LAS PARTES`
  (está en el encabezado de todas sus páginas) y frenando en la primera página
  hacia atrás que ya no la tiene. Si no aparece en ningún lado, **falla
  ruidosamente** (D-05): no se inventa un índice vacío.
- Cada página va a **dos columnas**. `page.extract_text()` plano las intercala
  renglón con renglón y es inservible; se recorta la página en dos mitades por
  el centro (`page.width / 2`) y se extrae cada una por separado. El corte por
  el centro está calibrado contra el Tomo 348 (riesgo R-2): otro tomo con la
  caja corrida entra como caso de regresión con su fixture.
- Dentro de una columna, una entrada es una o más líneas de carátula que
  terminan en `: p. NNN` (o `: ps. N y M`, `: ps. N, M y P` para las partes que
  aparecen en varios fallos). El número de página puede quedar en el renglón
  siguiente (`... perjuicios: p.\n274`) y la cola `y 955` de una lista larga
  también. Se descartan las letras divisoras del abecedario (`A`, `N R`) y los
  fragmentos del encabezado partidos por el corte de columna.

Este módulo no toca la base (regla de dependencias del plan). Devuelve las
entradas crudas; construir las filas de `fallos` con su cita y su rango de
páginas es PR-07.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

#: Marca del encabezado (running header) de toda página del índice de partes.
#: Va en la primera línea; se mira solo la cabeza porque el índice general
#: termina con una entrada de tabla de contenidos "Indice por los nombres de
#: las partes (i)" que si no daría un falso positivo.
_MARCA_PARTES = "NOMBRES DE LAS PARTES"
_LINEAS_CABECERA = 2

#: Palabras del título del índice, para descartar el encabezado partido por el
#: corte de columna (`E LAS PARTES (i)`, `INDICE POR LOS NOM`, `(ii) NOMBRES DE`).
_ENCABEZADO = re.compile(r"NOMBRES|MBRES|[IÍ]NDICE|PARTES", re.IGNORECASE)

#: El encabezado vive en las primeras líneas útiles de cada columna, nunca más
#: abajo. Limitar el filtro evita comerse una carátula que mencione "partes".
_MAX_LINEAS_ENCABEZADO = 2

#: Línea que es solo una o dos letras: divisor alfabético del índice.
_DIVISOR = re.compile(r"[A-ZÑ](?:\s+[A-ZÑ])*\Z")

#: `: p. 380` | `: ps. 443 y 494` | `: ps. 569, 841 y 955` | `: ps.43 y 45`
_REF = re.compile(r"\bps?\.\s*(\d+(?:\s*(?:,|y)\s*\d+)*)")

#: Línea que es solo números (con `y` / `,`): cola de una lista de páginas larga
#: que se cortó de renglón (`... ps. 569, 841` \n `y 955`).
_SOLO_PAGINAS = re.compile(r"(?:y\s+|,\s*)?\d+(?:\s*(?:,|y)\s*\d+)*\Z")


@dataclass(frozen=True, slots=True)
class EntradaIndice:
    """Una línea del índice: una carátula y la página (o páginas) donde arranca
    el o los fallos de esas partes."""

    caratula: str
    paginas: tuple[int, ...]

    def _con_paginas(self, extra: list[int]) -> EntradaIndice:
        return EntradaIndice(self.caratula, self.paginas + tuple(extra))


@dataclass(frozen=True, slots=True)
class ResumenIndice:
    """Lo que mide el criterio de aceptación de PR-06.

    El rango de página oficial del tomo (D-2: "de la página 1 a la 953") se
    chequea contra ese número; acá no está la paginación oficial (eso es PR-04),
    así que `paginas_citadas` se reporta cruda y quien mide compara.
    """

    paginas_indice: tuple[int, int]  # pdf_page 1-based, inicio y fin inclusive
    entradas: tuple[EntradaIndice, ...]

    @property
    def caratulas(self) -> int:
        return len(self.entradas)

    @property
    def referencias(self) -> int:
        return sum(len(e.paginas) for e in self.entradas)

    @property
    def paginas_citadas(self) -> tuple[int, ...]:
        return tuple(sorted(p for e in self.entradas for p in e.paginas))


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def _numeros(texto: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", texto)]


def _es_pagina_indice_partes(texto: str) -> bool:
    cabeza = _sin_acentos("\n".join(texto.splitlines()[:_LINEAS_CABECERA]).upper())
    return _MARCA_PARTES in cabeza


def localizar_indice_partes(pdf: pdfplumber.PDF) -> range:
    """Índices de página (0-based) de la sección 'ÍNDICE POR LOS NOMBRES DE LAS
    PARTES', buscando desde el final. Lanza `ValueError` si no está."""
    fin: int | None = None
    ini: int | None = None
    for i in range(len(pdf.pages) - 1, -1, -1):
        if _es_pagina_indice_partes(pdf.pages[i].extract_text() or ""):
            fin = i if fin is None else fin
            ini = i
        elif fin is not None:
            break
    if fin is None or ini is None:
        raise ValueError(
            "no se encontró el índice por nombres de las partes: ninguna página "
            f"con {_MARCA_PARTES!r}"
        )
    return range(ini, fin + 1)


def _parsear_columna(lineas: list[str]) -> list[EntradaIndice]:
    """Entradas de una columna. Trabaja sobre su propia lista: una entrada nunca
    se continúa de una columna a la siguiente (no pasa en el Tomo 348)."""
    entradas: list[EntradaIndice] = []
    buffer: list[str] = []
    pos = 0
    for cruda in lineas:
        linea = cruda.strip()
        if not linea:
            continue
        pos += 1
        if pos <= _MAX_LINEAS_ENCABEZADO and _ENCABEZADO.search(linea):
            continue
        if _DIVISOR.fullmatch(linea):
            continue
        if not buffer and entradas and _SOLO_PAGINAS.fullmatch(linea):
            entradas[-1] = entradas[-1]._con_paginas(_numeros(linea))
            continue
        buffer.append(linea)
        unido = " ".join(buffer)
        refs = list(_REF.finditer(unido))
        if not refs:
            continue
        caratula = unido[: refs[0].start()].strip().rstrip(":").strip()
        paginas = tuple(n for r in refs for n in _numeros(r.group(1)))
        resto = unido[refs[-1].end() :].strip()
        if caratula:
            entradas.append(EntradaIndice(caratula, paginas))
        buffer = [resto] if resto else []
    return entradas


def _recolectar(pdf: pdfplumber.PDF) -> tuple[range, list[EntradaIndice]]:
    rango = localizar_indice_partes(pdf)
    entradas: list[EntradaIndice] = []
    for i in rango:
        page = pdf.pages[i]
        centro = page.width / 2
        for x0, x1 in ((0, centro), (centro, page.width)):
            columna = page.crop((x0, 0, x1, page.height)).extract_text() or ""
            entradas.extend(_parsear_columna(columna.splitlines()))
    return rango, entradas


def analizar_indice(pdf_path: Path | str) -> ResumenIndice:
    """Parsea el índice y devuelve el resumen con los números de aceptación.
    Lanza si el archivo no existe o si el índice no produjo ninguna entrada
    (nada de devolver una lista vacía como si hubiera andado)."""
    ruta = Path(pdf_path)
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe el PDF: {ruta}")
    with pdfplumber.open(ruta) as pdf:
        rango, entradas = _recolectar(pdf)
    if not entradas:
        raise ValueError(
            f"el índice por nombres de las partes de {ruta} no produjo entradas"
        )
    return ResumenIndice(
        paginas_indice=(rango.start + 1, rango.stop),
        entradas=tuple(entradas),
    )


def parsear_indice(pdf_path: Path | str) -> list[EntradaIndice]:
    """Las entradas del índice por nombres de las partes: carátula → página(s).
    La API para PR-07 y el pipeline."""
    return list(analizar_indice(pdf_path).entradas)
