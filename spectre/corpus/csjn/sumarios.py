"""Sumarios oficiales de la CSJN por tomo y página (PR-C2, spike + cliente).

La Secretaría de Jurisprudencia mantiene una base de **sumarios** —el texto
curado por la Corte que resume la doctrina de cada fallo, con sus *voces*
(descriptores temáticos de un tesauro propio)— consultable en
`https://sjconsulta.csjn.gov.ar/sjconsulta/consultaSumarios/consulta.html`.

**Spike (recon en vivo, 07/09/2026 — detalle en
`docs/qa/spike-C2-sumarios.md`):** la búsqueda es un flujo *stateful* de tres
pasos sobre un backend Java (campos `filter.*`):

  1. `GET  /consultaSumarios/consulta.html`  → abre sesión (cookies
     `SJCONSULTASESSION` + `SRV`).
  2. `POST /consultaSumarios/buscar.html`  (form `filter.tomo` / `filter.pagina`
     + el resto de los `filter.*` en blanco; `g-recaptcha-response` vacío — el
     backend **no lo valida** en este flujo) → guarda la búsqueda en la sesión
     y devuelve un HTML contenedor con `var totalResultados = "N"`.
  3. `GET  /consultaSumarios/paginarSumarios.html?startIndex=K` → **array JSON**
     de sumarios (10 por página) de la búsqueda guardada.

Cada objeto trae `tomo`, `pagina`, `autos` (carátula), `fechaString`
(`dd/mm/yyyy`), `voces` (string separada por `" - "`), `texto` (el sumario, en
HTML) y `linkDocumento` (con `idDocumento=N`). Un fallo puede tener **varios
sumarios** (uno por regla de doctrina), cada uno con sus voces. Es texto
seleccionable, JSON: **no hace falta OCR**. Acceso público, sin credenciales.

Este módulo **no persiste nada** (regla de dependencias: `corpus/` no toca
`index/` ni `embed/`, y todo lo que escribe la base pasa por `db/repo.py`).
`buscar_sumarios(tomo, pagina)` devuelve la lista en memoria; el volcado a la
base y el filtro por voz son PR-C2b.
"""

from __future__ import annotations

import html as _html
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from http.cookiejar import CookieJar

_BASE = "https://sjconsulta.csjn.gov.ar/sjconsulta"
_URL_CONSULTA = f"{_BASE}/consultaSumarios/consulta.html"
_URL_BUSCAR = f"{_BASE}/consultaSumarios/buscar.html"
_URL_PAGINAR = f"{_BASE}/consultaSumarios/paginarSumarios.html"
_URL_VOCES = f"{_BASE}/autocomplete/getVoces.html"

_TIMEOUT = 45
_PAGINA = 10  # el backend pagina de a 10 sí o sí

# Navegador real: el sitio tiene un WAF con firma de cliente. `urllib` (stack
# TLS del sistema) pasa; un `curl.exe` pelado no. Igual mandamos headers de
# navegador y respetamos el flujo de cookies (sin el GET inicial, el POST
# devuelve 500).
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-AR,es;q=0.9"}

_RE_TOTAL = re.compile(r'var\s+totalResultados\s*=\s*"?(\d+)"?')
_RE_ID_DOC = re.compile(r"idDocumento=(\d+)")
_RE_TAG = re.compile(r"<[^>]+>")
_RE_ESPACIOS = re.compile(r"\s+")
_RE_FECHA = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


@dataclass(frozen=True, slots=True)
class Sumario:
    """Un sumario oficial de la CSJN. Mapea 1:1 a un objeto del array JSON de
    `paginarSumarios`. `voces` es la tupla de descriptores del tesauro (en el
    orden que los da la Corte); `texto` es el sumario con las etiquetas HTML
    ya sacadas. `fecha` se normaliza a ISO (`AAAA-MM-DD`) o queda en `None` si
    no venía como `dd/mm/yyyy`. `materia` es
    `analisisDocumental.materiaSecretaria` — la rama del derecho con la que la
    Secretaría clasifica el sumario, o `None` si no vino (PR-C2b)."""

    tomo: int
    pagina: int
    caratula: str | None
    fecha: str | None
    voces: tuple[str, ...]
    texto: str
    id_documento: str | None
    materia: str | None = None


# --------------------------------------------------------------------------- #
# Parseo puro (sin red): testeable contra objetos/HTML de muestra.
# --------------------------------------------------------------------------- #


def _texto_plano(fragmento: str | None) -> str:
    if not fragmento:
        return ""
    sin_tags = _RE_TAG.sub(" ", fragmento)
    return _RE_ESPACIOS.sub(" ", _html.unescape(sin_tags)).strip()


def _voces(valor: object) -> tuple[str, ...]:
    if not isinstance(valor, str):
        return ()
    partes = (p.strip() for p in valor.split(" - "))
    return tuple(p for p in partes if p)


def _fecha_iso(valor: object) -> str | None:
    if not isinstance(valor, str):
        return None
    m = _RE_FECHA.match(valor)
    if not m:
        return None
    d, mes, a = m.groups()
    return f"{a}-{int(mes):02d}-{int(d):02d}"


def _id_documento(link: object) -> str | None:
    if not isinstance(link, str):
        return None
    m = _RE_ID_DOC.search(link)
    return m.group(1) if m else None


def _materia(analisis: object) -> str | None:
    """`analisisDocumental.materiaSecretaria` — la rama del derecho. Viene como
    string suelto o, a veces, como objeto `{descripcion: ...}`; se acepta
    cualquiera de las dos y se ignora lo demás."""
    if not isinstance(analisis, dict):
        return None
    valor = analisis.get("materiaSecretaria")
    if isinstance(valor, dict):
        valor = valor.get("descripcion") or valor.get("valor")
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    return None


def _total_resultados(html_contenedor: str) -> int | None:
    """El `var totalResultados = "N"` del HTML que devuelve `buscar.html`.
    `None` si no está (respuesta inesperada)."""
    m = _RE_TOTAL.search(html_contenedor)
    return int(m.group(1)) if m else None


def _map_sumario(obj: dict, *, tomo: int, pagina: int) -> Sumario:
    """Un objeto crudo del JSON de `paginarSumarios` → `Sumario`. `tomo` /
    `pagina` se pasan como respaldo: casi siempre vienen en `obj`, pero si
    faltaran se usa lo consultado."""
    return Sumario(
        tomo=int(obj.get("tomo") or tomo),
        pagina=int(obj.get("pagina") or pagina),
        caratula=(obj.get("autos") or obj.get("caratulaWeb") or None),
        fecha=_fecha_iso(obj.get("fechaString")),
        voces=_voces(obj.get("voces")),
        texto=_texto_plano(obj.get("texto")),
        id_documento=_id_documento(obj.get("linkDocumento")),
        materia=_materia(obj.get("analisisDocumental")),
    )


# --------------------------------------------------------------------------- #
# Transporte HTTP: el flujo de 3 pasos. Inyectable para los tests.
# --------------------------------------------------------------------------- #


class TransporteHTTP:
    """El flujo real contra la CSJN. Una instancia = una sesión (un juego de
    cookies). Los tests pasan un doble con la misma interfaz."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        self._sesion_abierta = False

    def _abrir(self, req: urllib.request.Request) -> bytes:
        with self._opener.open(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            cuerpo = resp.read()
        if b"Web Application Firewall" in cuerpo:
            raise RuntimeError(
                "la CSJN respondió con la página del WAF (firma de cliente); "
                "el flujo de sumarios quedó bloqueado"
            )
        return cuerpo

    def abrir_sesion(self) -> None:
        """Abre la sesión (GET inicial que setea las cookies). Idempotente:
        si ya está abierta no vuelve a pegarle al sitio — así reusar un mismo
        transporte para varios fallos (el sync de PR-C2b) no hace un GET de más
        por fallo."""
        if self._sesion_abierta:
            return
        req = urllib.request.Request(_URL_CONSULTA, headers=_HEADERS)
        self._abrir(req)
        self._sesion_abierta = True

    def buscar(self, tomo: int, pagina: int) -> int | None:
        if not self._sesion_abierta:
            self.abrir_sesion()
        form = {
            "filter.fullText": "",
            "filter.terminos": "T",
            "filter.autos": "",
            "filter.fechaExacta": "",
            "filter.fechaDesde": "",
            "filter.fechaHasta": "",
            "filter.tomo": str(tomo),
            "filter.pagina": str(pagina),
            "g-recaptcha-response": "",
        }
        req = urllib.request.Request(
            _URL_BUSCAR,
            data=urllib.parse.urlencode(form).encode(),
            headers={
                **_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": _URL_CONSULTA,
                "Origin": "https://sjconsulta.csjn.gov.ar",
            },
            method="POST",
        )
        return _total_resultados(self._abrir(req).decode("utf-8", "replace"))

    def paginar(self, start_index: int) -> list[dict]:
        url = _URL_PAGINAR + "?" + urllib.parse.urlencode({"startIndex": start_index})
        req = urllib.request.Request(
            url,
            headers={
                **_HEADERS,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": _URL_BUSCAR,
            },
        )
        cuerpo = self._abrir(req).decode("utf-8", "replace")
        try:
            datos = json.loads(cuerpo)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"paginarSumarios no devolvió JSON (start={start_index}): "
                f"{cuerpo[:200]}"
            ) from e
        return datos if isinstance(datos, list) else []

    def voces(self, termino: str) -> list[dict]:
        if not self._sesion_abierta:
            self.abrir_sesion()
        req = urllib.request.Request(
            _URL_VOCES,
            data=urllib.parse.urlencode({"term": termino}).encode(),
            headers={
                **_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": _URL_CONSULTA,
            },
            method="POST",
        )
        datos = json.loads(self._abrir(req).decode("utf-8", "replace"))
        return datos if isinstance(datos, list) else []


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #


def buscar_sumarios(
    tomo: int, pagina: int, *, transporte: TransporteHTTP | None = None
) -> list[Sumario]:
    """Los sumarios oficiales del fallo que arranca en `tomo:pagina`, en el
    orden que los da la Corte. Lista vacía si ese fallo no tiene sumarios en la
    base (frecuente: no todos los fallos entran). `transporte` es el punto de
    inyección para los tests; sin él pega contra el sitio real de la CSJN.

    Recorre `paginarSumarios` de a 10 hasta juntar `totalResultados`."""
    tr = transporte or TransporteHTTP()
    tr.abrir_sesion()
    total = tr.buscar(tomo, pagina)
    if not total:
        return []

    sumarios: list[Sumario] = []
    start = 0
    while len(sumarios) < total:
        lote = tr.paginar(start)
        if not lote:
            break
        sumarios.extend(_map_sumario(o, tomo=tomo, pagina=pagina) for o in lote)
        start += _PAGINA
    return sumarios[:total]


@dataclass(frozen=True, slots=True)
class Voz:
    """Una entrada del tesauro de voces de la CSJN (`getVoces`). `codigo` es lo
    que el buscador manda en `filter.idsVocesElegidas` para filtrar por voz."""

    codigo: int
    valor: str


def buscar_voces(
    termino: str, *, transporte: TransporteHTTP | None = None
) -> list[Voz]:
    """Autocompletado del tesauro: las voces cuyo texto contiene `termino`
    (`POST /autocomplete/getVoces.html`, JSON). Para armar el filtro por voz de
    PR-C2b."""
    tr = transporte or TransporteHTTP()
    return _map_voces(tr.voces(termino))


def _map_voces(datos: Iterable[dict]) -> list[Voz]:
    salida: list[Voz] = []
    for d in datos:
        cod, val = d.get("codigoValor"), d.get("valor")
        if isinstance(cod, int) and isinstance(val, str) and val.strip():
            salida.append(Voz(cod, val.strip()))
    return salida
