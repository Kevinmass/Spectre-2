"""Parte un fallo en secciones: dictamen, mayoría, votos y disidencias.

Regla D-4 del plan: un chunk nunca puede cruzar el borde entre la mayoría, un
voto concurrente y una disidencia — devolver una disidencia como doctrina de la
Corte es un riesgo profesional. PR-09 marca esos bordes; PR-11 fragmenta dentro
de cada sección.

Estructura de un fallo de Fallos (verificado en los tomos 348 y 349):

1. **Sumarios**: párrafos de doctrina encabezados por un título en MAYÚSCULAS
   (`COMERCIALIZACION DE ESTUPEFACIENTES`, `PENA`). Cada uno puede terminar con
   una etiqueta `(Voto del juez X)` / `(Disidencia de los jueces X y Y)` que dice
   a qué opinión resume; sin etiqueta, es de la mayoría. Se **atribuyen**: cada
   párrafo va al texto de la sección que le corresponde.
2. **Dictamen** de la Procuración General (`Dictamen de la Procuración General` /
   `Suprema Corte:`), si se reproduce.
3. **Mayoría**: `FALLO DE LA CORTE SUPREMA` + `Vistos` + `Considerando:`.
4. **Votos** y **disidencias**: `voto Del Señor <cargo> Doctor don <nombre>` /
   `Disidencia Del Señor ...`, cada uno seguido de `Considerando:`. El nombre
   puede seguir en la línea de abajo; dos jueces pueden firmar una sola sección
   (`... don Horacio Rosatti y del Señor Ministro Doctor don Ricardo Lorenzetti`).

Las menciones inline (`voto del juez Fayt, considerando 10`, `disidencia de los
jueces Lorenzetti y Zaffaroni). En tales condiciones`) **no** son encabezados: se
descartan por traer dígitos, `;` o `)`.

Ningún texto de contenido queda huérfano: cada línea del fallo que no sea un
marcador estructural cae en exactamente una sección. Si el fallo no trae ningún
encabezado (sumario-only, "Ver fallo"), es una sola sección `mayoria`.

No toca la base.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CARGOS = r"(?:Presidente|Vicepresidente|Ministr[oa]|juez|jueza|conjuez|conjueza)"

#: Encabezado de voto/disidencia. Arranca la línea; sin dígitos ni `;` ni `)`
#: (eso lo tiene una cita inline, no un encabezado).
_H_OPINION = re.compile(
    rf"^\s*(voto|disidencia)\s+(?:parcial\s+)?"
    rf"(?:del?|de\s+la|de\s+los)\s+(?:se[ñn]ora?|{_CARGOS}|jueces)\b",
    re.IGNORECASE,
)
_H_FALLO = re.compile(r"^\s*FALLO DE LA CORTE SUPREMA\s*$", re.IGNORECASE)
_H_DICTAMEN = re.compile(
    r"^\s*Dictamen de la Procuraci[oó]n General\s*$", re.IGNORECASE
)

#: Cierra el bloque de encabezado y empieza el cuerpo de la opinión.
_INICIO_CUERPO = re.compile(
    r"^\s*(Considerando\s*:|Autos y [Vv]istos|Resulta\s*:|Vistos\b|1[°º]\s*\))"
)

#: Separa por `don` / `doña`: cada trozo posterior arranca con un nombre de juez
#: (un encabezado conjunto trae dos).
_DON = re.compile(r"\b(?:don|doña)\s+", re.IGNORECASE)
#: `de los jueces Rosenkrantz y Lorenzetti` (forma sin "Doctor don").
_DE_LOS_JUECES = re.compile(r"jueces?\s+(.+)", re.IGNORECASE)
#: Prefijo a sacar del autor de una etiqueta de sumario (`del juez X`, ...).
_PREFIJO_JUEZ = re.compile(
    r"^(?:del?|de\s+la|de\s+los)\s+(?:juez|jueces|jueza|conjuez|conjueces)\s+",
    re.IGNORECASE,
)
#: Palabras que cortan un nombre propio de juez (el nombre puede traer partes en
#: minúscula —`Manuel josé`, `Ricardo luis`— así que no se exige mayúscula).
_CORTE_NOMBRE = {
    "y",
    "e",
    "considerando",
    "resulta",
    "resultando",
    "autos",
    "vistos",
    "según",
    "segun",
    "del",
    "el",
    "los",
    "las",
    "un",
    "una",
    "que",
}

#: Título de sumario en MAYÚSCULAS (letras y espacios; sin minúsculas).
_HEADING_CAPS = re.compile(r"^[A-ZÑÁÉÍÓÚÜ][A-ZÑÁÉÍÓÚÜ ]{2,58}$")
#: Etiqueta al pie de un sumario: `(Voto del juez X)` / `(Disidencia de ...)`.
_TAG_SUMARIO = re.compile(r"\((Voto|Disidencia)\b([^)]*)\)", re.IGNORECASE)
_REMITE_DICTAMEN = re.compile(
    r"-\s*Del dictamen de la Procuraci[oó]n General al que", re.IGNORECASE
)

_ORDEN_TIPO = {"dictamen": 0, "mayoria": 1, "voto": 2, "disidencia": 3}


@dataclass(frozen=True, slots=True)
class SeccionFallo:
    """Un bloque del fallo con una sola voz. `autor` es `None` para la mayoría
    sin firmante nombrado y para el dictamen anónimo."""

    tipo: str  # "dictamen" | "mayoria" | "voto" | "disidencia"
    autor: str | None
    orden: int
    texto: str


@dataclass
class _Bloque:
    tipo: str
    autores: list[str]
    pos: int  # línea del encabezado; -1 si la sección nace de un sumario
    cuerpo_desde: int = -1
    cuerpo: str = ""
    sumarios: list[str] = field(default_factory=list)

    @property
    def autor(self) -> str | None:
        return ", ".join(self.autores) or None

    def texto(self) -> str:
        return "\n".join([*self.sumarios, self.cuerpo]).strip()


def _capitalizar(nombre: str) -> str:
    def cap(palabra: str) -> str:
        if palabra.lower() in ("de", "del", "la", "y", "e"):
            return palabra
        return "-".join(p.capitalize() for p in palabra.split("-"))

    return " ".join(cap(w) for w in nombre.split())


def _es_heading_caps(linea: str) -> bool:
    s = linea.strip()
    return bool(_HEADING_CAPS.match(s)) and not s.endswith(".")


def _nombre_desde(resto: str) -> str:
    """Las palabras que siguen a `don` / `doña`, hasta la primera que corta un
    nombre (`y`, `Autos`, `Considerando`, `:`, `(`, ...) o la 5ª."""
    palabras: list[str] = []
    for w in resto.split():
        if ":" in w or "(" in w:
            break
        wl = w.lower().strip(".,;:()")
        if not wl or wl in _CORTE_NOMBRE:
            break
        palabras.append(w.strip(".,;:"))
        if len(palabras) >= 5:
            break
    return _capitalizar(" ".join(palabras))


def _nombres_de_encabezado(bloque_lineas: list[str]) -> list[str]:
    texto = " ".join(bloque_lineas)
    autores = [n for p in _DON.split(texto)[1:] if (n := _nombre_desde(p))]
    if autores:
        return autores
    m = _DE_LOS_JUECES.search(texto)
    if m:
        crudo = re.split(r"\(|Considerando", m.group(1))[0]
        for parte in re.split(r"\s+y\s+|\s+e\s+|,", crudo):
            nombre = _capitalizar(parte.strip(" .,"))
            if nombre and nombre[0].isupper():
                autores.append(nombre)
    return autores


def _fin_de_encabezado(lineas: list[str], pos: int, tipo: str) -> int:
    """Índice de la primera línea de cuerpo tras el encabezado que arranca en
    `pos`. Un encabezado conjunto (`voto ... don X` / `voto ... don Y`) del mismo
    tipo se consume entero."""
    j = pos + 1
    while j < len(lineas) and j < pos + 8:
        linea = lineas[j]
        if _INICIO_CUERPO.match(linea):
            return j + 1
        if _es_heading_caps(linea):
            return j
        m = _H_OPINION.match(linea)
        if m and not re.search(r"[\d;)]", linea):
            mismo = ("voto" if m.group(1).lower() == "voto" else "disidencia") == tipo
            if not mismo:
                return j
        j += 1
    return j


def _encontrar_bloques(lineas: list[str]) -> list[_Bloque]:
    bloques: list[_Bloque] = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if _H_DICTAMEN.match(linea):
            b = _Bloque("dictamen", [], i, i + 1)
            bloques.append(b)
            i += 1
            continue
        if _H_FALLO.match(linea):
            b = _Bloque("mayoria", [], i, i + 1)
            bloques.append(b)
            i += 1
            continue
        m = _H_OPINION.match(linea)
        if m and not re.search(r"[\d;)]", linea):
            tipo = "voto" if m.group(1).lower() == "voto" else "disidencia"
            fin = _fin_de_encabezado(lineas, i, tipo)
            bloques.append(_Bloque(tipo, _nombres_de_encabezado(lineas[i:fin]), i, fin))
            i = fin
            continue
        i += 1
    return bloques


def _apellidos(nombre: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[^\W\d_]{3,}", nombre)}


def _parrafos_sumario(lineas: list[str]) -> list[tuple[str, str, str]]:
    """`(tipo_tag, autor_tag, texto)` por párrafo de sumario. `tipo_tag`:
    `""` (mayoría) / `"voto"` / `"disidencia"` / `"dictamen"`."""
    parrafos: list[list[str]] = []
    for linea in lineas:
        if _es_heading_caps(linea) or not parrafos:
            parrafos.append([linea])
        else:
            parrafos[-1].append(linea)
    salida = []
    for p in parrafos:
        texto = "\n".join(p).strip()
        if not texto:
            continue
        tag = _TAG_SUMARIO.search(texto)
        if tag:
            salida.append((tag.group(1).lower(), tag.group(2).strip(), texto))
        elif _REMITE_DICTAMEN.search(texto):
            salida.append(("dictamen", "", texto))
        else:
            salida.append(("", "", texto))
    return salida


def _destino_sumario(
    tipo_tag: str, autor_tag: str, bloques: list[_Bloque], mayoria: _Bloque
) -> _Bloque:
    if tipo_tag == "dictamen":
        return next((b for b in bloques if b.tipo == "dictamen"), mayoria)
    if tipo_tag == "":
        return mayoria
    del_tipo = [b for b in bloques if b.tipo == tipo_tag]
    palabras = _apellidos(autor_tag)
    for b in del_tipo:
        if palabras & _apellidos(" ".join(b.autores)):
            return b
    if del_tipo:  # hay bloques de ese tipo pero no matchea el nombre → el primero
        return del_tipo[0]
    if tipo_tag == "disidencia":
        limpio = _PREFIJO_JUEZ.sub("", autor_tag).strip()
        nuevo = _Bloque("disidencia", [_capitalizar(limpio)] if limpio else [], -1)
        bloques.append(nuevo)
        return nuevo
    return mayoria


def partir_secciones(texto: str) -> list[SeccionFallo]:
    """Las secciones del fallo, en orden. Cada línea de contenido cae en una."""
    lineas = texto.splitlines()
    bloques = _encontrar_bloques(lineas)
    if not bloques:
        limpio = texto.strip()
        return [SeccionFallo("mayoria", None, 0, limpio)] if limpio else []

    posiciones = sorted(b.pos for b in bloques)
    primero = posiciones[0]
    for b in bloques:
        siguientes = [p for p in posiciones if p > b.pos]
        fin = min(siguientes) if siguientes else len(lineas)
        b.cuerpo = "\n".join(lineas[b.cuerpo_desde : fin]).strip()

    mayoria = next((b for b in bloques if b.tipo == "mayoria"), None)
    if mayoria is None:
        mayoria = _Bloque("mayoria", [], primero, primero)
        bloques.append(mayoria)

    for tipo_tag, autor_tag, parrafo in _parrafos_sumario(lineas[:primero]):
        _destino_sumario(tipo_tag, autor_tag, bloques, mayoria).sumarios.append(parrafo)

    bloques.sort(key=lambda b: (b.pos if b.pos >= 0 else 10**9, _ORDEN_TIPO[b.tipo]))
    return [
        SeccionFallo(b.tipo, b.autor, i, b.texto())
        for i, b in enumerate(bloques)
        if b.texto()
    ]
