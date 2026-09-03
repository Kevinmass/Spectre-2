"""Cola de trabajos durable sobre SQLite y su runner.

Diseño (plan §6 PR-03, decisiones D-3 / D-5 / D-6):

- **Un proceso, un hilo.** El runner es un `while` que reclama el pendiente más
  viejo, lo corre y pasa al siguiente. Sin threads, sin pool, sin control de
  recursos casero (D-06). Si hace falta paralelismo se corren varios procesos,
  no varios hilos, y recién cuando esté medido que hace falta.
- **La cola vive en la tabla `jobs`** (creada en la migración 0001). El estado
  de cada trabajo está en la base, no en memoria ni en un JSON (D-04).
- **Reanudable sin perder ni duplicar.** El ciclo de un job es
  `pendiente → en_proceso → hecho | fallido`. Reclamar un job (pasarlo a
  `en_proceso` e incrementar `intentos`) se **commitea solo**: es lo único que
  queda si el proceso muere justo después. Los efectos del handler y la marca
  `hecho` van juntos en **una sola transacción**; si el proceso muere antes del
  commit, SQLite descarta esa transacción y el job queda `en_proceso`. Al
  reanudar, `recuperar_zombis()` lo devuelve a `pendiente` y se reprocesa desde
  cero. Nada se pierde (el job sigue en la cola) y nada se duplica (los efectos
  a medio hacer se descartaron con la transacción).

**Contrato del handler:** recibe `(conn, job)`, escribe *solo* a través de esa
conexión y **no llama `commit()` ni `rollback()`**. El runner es dueño del
límite transaccional. Un handler que commitea rompe la garantía de "sin
duplicar". Si el handler lanza una excepción, el runner hace rollback y
reintenta hasta `max_intentos`; agotados, el job queda `fallido` con el error
guardado. Ningún job "termina bien" sin haber corrido de verdad (D-05).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from spectre.db import ahora_iso

PENDIENTE = "pendiente"
EN_PROCESO = "en_proceso"
HECHO = "hecho"
FALLIDO = "fallido"

#: Estados terminales: el runner no los vuelve a tocar.
TERMINALES = frozenset({HECHO, FALLIDO})


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    tipo: str
    payload: dict
    estado: str
    intentos: int
    error: str | None
    creado_at: str
    iniciado_at: str | None
    terminado_at: str | None


Handler = Callable[[sqlite3.Connection, Job], None]


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        tipo=row["tipo"],
        payload=json.loads(row["payload"]) if row["payload"] else {},
        estado=row["estado"],
        intentos=row["intentos"],
        error=row["error"],
        creado_at=row["creado_at"],
        iniciado_at=row["iniciado_at"],
        terminado_at=row["terminado_at"],
    )


class Runner:
    """Encola y procesa jobs sobre una conexión ya migrada.

    `max_intentos` cuenta *corridas* del job, incluidas las que abortó una
    caída del proceso (el `intentos` se incrementa al reclamar, antes de
    correr el handler): así un handler que revienta el proceso una y otra vez
    no deja la cola girando para siempre.
    """

    def __init__(self, conn: sqlite3.Connection, *, max_intentos: int = 3) -> None:
        if max_intentos < 1:
            raise ValueError("max_intentos tiene que ser >= 1")
        self.conn = conn
        self.max_intentos = max_intentos
        self._handlers: dict[str, Handler] = {}

    # -- registro y encolado -------------------------------------------- #

    def registrar(self, tipo: str, handler: Handler) -> None:
        if tipo in self._handlers:
            raise ValueError(f"ya hay un handler para el tipo {tipo!r}")
        self._handlers[tipo] = handler

    def encolar(self, tipo: str, payload: dict | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO jobs (tipo, payload, estado, creado_at) VALUES (?, ?, ?, ?)",
            (
                tipo,
                json.dumps(payload or {}, ensure_ascii=False),
                PENDIENTE,
                ahora_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # -- lectura ------------------------------------------------------------ #

    def get(self, job_id: int) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job(row) if row is not None else None

    def contar_por_estado(self) -> dict[str, int]:
        return {
            row["estado"]: row["n"]
            for row in self.conn.execute(
                "SELECT estado, count(*) AS n FROM jobs GROUP BY estado"
            )
        }

    # -- ejecución ------------------------------------------------------- #

    def recuperar_zombis(self) -> int:
        """Jobs que quedaron `en_proceso` porque el proceso anterior murió a
        mitad. Vuelven a `pendiente`, o a `fallido` si ya agotaron los
        intentos. Devuelve cuántos tocó. Se llama sola al arrancar `run()`."""
        filas = self.conn.execute(
            "SELECT id, intentos FROM jobs WHERE estado = ?", (EN_PROCESO,)
        ).fetchall()
        for fila in filas:
            if fila["intentos"] >= self.max_intentos:
                self.conn.execute(
                    "UPDATE jobs SET estado = ?, error = ?, terminado_at = ? "
                    "WHERE id = ?",
                    (
                        FALLIDO,
                        "el proceso cayó y no quedan reintentos",
                        ahora_iso(),
                        fila["id"],
                    ),
                )
            else:
                self.conn.execute(
                    "UPDATE jobs SET estado = ?, iniciado_at = NULL WHERE id = ?",
                    (PENDIENTE, fila["id"]),
                )
        self.conn.commit()
        return len(filas)

    def _tomar(self) -> Job | None:
        """Reclama el pendiente más viejo: `en_proceso`, `iniciado_at` ahora,
        `intentos + 1`, y **commit**. Un solo proceso toca esta tabla (decisión
        del plan), así que SELECT + UPDATE + commit alcanza para reclamar sin
        carrera. El commit hace durable el reclamo: si el proceso muere ya, el
        job queda `en_proceso` y lo rescata `recuperar_zombis()`."""
        row = self.conn.execute(
            "SELECT id FROM jobs WHERE estado = ? ORDER BY id LIMIT 1", (PENDIENTE,)
        ).fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        self.conn.execute(
            "UPDATE jobs SET estado = ?, iniciado_at = ?, intentos = intentos + 1 "
            "WHERE id = ?",
            (EN_PROCESO, ahora_iso(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def _terminar_ok(self, job: Job) -> None:
        self.conn.execute(
            "UPDATE jobs SET estado = ?, terminado_at = ?, error = NULL WHERE id = ?",
            (HECHO, ahora_iso(), job.id),
        )

    def _fallar(self, job: Job, error: str) -> None:
        """Manda el job a `fallido` sin más reintentos. Commit propio."""
        self.conn.execute(
            "UPDATE jobs SET estado = ?, error = ?, terminado_at = ? WHERE id = ?",
            (FALLIDO, error, ahora_iso(), job.id),
        )
        self.conn.commit()

    def _reintentar_o_fallar(self, job: Job, error: str) -> bool:
        """Un intento reventó. Si a `job.intentos` (ya incrementado por el
        reclamo) le quedan reintentos, vuelve a `pendiente`; si no, `fallido`.
        Devuelve True si el job quedó en estado terminal. Commit propio, fuera
        de la transacción de los efectos (que `with self.conn` ya descartó)."""
        if job.intentos >= self.max_intentos:
            self._fallar(job, error)
            return True
        self.conn.execute(
            "UPDATE jobs SET estado = ?, error = ? WHERE id = ?",
            (PENDIENTE, error, job.id),
        )
        self.conn.commit()
        return False

    def _procesar(self, job: Job) -> bool:
        """Corre el handler del job en una sola transacción con la marca
        `hecho`. Devuelve True si el job quedó en estado terminal (`hecho` o
        `fallido`), False si vuelve a la cola para reintento."""
        handler = self._handlers.get(job.tipo)
        if handler is None:
            # Falta cablear un handler: error de programa, pero no puede trabar
            # la cola entera. Directo a `fallido` con el motivo, seguimos.
            self._fallar(job, f"sin handler para el tipo {job.tipo!r}")
            return True
        try:
            with self.conn:
                handler(self.conn, job)
                self._terminar_ok(job)
        except Exception as exc:
            # `with self.conn` ya hizo rollback de los efectos + la marca.
            return self._reintentar_o_fallar(job, f"{type(exc).__name__}: {exc}")
        return True

    def run(self, *, max_jobs: int | None = None) -> int:
        """Procesa pendientes hasta vaciar la cola (o hasta que `max_jobs` jobs
        lleguen a un estado terminal). Arranca rescatando zombis de una caída
        anterior. Devuelve cuántos jobs terminaron (`hecho` o `fallido`) en esta
        corrida; los reintentos no cuentan hasta que se resuelven."""
        self.recuperar_zombis()
        terminados = 0
        while max_jobs is None or terminados < max_jobs:
            job = self._tomar()
            if job is None:
                break
            if self._procesar(job):
                terminados += 1
        return terminados
