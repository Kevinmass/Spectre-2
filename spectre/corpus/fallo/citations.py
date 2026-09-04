"""Extracción de citas a precedentes: `Fallos: <tomo>:<página>`.

La Corte cita jurisprudencia propia con la forma `Fallos: 311:2478`. PR-10
detecta esas referencias en el texto de cada fallo y arma la relación
fallo citante → fallo citado (`tomo_citado`, `pagina_citada`), con un recorte
del texto alrededor (`contexto`). Es la materia prima del grafo de precedentes
(plan §8.3: ~887 citas por tomo).

**Formas cubiertas** (todas con casos reales de los tomos 348 y 349):

- simple: `Fallos: 311:2478`
- varias, un solo prefijo, separadas por `;`: `Fallos: 301:1149; 302:1078`
- otra página del mismo tomo tras `,` o `y`: `Fallos: 340:1084, 1093 y 1099`
- unión con `y` / `e` de un nuevo `tomo:página`: `Fallos: 300:1282 y 301:771`
- ruido tolerado entre medio: `Fallos: 340:1084, esp. p. 1090`
- cortada de renglón: `Fallos:\n312:\n1234` (se colapsan los blancos antes de leer)
- prefijos que no importan: `cf.`, `arg.`, `conf.`, `ver`, comillas, paréntesis

**Lo que NO toma** (D-05: no se inventa nada):

- el año entre paréntesis: `Fallos: 312:1234 (1989)` → solo `312:1234`
- lo que sigue a la cita: `Fallos: 348:145, considerando 5°` → solo `348:145`
- el formato viejo `t. 246, p. 345` (sin `Fallos:`): fuera de alcance de PR-10,
  se ancla siempre en la palabra `Fallos`.

`tomo_citado` se acota a 1–400 y `pagina_citada` a 1–8000 (los tomos
multi-volumen llevan paginación corrida de varios miles): un número fuera de
rango corta el falso positivo y no entra como cita.

No toca la base (regla de dependencias del plan). `extraer_citas` trabaja sobre
el texto de un fallo (el que arma `structure.texto_del_fallo`); el bucle por
tomo y el volcado a la tabla `citas` los hace el CLI / PR-19.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Ancla: la palabra `Fallos` seguida de `:`. Se exige el `:` — `Fallos 311:2478`
#: sin dos puntos es rarísimo y sin ancla firme entran falsos positivos. El
#: corte de renglón ya se colapsó a un espacio antes de buscar.
_ANCLA = re.compile(r"\bFallos\s*:\s*", re.IGNORECASE)

#: `<tomo>:<página>` con blancos tolerados alrededor de los `:`.
_TOMO_PAGINA = re.compile(r"(\d{1,3})\s*:\s*(\d{1,4})")

#: Separadores dentro de una lista de citas con un solo `Fallos:`.
_SEPARADOR = re.compile(r"\s*(?:;|,|(?:y|e)\b)\s*", re.IGNORECASE)

#: Ruido que puede colarse antes de un número de página en la continuación
#: (`, esp. p. 1090`, `y págs. 1099`, `, esp. págs.`). No es una cita en sí; se
#: consume uno o más de estos tokens seguidos.
_RELLENO = re.compile(r"(?:(?:esp(?:ecialmente)?|p[aá]gs?|ps?)\.?\s*)+", re.IGNORECASE)

#: Página suelta (continuación del último tomo tras `,` o `y`).
_PAGINA_SOLA = re.compile(r"(\d{1,4})")

_TOMO_MIN, _TOMO_MAX = 1, 400
#: Los tomos multi-volumen (327, 329, 330, ...) llevan paginación corrida y
#: pasan de 5.000 páginas; por eso el tope alto.
_PAGINA_MIN, _PAGINA_MAX = 1, 8000

#: Caracteres de contexto a cada lado de la cita (sobre el texto ya colapsado).
_MARGEN_CONTEXTO = 90


@dataclass(frozen=True, slots=True)
class CitaExtraida:
    """Una referencia `Fallos: <tomo>:<página>` hallada en un fallo. Mapea 1:1 a
    una fila de la tabla `citas` (`fallo_id` lo pone el pipeline, PR-19)."""

    tomo_citado: int
    pagina_citada: int
    contexto: str


def _en_rango(tomo: int, pagina: int) -> bool:
    return _TOMO_MIN <= tomo <= _TOMO_MAX and _PAGINA_MIN <= pagina <= _PAGINA_MAX


def _leer_lista(s: str, pos: int) -> tuple[list[tuple[int, int]], int]:
    """Desde `pos` (justo después de `Fallos:`), lee la lista de citas y devuelve
    los pares `(tomo, página)` y el índice donde la lista termina. Lista vacía si
    lo que sigue al ancla no es un `tomo:página` válido."""
    m = _TOMO_PAGINA.match(s, pos)
    if not m:
        return [], pos
    tomo, pagina = int(m.group(1)), int(m.group(2))
    if not _en_rango(tomo, pagina):
        return [], pos
    pares = [(tomo, pagina)]
    i = m.end()
    while (sep := _SEPARADOR.match(s, i)) is not None:
        j = sep.end()
        if (relleno := _RELLENO.match(s, j)) is not None:
            j = relleno.end()
        par = _TOMO_PAGINA.match(s, j)
        if par is not None:
            t2, p2 = int(par.group(1)), int(par.group(2))
            if not _en_rango(t2, p2):
                break
            pares.append((t2, p2))
            tomo = t2
            i = par.end()
            continue
        # una página suelta continúa el último tomo, pero solo tras `,` o `y`
        # (un `;` sin `tomo:` es raro y más vale cortar que inventar).
        suelta = _PAGINA_SOLA.match(s, j)
        if (
            suelta is not None
            and not sep.group(0).strip().startswith(";")
            and _PAGINA_MIN <= int(suelta.group(1)) <= _PAGINA_MAX
        ):
            pares.append((tomo, int(suelta.group(1))))
            i = suelta.end()
            continue
        break
    return pares, i


def _contexto(s: str, inicio: int, fin: int) -> str:
    desde = max(0, inicio - _MARGEN_CONTEXTO)
    hasta = min(len(s), fin + _MARGEN_CONTEXTO)
    recorte = s[desde:hasta].strip()
    if desde > 0:
        recorte = "..." + recorte
    if hasta < len(s):
        recorte = recorte + "..."
    return recorte


def _colapsar(texto: str) -> str:
    """Todo el fallo en una línea: una cita puede venir cortada de renglón
    (`Fallos:\\n312:\\n1234`) y el escaneo trabaja sobre texto continuo."""
    return re.sub(r"\s+", " ", texto)


def _sitios(s: str) -> list[tuple[list[tuple[int, int]], int, int]]:
    """Sobre texto ya colapsado: cada `Fallos:` seguido de al menos un
    `<tomo>:<página>` válido, como `(pares, inicio_del_ancla, fin_de_la_lista)`."""
    sitios: list[tuple[list[tuple[int, int]], int, int]] = []
    for ancla in _ANCLA.finditer(s):
        pares, fin = _leer_lista(s, ancla.end())
        if pares:
            sitios.append((pares, ancla.start(), fin))
    return sitios


def extraer_citas(texto: str) -> list[CitaExtraida]:
    """Las citas a precedentes del texto de un fallo, en orden de aparición: **una
    `CitaExtraida` por fallo citado**. Una cadena con un solo prefijo
    (`Fallos: 301:1149; 302:1078`) cita dos precedentes → dos filas, que es lo que
    la tabla `citas` y el grafo de precedentes necesitan. Una cita repetida da
    varias filas, con su contexto propio (la tabla no deduplica)."""
    s = _colapsar(texto)
    citas: list[CitaExtraida] = []
    for pares, inicio, fin in _sitios(s):
        contexto = _contexto(s, inicio, fin)
        citas.extend(CitaExtraida(tomo, pagina, contexto) for tomo, pagina in pares)
    return citas


def contar_referencias(texto: str) -> int:
    """Cuántas veces el fallo escribe `Fallos: <tomo>:<página>...` (una cadena de
    varios precedentes con un solo prefijo cuenta **una**). Es la métrica del
    criterio de aceptación del plan (§6 PR-10: 887 en el Tomo 348); `extraer_citas`
    devuelve más, porque expande cada cadena a sus precedentes."""
    return len(_sitios(_colapsar(texto)))
