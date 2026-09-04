-- 0004 — CHECK sobre tomos.estado, ahora que PR-19 congela el vocabulario del
-- pipeline: el estado avanza en una sola dirección,
--   registrado -> descargado -> extraido -> limpio -> segmentado
--             -> estructurado -> fragmentado -> embebido -> indexado
-- una etapa por job (`jobs/pipeline.py`). Un tomo que mide `requiere_ocr`
-- (columna `calidad`, PR-18) se frena en `extraido`: no hay estados propios
-- para eso, la cola visible de D-10 se lee cruzando `estado` y `calidad`, no
-- inventando un `estado` más.
--
-- Mismo patrón que 0002 (jobs.estado): SQLite no tiene ALTER TABLE ADD
-- CONSTRAINT, hay que reconstruir la tabla. A diferencia de `jobs`, `tomos`
-- SÍ tiene claves foráneas entrantes (`paginas.tomo_id`, `fallos.tomo_id`,
-- ambas ON DELETE CASCADE) — por eso el PRAGMA foreign_keys se apaga durante
-- el swap: dentro de la transacción de la migración no hay drop real hasta el
-- `DROP TABLE tomos`, y para ese instante las FK de `paginas`/`fallos` deben
-- poder seguir apuntando al nombre `tomos` sin que SQLite objete el hueco
-- momentáneo. Se reactiva al final, dentro de la misma transacción.

PRAGMA foreign_keys = OFF;

CREATE TABLE tomos_nueva (
    id            INTEGER PRIMARY KEY,
    numero        INTEGER NOT NULL UNIQUE,
    volumen       TEXT,
    anio          INTEGER,
    csjn_tomo_id  TEXT,
    pdf_path      TEXT,
    sha256        TEXT UNIQUE,
    calidad       TEXT NOT NULL DEFAULT 'desconocida'
                    CHECK (calidad IN ('digital', 'requiere_ocr', 'desconocida')),
    paginas       INTEGER,
    offset_pagina INTEGER,
    estado        TEXT NOT NULL DEFAULT 'registrado'
                    CHECK (estado IN (
                        'registrado', 'descargado', 'extraido', 'limpio',
                        'segmentado', 'estructurado', 'fragmentado',
                        'embebido', 'indexado'
                    )),
    indexado_at   TEXT
);

INSERT INTO tomos_nueva (
    id, numero, volumen, anio, csjn_tomo_id, pdf_path, sha256, calidad,
    paginas, offset_pagina, estado, indexado_at
)
SELECT
    id, numero, volumen, anio, csjn_tomo_id, pdf_path, sha256, calidad,
    paginas, offset_pagina, estado, indexado_at
FROM tomos;

DROP TABLE tomos;
ALTER TABLE tomos_nueva RENAME TO tomos;

PRAGMA foreign_keys = ON;
