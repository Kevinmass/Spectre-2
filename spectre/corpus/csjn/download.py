"""Descarga de PDFs de tomos desde la CSJN (D-9): dado un `csjn_tomo_id`
(los que da `catalog.listar_catalogo`), baja el PDF a disco con reintentos y
lo cachea por archivo/sha256.

**Sin resume por HTTP Range** (spike de este PR, sigue al de PR-16): el
servidor ignora el header `Range` y devuelve el archivo entero igual — probado
pidiendo los primeros 1024 bytes de un tomo de 58 MB: `200 OK` con el archivo
completo, no `206 Partial Content`. "Reanudar una descarga cortada" (criterio
de aceptación) es entonces a nivel de archivo, no de bytes: se descarga
siempre a un temporal (`<destino>.partial`) y solo se lo renombra al destino
final si terminó bien; un proceso cortado a mitad deja ese `.partial` a medio
escribir, y la próxima corrida lo **descarta y vuelve a bajar entero** — no
intenta pegar bytes al final de algo que quizás esté corrupto.

Caché: si `destino` ya existe, no se pide nada de nuevo (`forzar=True` lo
saltea). Así una corrida repetida sobre los mismos tomos no vuelve a bajar
megabytes que ya están — el sha256 de lo que hay en disco identifica qué se
tiene, coherente con `tomos.sha256` del esquema.
"""

from __future__ import annotations

import hashlib
import time
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

_URL_TOMO = "https://sjservicios.csjn.gov.ar/sj/verTomo"
_TIMEOUT = 60
_AGENTE = (
    "Mozilla/5.0 (compatible; Spectre/0.0; +https://github.com/Kevinmass/Spectre-2)"
)
_TAMANO_BLOQUE = 1 << 16  # 64 KiB


@dataclass(frozen=True, slots=True)
class Descarga:
    """El resultado de bajar (o reusar) un tomo."""

    ruta: Path
    sha256: str
    bytes: int
    reutilizada: bool  # True: ya estaba en disco, no se pidió nada


def _sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(_TAMANO_BLOQUE), b""):
            h.update(bloque)
    return h.hexdigest()


def _descargar_a(url: str, destino_parcial: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _AGENTE, "Accept": "*/*"})
    with (
        urllib.request.urlopen(req, timeout=_TIMEOUT) as resp,  # noqa: S310
        destino_parcial.open("wb") as f,
    ):
        while True:
            bloque = resp.read(_TAMANO_BLOQUE)
            if not bloque:
                break
            f.write(bloque)


def descargar_tomo(
    csjn_tomo_id: str,
    destino: Path,
    *,
    intentos: int = 3,
    espera: float = 1.0,
    forzar: bool = False,
    descargar_a: Callable[[str, Path], None] = _descargar_a,
) -> Descarga:
    """Descarga el PDF de `csjn_tomo_id` a `destino`.

    Si `destino` ya existe y `forzar` es `False`, no pide nada (caché por
    archivo). Si no, reintenta hasta `intentos` veces con backoff simple
    (`espera * intento` segundos entre reintentos) antes de rendirse con
    `ConnectionError` — D-05: no vuelve silenciosamente un archivo vacío o a
    medio bajar como si hubiera terminado. `descargar_a` es un punto de
    inyección para los tests (simular fallas/red sin tocar la red real); sin
    pasarlo, pega contra el sitio real.
    """
    if destino.exists() and not forzar:
        return Descarga(destino, _sha256_de(destino), destino.stat().st_size, True)

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".partial")
    url = f"{_URL_TOMO}?tomoId={csjn_tomo_id}"

    ultimo_error: OSError | None = None
    for intento in range(1, intentos + 1):
        try:
            descargar_a(url, parcial)
            parcial.replace(destino)  # atómico: recién acá "está" el archivo
            ultimo_error = None
            break
        except OSError as e:
            ultimo_error = e
            parcial.unlink(missing_ok=True)  # descarta el parcial: no se pega a él
            if intento < intentos:
                time.sleep(espera * intento)

    if ultimo_error is not None:
        raise ConnectionError(
            f"no se pudo descargar tomoId={csjn_tomo_id} tras {intentos} intentos"
        ) from ultimo_error

    return Descarga(destino, _sha256_de(destino), destino.stat().st_size, False)


def descargar_varios(
    pedidos: Iterable[tuple[str, Path]],
    *,
    intentos: int = 3,
    espera: float = 1.0,
    pausa_entre_tomos: float = 1.0,
    descargar_a: Callable[[str, Path], None] = _descargar_a,
) -> list[Descarga]:
    """Descarga varios `(csjn_tomo_id, destino)` en secuencia, con una pausa
    entre cada uno (ritmo respetuoso: sin esto, bajar el catálogo entero sería
    una ráfaga de cientos de pedidos seguidos al mismo servidor)."""
    pedidos = list(pedidos)
    resultados = []
    for i, (csjn_tomo_id, destino) in enumerate(pedidos):
        resultados.append(
            descargar_tomo(
                csjn_tomo_id,
                destino,
                intentos=intentos,
                espera=espera,
                descargar_a=descargar_a,
            )
        )
        if i < len(pedidos) - 1:
            time.sleep(pausa_entre_tomos)
    return resultados
