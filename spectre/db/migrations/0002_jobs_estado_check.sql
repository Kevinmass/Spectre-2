-- 0002 — CHECK sobre jobs.estado, ahora que PR-03 congela el vocabulario de la
-- cola: 'pendiente' | 'en_proceso' | 'hecho' | 'fallido'.
--
-- SQLite no tiene ALTER TABLE ADD CONSTRAINT: hay que reconstruir la tabla
-- (crear la nueva, copiar, borrar la vieja, renombrar). `jobs` no tiene claves
-- foráneas entrantes, así que no hace falta tocar PRAGMA foreign_keys.

CREATE TABLE jobs_nueva (
    id           INTEGER PRIMARY KEY,
    tipo         TEXT NOT NULL,
    payload      TEXT,
    estado       TEXT NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente', 'en_proceso', 'hecho', 'fallido')),
    intentos     INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    creado_at    TEXT NOT NULL,
    iniciado_at  TEXT,
    terminado_at TEXT
);

INSERT INTO jobs_nueva (
    id, tipo, payload, estado, intentos, error, creado_at, iniciado_at, terminado_at
)
SELECT
    id, tipo, payload, estado, intentos, error, creado_at, iniciado_at, terminado_at
FROM jobs;

DROP TABLE jobs;
ALTER TABLE jobs_nueva RENAME TO jobs;

CREATE INDEX idx_jobs_estado ON jobs (estado);
