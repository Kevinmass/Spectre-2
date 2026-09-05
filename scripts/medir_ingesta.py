"""PR-25 — Medición end-to-end de la ingesta.

Corre `spectre ingest` de verdad (subproceso nuevo) sobre un tomo, contra un
`SPECTRE_DATA_DIR` temporal y vacío, y mide tres cosas reales, no estimadas:

- **Tiempo por etapa**: se lee de `jobs.iniciado_at`/`terminado_at` (ya las
  escribe el runner, PR-03/19) después de que el proceso termina — no hace
  falta instrumentar nada del pipeline.
- **Memoria pico**: el propio subproceso de ingesta se mide a **sí mismo**
  justo antes de salir (`_entrypoint_subproceso`) y lo imprime por stdout con
  un marcador. En Linux eso es `resource.getrusage(RUSAGE_SELF).ru_maxrss`,
  un contador que mantiene el kernel y que solo crece — exacto, sin sondeo.
  En Windows (`resource` no existe) es `psutil...memory_info().peak_wset`
  del propio proceso, mismo contador mantenido por el sistema operativo.
  **Se descartó que el proceso *padre* sondeara al *hijo* desde afuera**: en
  el entorno donde se corrió esta medición (ver bitácora PR-25), leer la
  memoria de un proceso ajeno por `psutil` devolvía un valor congelado en
  ~4 MB sin importar cuánto asignara el hijo — un proceso midiéndose a sí
  mismo no tiene ese problema y además es el método más simple que existe
  para esto en cualquier sistema operativo.
- **Tamaño del índice**: se mide el `spectre.db` y `data/vectors/` reales
  después de ingestar, no se calcula a mano.

Corre los tomos uno atrás del otro en el **mismo** `data_dir` temporal (como
haría alguien indexando su colección de a poco), para que el tamaño de
índice final sea el de "N tomos juntos", no la suma de mediciones aisladas.

Uso: `python scripts/medir_ingesta.py <pdf1>:<numero1> <pdf2>:<numero2> ...`
Sin argumentos, usa `data/tomos/348.pdf` y `data/tomos/349.pdf` del propio
repo (el fixture de referencia, ver CLAUDE.md).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Nombres de etapa en el orden del pipeline (espeja `spectre/jobs/pipeline.py`
#: sin importarlo, para poder leer los resultados aunque el import fallara).
ETAPAS = (
    "descargar",
    "extraer",
    "limpiar",
    "segmentar",
    "estructurar",
    "fragmentar",
    "embeber",
    "indexar",
)

_MARCADOR_PICO = "__SPECTRE_PICO_MB__="


@dataclass
class MedicionTomo:
    numero: int
    paginas: int
    fallos: int
    chunks: int
    segundos_por_etapa: dict[str, float] = field(default_factory=dict)
    segundos_total: float = 0.0
    memoria_pico_mb: float = 0.0


def _pico_propio_mb() -> float:
    """El pico de memoria física del proceso **actual**, medido por el
    propio sistema operativo. Nunca estima ni promedia."""
    try:
        import resource  # no existe en Windows

        pico_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reporta KB; macOS reporta bytes.
        return pico_kb / (1024 * 1024 if platform.system() == "Darwin" else 1024)
    except ImportError:
        import psutil

        mem = psutil.Process(os.getpid()).memory_info()
        valor = getattr(mem, "peak_wset", None) or mem.rss
        return valor / (1024 * 1024)


def _entrypoint_subproceso(numero: int, pdf_path: str) -> int:
    """Corre en el subproceso hijo: hace la ingesta real y al final imprime
    su propio pico de memoria por stdout con un marcador fácil de parsear."""
    from spectre.cli import main as cli_main

    rc = cli_main(["ingest", str(numero), "--pdf", pdf_path])
    print(f"{_MARCADOR_PICO}{_pico_propio_mb()}")
    return rc


def _tamano_dir(ruta: Path) -> int:
    """Bytes reales en disco. `0` si no existe (no se inventa un número)."""
    if not ruta.exists():
        return 0
    if ruta.is_file():
        return ruta.stat().st_size
    return sum(p.stat().st_size for p in ruta.rglob("*") if p.is_file())


def _duraciones_por_etapa(conn: sqlite3.Connection, tomo_id: int) -> dict[str, float]:
    """Segundos entre `iniciado_at` y `terminado_at` de la corrida más
    reciente de cada etapa para este tomo. Una etapa sin job (no debería
    pasar en una corrida limpia que terminó `indexado`) queda afuera del
    dict en vez de rellenarse con `0` — un `0` inventado escondería el bug."""
    resultado: dict[str, float] = {}
    for nombre in ETAPAS:
        tipo = f"pipeline.{nombre}"
        filas = conn.execute(
            "SELECT payload, iniciado_at, terminado_at FROM jobs "
            "WHERE tipo = ? ORDER BY id DESC",
            (tipo,),
        ).fetchall()
        for payload, iniciado_at, terminado_at in filas:
            if json.loads(payload).get("tomo_id") != tomo_id:
                continue
            if iniciado_at and terminado_at:
                delta = datetime.fromisoformat(terminado_at) - datetime.fromisoformat(
                    iniciado_at
                )
                resultado[nombre] = delta.total_seconds()
            break
    return resultado


def medir_tomo(numero: int, pdf_path: Path, data_dir: Path) -> MedicionTomo:
    """Corre `spectre ingest <numero> --pdf <pdf_path>` como subproceso real
    contra `data_dir`, y mide tiempo total, memoria pico y tiempo por etapa.
    Revienta si el tomo no terminó `indexado` — no hay número honesto que
    reportar para una ingesta que falló."""
    env = {**os.environ, "SPECTRE_DATA_DIR": str(data_dir)}
    inicio = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.medir_ingesta",
            "--subproceso",
            str(numero),
            str(pdf_path),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    segundos_total = time.perf_counter() - inicio
    if proc.returncode != 0:
        raise RuntimeError(
            f"`spectre ingest {numero}` terminó con código {proc.returncode}:\n"
            f"{proc.stdout}"
        )

    memoria_pico_mb = 0.0
    for linea in proc.stdout.splitlines():
        if linea.startswith(_MARCADOR_PICO):
            memoria_pico_mb = float(linea[len(_MARCADOR_PICO) :])
    if memoria_pico_mb == 0.0:
        raise RuntimeError(
            f"el subproceso del tomo {numero} no reportó su pico de memoria "
            f"(salida completa):\n{proc.stdout}"
        )

    conn = sqlite3.connect(data_dir / "spectre.db")
    try:
        fila = conn.execute(
            "SELECT id, estado, paginas FROM tomos WHERE numero = ?", (numero,)
        ).fetchone()
        if fila is None:
            raise RuntimeError(f"tomo {numero}: no quedó registrado en la base")
        tomo_id, estado, paginas = fila
        if estado != "indexado":
            raise RuntimeError(
                f"tomo {numero} terminó en estado '{estado}', no 'indexado' — "
                "no se reporta un número de una ingesta que no cerró"
            )
        fallos = conn.execute(
            "SELECT COUNT(*) FROM fallos WHERE tomo_id = ?", (tomo_id,)
        ).fetchone()[0]
        chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks c JOIN fallos f ON f.id = c.fallo_id "
            "WHERE f.tomo_id = ?",
            (tomo_id,),
        ).fetchone()[0]
        segundos_por_etapa = _duraciones_por_etapa(conn, tomo_id)
    finally:
        conn.close()

    return MedicionTomo(
        numero=numero,
        paginas=paginas or 0,
        fallos=fallos,
        chunks=chunks,
        segundos_por_etapa=segundos_por_etapa,
        segundos_total=segundos_total,
        memoria_pico_mb=memoria_pico_mb,
    )


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--subproceso":
        return _entrypoint_subproceso(int(argv[1]), argv[2])

    if argv:
        pares = []
        for arg in argv:
            ruta, _, numero = arg.partition(":")
            pares.append((int(numero), Path(ruta)))
    else:
        pares = [
            (348, PROJECT_ROOT / "data" / "tomos" / "348.pdf"),
            (349, PROJECT_ROOT / "data" / "tomos" / "349.pdf"),
        ]

    for _, pdf in pares:
        if not pdf.exists():
            print(f"falta {pdf} — no hay nada que medir", file=sys.stderr)
            return 1

    data_dir = Path(tempfile.mkdtemp(prefix="spectre-medicion-"))
    print(f"data_dir temporal: {data_dir}")
    try:
        mediciones = []
        for numero, pdf in pares:
            print(f"midiendo tomo {numero} ({pdf})...")
            m = medir_tomo(numero, pdf, data_dir)
            mediciones.append(m)
            print(
                f"  {m.segundos_total:.1f}s total, "
                f"{m.memoria_pico_mb:.0f} MB pico, {m.chunks} chunks"
            )

        tamano_db = _tamano_dir(data_dir / "spectre.db")
        tamano_vectores = _tamano_dir(data_dir / "vectors")
        print(f"\nspectre.db final ({len(pares)} tomos): {tamano_db / 1e6:.1f} MB")
        print(f"vectors/ final ({len(pares)} tomos): {tamano_vectores / 1e6:.1f} MB")

        for m in mediciones:
            print(f"\n--- tomo {m.numero} ---")
            print(json.dumps(m.__dict__, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
