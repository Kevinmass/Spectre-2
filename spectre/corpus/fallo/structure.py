"""Metadatos de un fallo: fecha, jueces firmantes, tipo de recurso, tribunal de
origen y partes.

El texto de un fallo se arma concatenando las páginas de su rango (PR-07) más la
página donde arranca el siguiente —el pie de un fallo y la carátula del que
sigue comparten página—, cortando en esa carátula. Sobre ese texto:

- **fecha**: la última `Buenos Aires, <día> de <mes> de <año>` (la de la Corte
  viene después del dictamen del Procurador). Si el fallo remite al dictamen y
  no imprime su propia sentencia, la fecha está en la nota
  `(*) Sentencia del <día> de <mes> de <año>. Ver fallo.`.
- **jueces**: tras una fórmula de cierre (`Notifíquese`, `Archívese`,
  `devuélvase`, ...), la línea —a veces partida en dos— con los nombres unidos
  por `—`, terminada en punto. Se quitan las aclaraciones `(según su voto)` /
  `(en disidencia)`. Cada nombre se normaliza a Capitalizado (el PDF los trae en
  versalita, y el Tomo 349 con el apellido en minúscula).
- **tipo de recurso**: la línea `Recurso ... interpuesto/deducido por ...` o
  `Vistos los autos: "Recurso de hecho ..."`.
- **tribunal de origen**: la línea `Tribunal de origen: ...` (puede seguir en la
  línea siguiente hasta el punto).
- **partes**: de la carátula, partida en `c/` (actor / demandado). Una carátula
  `... s/ ...` sin `c/` tiene una sola parte.

**Nada se inventa** (D-05): lo que no se encuentra queda en `None` / `()` y se
cuenta como faltante. El criterio de aceptación (plan §6) es ≥90% de los fallos
con fecha y jueces; el resto queda marcado.

No toca la base. Usa `es_versalita` / `limpiar` de `corpus/pdf/clean` y
`_linea_es_caratula` de `segmenter`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from spectre.corpus.fallo.segmenter import _linea_es_caratula
from spectre.corpus.pdf.clean import limpiar

if TYPE_CHECKING:
    from spectre.corpus.pdf.extract import PaginaTexto

_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_FECHA_CORTE = re.compile(
    r"Buenos Aires,?\s+(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", re.IGNORECASE
)
_FECHA_NOTA = re.compile(
    r"Sentencia del\s+(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", re.IGNORECASE
)

#: Fórmulas con las que cierra la parte dispositiva, justo antes de las firmas.
_CIERRE = re.compile(
    r"\b(?:Notif[ií]quese|Arch[ií]vese|c[uú]mplase|devu[eé]lv\w+|Reg[ií]strese|"
    r"rem[ií]tase|H[aá]gase saber|comun[ií]quese|Publ[ií]quese|"
    r"protocol[ií]cese)\b",
    re.IGNORECASE,
)
_ACLARACION = re.compile(r"\([^)]*\)")

#: `—` (em dash) separa los jueces firmantes. Ojo: `–` (en dash) es otra cosa
#: (`Estado Nacional – Ministerio de Defensa` en una carátula).
_EMDASH = "—"
#: Línea de firmas: arranca con mayúscula, tiene em dash y ni un dígito.
_LINEA_FIRMAS = re.compile(rf"^[A-ZÁÉÍÓÚÑ][^\d\n]*{_EMDASH}[^\d\n]*$")
#: Firma de un solo juez (jurisdicción originaria): `Horacio Rosatti.`
_NOMBRE_SOLO = re.compile(
    r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3}\.?$"
)
_TRIBUNAL_ORIGEN = re.compile(r"Tribunal de origen:\s*(.+)", re.IGNORECASE)
_TIPO_RECURSO = re.compile(
    r"\b(Recurso\s+(?:extraordinario|ordinario|de\s+queja|de\s+hecho|"
    r"de\s+casaci[oó]n|de\s+reposici[oó]n|directo|de\s+apelaci[oó]n))\b",
    re.IGNORECASE,
)
_PALABRA_NOMBRE = re.compile(r"[^\W\d_]+", re.UNICODE)
#: Un fragmento entre em dashes no es un nombre si arranca con una de estas o
#: contiene una palabra de "prosa" (corta el falso positivo de una frase con —).
_NO_ES_NOMBRE_INICIAL = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "de",
    "del",
    "por",
    "que",
    "con",
    "y",
    "en",
    "a",
    "o",
    "al",
    "su",
    "segun",
    "según",
    "este",
    "esta",
    "no",
}
_PROSA = {
    "sentencia",
    "corte",
    "voto",
    "recurso",
    "fallo",
    "considerando",
    "tribunal",
    "queja",
    "costas",
    "disidencia",
    "dictamen",
}


@dataclass(frozen=True, slots=True)
class MetadatosFallo:
    """Lo que se pudo leer del texto del fallo. `None` / `()` = no encontrado."""

    fecha: str | None  # ISO "2025-02-06"
    jueces: tuple[str, ...]
    tipo_recurso: str | None
    tribunal_origen: str | None
    actor: str | None
    demandado: str | None


def _iso(dia: str, mes: str, anio: str) -> str | None:
    n = _MESES.get(mes.lower())
    if n is None:
        return None
    return f"{int(anio):04d}-{n:02d}-{int(dia):02d}"


def _fecha(texto: str) -> str | None:
    corte = _FECHA_CORTE.findall(texto)
    if corte:
        return _iso(*corte[-1])
    nota = _FECHA_NOTA.findall(texto)
    if nota:
        return _iso(*nota[-1])
    return None


def _capitalizar_nombre(fragmento: str) -> str:
    palabras = fragmento.split()
    return " ".join(
        w if w.lower() in ("de", "del", "la", "y") else w.capitalize() for w in palabras
    )


def _jueces(texto: str) -> tuple[str, ...]:
    lineas = [ln.strip() for ln in texto.splitlines()]
    # 1) la línea de firmas con em dash — no siempre viene una fórmula de cierre
    #    justo antes (a veces la dispositiva termina en "... a los fines que
    #    hubiere lugar."), así que se busca la línea por su forma.
    for j, linea in enumerate(lineas):
        if _EMDASH not in linea or not _LINEA_FIRMAS.match(linea):
            continue
        bloque = linea
        for k in range(j + 1, min(j + 3, len(lineas))):
            if not lineas[k]:
                break
            bloque += " " + lineas[k]
            if lineas[k].endswith("."):
                break
        firmas = _partir_firmas(bloque)
        if len(firmas) >= 2:
            return firmas
    # 2) firma de un solo juez, tras una fórmula de cierre
    for i, linea in enumerate(lineas):
        if not _CIERRE.search(linea):
            continue
        for k in range(i + 1, min(i + 4, len(lineas))):
            if _NOMBRE_SOLO.match(lineas[k]):
                firmas = _partir_firmas(lineas[k])
                if firmas:
                    return firmas
    return ()


def _partir_firmas(bloque: str) -> tuple[str, ...]:
    bloque = _ACLARACION.sub("", bloque).split(".")[0]
    nombres = []
    for parte in bloque.split(_EMDASH):
        palabras = _PALABRA_NOMBRE.findall(parte)
        if not 2 <= len(palabras) <= 5:
            continue
        bajas = [p.lower() for p in palabras]
        if bajas[0] in _NO_ES_NOMBRE_INICIAL or _PROSA.intersection(bajas):
            continue
        nombres.append(_capitalizar_nombre(" ".join(palabras)))
    return tuple(nombres)


def _tribunal_origen(texto: str) -> str | None:
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        m = _TRIBUNAL_ORIGEN.search(linea)
        if not m:
            continue
        valor = m.group(1).strip()
        if not valor.endswith(".") and i + 1 < len(lineas):
            valor += " " + lineas[i + 1].strip()
        return valor.split(".")[0].strip() or None
    return None


def _tipo_recurso(texto: str, caratula: str) -> str | None:
    for linea in texto.splitlines():
        if re.search(r"(?:interpuest\w|deducid\w)\s+por", linea, re.IGNORECASE):
            m = _TIPO_RECURSO.search(linea)
            if m:
                return " ".join(m.group(1).split()).lower()
    m = _TIPO_RECURSO.search(texto)
    if m:
        return " ".join(m.group(1).split()).lower()
    if re.search(
        r"incidente de (?:in)?competencia|cuesti[oó]n de competencia",
        caratula,
        re.IGNORECASE,
    ):
        return "competencia"
    return None


def _partes(caratula: str) -> tuple[str | None, str | None]:
    m = re.search(r"\s+c/\s+", caratula, re.IGNORECASE)
    if not m:
        actor = re.split(r"\s+s/\s+", caratula, maxsplit=1, flags=re.IGNORECASE)[0]
        return (actor.strip() or None, None)
    actor = caratula[: m.start()].strip()
    resto = caratula[m.end() :]
    demandado = re.split(r"\s+s/\s+", resto, maxsplit=1, flags=re.IGNORECASE)[0]
    return (actor or None, demandado.strip() or None)


def extraer_metadatos(texto: str, *, caratula: str) -> MetadatosFallo:
    """Los metadatos que se puedan leer del texto del fallo y su carátula."""
    actor, demandado = _partes(caratula)
    return MetadatosFallo(
        fecha=_fecha(texto),
        jueces=_jueces(texto),
        tipo_recurso=_tipo_recurso(texto, caratula),
        tribunal_origen=_tribunal_origen(texto),
        actor=actor,
        demandado=demandado,
    )


def texto_del_fallo_paginado(
    paginas_por_oficial: dict[int, PaginaTexto],
    *,
    pagina_inicio: int,
    pagina_inicio_siguiente: int | None,
    pagina_fin_cuerpo: int,
) -> list[tuple[int, str]]:
    """El texto limpio del fallo troceado por página oficial: `[(oficial, texto),
    ...]` en orden. `"\\n".join(t for _, t in ...)` reproduce `texto_del_fallo`
    exactamente; el trozo por página es lo que necesita el chunker (PR-11) para
    heredar `pagina_oficial`."""
    fin = pagina_inicio_siguiente if pagina_inicio_siguiente else pagina_fin_cuerpo
    paginado: list[tuple[int, str]] = []
    for oficial in range(pagina_inicio, fin + 1):
        pagina = paginas_por_oficial.get(oficial)
        if pagina is None:
            continue
        # el corte en la carátula del fallo siguiente se busca sobre el texto
        # crudo: `limpiar` normaliza las versalitas y la carátula deja de
        # reconocerse. Recién después se limpia lo que se conserva.
        crudo = pagina.texto
        if oficial == pagina_inicio_siguiente:
            lineas = crudo.splitlines()
            corte = next(
                (i for i, ln in enumerate(lineas) if i and _linea_es_caratula(ln)),
                len(lineas),
            )
            conservado = lineas[:corte]
            # la nota "(*) Sentencia del <fecha>. Ver fallo." va al pie de la
            # página, después de la carátula del siguiente, pero es de este fallo.
            nota = next((ln for ln in lineas[corte:] if _FECHA_NOTA.search(ln)), None)
            if nota is not None:
                conservado.append(nota)
            crudo = "\n".join(conservado)
        paginado.append((oficial, limpiar(crudo)))
    return paginado


def texto_del_fallo(
    paginas_por_oficial: dict[int, PaginaTexto],
    *,
    pagina_inicio: int,
    pagina_inicio_siguiente: int | None,
    pagina_fin_cuerpo: int,
) -> str:
    """Texto limpio del fallo: sus páginas más la de arranque del siguiente
    (comparten el pie), cortada en la próxima carátula."""
    return "\n".join(
        texto
        for _, texto in texto_del_fallo_paginado(
            paginas_por_oficial,
            pagina_inicio=pagina_inicio,
            pagina_inicio_siguiente=pagina_inicio_siguiente,
            pagina_fin_cuerpo=pagina_fin_cuerpo,
        )
    )
