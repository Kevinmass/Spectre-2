"""Catálogo de tomos de la colección Fallos (D-9 del plan): qué tomos existen.

**Spike de este PR** (antes de escribir nada más): confirmar cómo se obtiene
el PDF de un tomo. El listado se ve por primera vez en
`https://sjservicios.csjn.gov.ar/sj/tomosFallos.do?method=iniciar` (GET), pero
pagina por `POST /sj/tomosFallos` (sin `.do`, la acción real del `<form>`) —
HTML plano (5 páginas de hasta 90 filas cada una al momento de escribir
esto), sin API ni JSON. Cada fila trae la etiqueta de volumen ("349-I",
"216", ...), el año y un link `verTomo?tomoId=N`. Verificado con un `HEAD`
real a ese link:
`content-type: application/pdf`, `content-disposition: attachment; filename=
LibroVolNNN-M.pdf` — **entrega el PDF directo**, sin paso intermedio. Eso
resuelve el riesgo R-1/R-3 del plan: sí hay descarga programática, y la
implementa PR-17 (`download.py`) sobre esto.

Dos hallazgos del spike que no se resuelven en este PR (solo se documentan;
persistir el catálogo es de PR-17 en adelante, ver bitácora PR-16):

1. **Un `numero` de tomo puede tener más de un volumen físico** (`347-I` y
   `347-II` son dos filas distintas, mismo `numero=347`). El esquema actual
   (`tomos.numero UNIQUE`, migración 0001) no lo contempla.
2. **El "año" no siempre es un año único.** Los tomos más viejos (hasta
   ~1917) lo publican como rango (`"1898/1899"`), no un entero — por eso
   `EntradaCatalogo.anio` es `str`, no `int`.

Este módulo no persiste nada, igual que `corpus/pdf` y `corpus/fallo`:
`listar_catalogo()` devuelve la lista en memoria.
"""

from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

# Sin ".do": esa es la página inicial (GET, `?method=iniciar`); el `<form
# action="/sj/tomosFallos" method="post">` que pagina apunta acá.
_URL_LISTADO = "https://sjservicios.csjn.gov.ar/sj/tomosFallos"
_TIMEOUT = 30
_AGENTE = (
    "Mozilla/5.0 (compatible; Spectre/0.0; +https://github.com/Kevinmass/Spectre-2)"
)

# Una fila: <div ...lg-col-span-4...><span>ETIQUETA</span></div>
#           <div ...lg-col-span-3...><span>AÑO</span></div> ... (columna vacía)
#           ... href="/sj/verTomo?tomoId=N"
_FILA = re.compile(
    r"lg-col-span-4[^>]*>\s*<span>\s*(?P<etiqueta>[^<]+?)\s*</span>.*?"
    r"lg-col-span-3[^>]*>\s*<span>\s*(?P<anio>\d{4}(?:/\d{4})?)\s*</span>.*?"
    r'href="/sj/verTomo\?tomoId=(?P<tomo_id>\d+)"',
    re.DOTALL,
)
_PAGINACION = re.compile(r"gina&nbsp;<span>(\d+)</span> de <span>(\d+)</span>")


@dataclass(frozen=True, slots=True)
class EntradaCatalogo:
    """Una fila del catálogo: un volumen físico. `numero` no identifica la
    fila (`347-I` y `347-II` comparten `numero=347`, ver el hallazgo 1 de
    arriba); `csjn_tomo_id` sí es único por fila."""

    numero: int
    volumen: str | None
    anio: str
    csjn_tomo_id: str


def _parsear_etiqueta(etiqueta: str) -> tuple[int, str | None]:
    """`"349-I"` -> `(349, "I")`; `"216"` -> `(216, None)`."""
    numero, _, volumen = etiqueta.partition("-")
    return int(numero.strip()), (volumen.strip() or None)


def parsear_pagina(html: str) -> tuple[list[EntradaCatalogo], int, int]:
    """Las entradas de una página + `(página actual, total de páginas)`.

    Función pura (sin red): la usa `listar_catalogo` y también los tests,
    contra un recorte real guardado en `tests/fixtures/`.
    """
    entradas = []
    for m in _FILA.finditer(html):
        numero, volumen = _parsear_etiqueta(m.group("etiqueta"))
        entradas.append(
            EntradaCatalogo(numero, volumen, m.group("anio"), m.group("tomo_id"))
        )
    pag = _PAGINACION.search(html)
    if pag is None:
        raise ValueError("no se encontró el indicador de paginación en la página")
    return entradas, int(pag.group(1)), int(pag.group(2))


def _pedir_pagina(desde_pagina: int) -> str:
    datos = urlencode({"desdePagina": desde_pagina}).encode()
    req = urllib.request.Request(
        _URL_LISTADO,
        data=datos,
        # El `Accept` no es opcional: sin él el servidor responde 405 (no es
        # que el método esté mal — `curl` con los mismos verbo/body/User-Agent
        # anda, pero sin `Accept` explícito no).
        headers={
            "User-Agent": _AGENTE,
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def listar_catalogo(
    *, pedir_pagina: Callable[[int], str] = _pedir_pagina
) -> list[EntradaCatalogo]:
    """Todo el catálogo (349 números de tomo, algunos con más de un volumen):
    pagina hasta que el sitio dice que no hay más páginas. Hace una llamada de
    red por página del listado (5 al momento de escribir esto). `pedir_pagina`
    es un punto de inyección para los tests: sin pasarlo, pega contra el sitio
    real."""
    entradas: list[EntradaCatalogo] = []
    pagina = 1
    total_paginas = 1
    while pagina <= total_paginas:
        html = pedir_pagina(pagina)
        de_esta_pagina, _pagina_actual, total_paginas = parsear_pagina(html)
        entradas.extend(de_esta_pagina)
        pagina += 1
    return entradas
