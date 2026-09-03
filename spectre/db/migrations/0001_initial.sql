-- 0001_initial — esquema base de Spectre (plan §5, modelo de datos congelado).
--
-- Convenciones:
--   * id INTEGER PRIMARY KEY (alias explícito de rowid).
--   * Timestamps en TEXT ISO 8601 UTC ("2026-09-03T12:00:00+00:00").
--   * `jueces` y `payload` en TEXT con JSON; el repo no los interpreta todavía.
--   * Las FK hacia el tomo / fallo padre borran en cascada.
--   * CHECK solo sobre los vocabularios que el plan congela: `tomos.calidad` y
--     `secciones.tipo`. `tomos.estado` y `jobs.estado` quedan sin CHECK porque
--     su vocabulario lo fijan PR-19 y PR-03; ponerles uno ahora sería adivinar.
--   * Las tablas que otro PR va a estrenar (secciones, chunks, citas, jobs)
--     llevan lo mínimo: PK, FK, NOT NULL evidentes e índices de lookup. Los
--     UNIQUE de dominio los agrega el PR dueño con su propia migración.

CREATE TABLE tomos (
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
    estado        TEXT NOT NULL DEFAULT 'registrado',
    indexado_at   TEXT
);

CREATE TABLE paginas (
    id             INTEGER PRIMARY KEY,
    tomo_id        INTEGER NOT NULL REFERENCES tomos (id) ON DELETE CASCADE,
    pdf_page       INTEGER NOT NULL,
    pagina_oficial INTEGER,
    texto_crudo    TEXT,
    texto_limpio   TEXT,
    UNIQUE (tomo_id, pdf_page)
);

CREATE INDEX idx_paginas_tomo_oficial ON paginas (tomo_id, pagina_oficial);

CREATE TABLE fallos (
    id              INTEGER PRIMARY KEY,
    tomo_id         INTEGER NOT NULL REFERENCES tomos (id) ON DELETE CASCADE,
    caratula        TEXT NOT NULL,
    cita            TEXT UNIQUE,
    pagina_inicio   INTEGER,
    pagina_fin      INTEGER,
    fecha           TEXT,
    tribunal_origen TEXT,
    tipo_recurso    TEXT,
    jueces          TEXT
);

CREATE INDEX idx_fallos_tomo ON fallos (tomo_id);

CREATE TABLE secciones (
    id       INTEGER PRIMARY KEY,
    fallo_id INTEGER NOT NULL REFERENCES fallos (id) ON DELETE CASCADE,
    tipo     TEXT NOT NULL
               CHECK (tipo IN ('mayoria', 'voto', 'disidencia', 'dictamen')),
    autor    TEXT,
    orden    INTEGER NOT NULL,
    texto    TEXT
);

CREATE INDEX idx_secciones_fallo ON secciones (fallo_id);

CREATE TABLE chunks (
    id               INTEGER PRIMARY KEY,
    fallo_id         INTEGER NOT NULL REFERENCES fallos (id) ON DELETE CASCADE,
    seccion_id       INTEGER REFERENCES secciones (id) ON DELETE CASCADE,
    orden            INTEGER NOT NULL,
    texto            TEXT NOT NULL,
    pagina_oficial   INTEGER,
    modelo_embedding TEXT,
    embedding_at     TEXT
);

CREATE INDEX idx_chunks_fallo ON chunks (fallo_id);
CREATE INDEX idx_chunks_modelo ON chunks (modelo_embedding);

CREATE TABLE citas (
    id            INTEGER PRIMARY KEY,
    fallo_id      INTEGER NOT NULL REFERENCES fallos (id) ON DELETE CASCADE,
    tomo_citado   INTEGER,
    pagina_citada INTEGER,
    contexto      TEXT
);

CREATE INDEX idx_citas_fallo ON citas (fallo_id);
CREATE INDEX idx_citas_destino ON citas (tomo_citado, pagina_citada);

CREATE TABLE jobs (
    id           INTEGER PRIMARY KEY,
    tipo         TEXT NOT NULL,
    payload      TEXT,
    estado       TEXT NOT NULL DEFAULT 'pendiente',
    intentos     INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    creado_at    TEXT NOT NULL,
    iniciado_at  TEXT,
    terminado_at TEXT
);

CREATE INDEX idx_jobs_estado ON jobs (estado);
