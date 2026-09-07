-- 0005 — sumarios oficiales de la CSJN y sus voces (PR-C2b).
--
-- La Secretaría de Jurisprudencia publica, por tomo y página, uno o varios
-- *sumarios* (una regla de doctrina cada uno) con sus *voces* (descriptores de
-- un tesauro propio). PR-C2a dejó el cliente HTTP (`corpus/csjn/sumarios.py`);
-- esta migración es dónde se guardan.
--
-- Aditiva: solo `CREATE TABLE` nuevas, ninguna tabla existente se reconstruye
-- (a diferencia de 0002 / 0004). El vocabulario de `voces` lo trae la CSJN, no
-- lo fija Spectre, así que no hay CHECK.
--
-- `sumarios.voces` guarda las voces de ESE sumario como JSON (igual criterio
-- que `fallos.jueces`): así la vista de fallo / los resultados muestran el
-- sumario sin un join. `fallo_voces` es la forma normalizada, para el filtro
-- por voz de `/api/buscar` (un fallo tiene las voces de todos sus sumarios).

CREATE TABLE sumarios (
    id              INTEGER PRIMARY KEY,
    fallo_id        INTEGER NOT NULL REFERENCES fallos (id) ON DELETE CASCADE,
    orden           INTEGER NOT NULL,
    texto           TEXT NOT NULL,
    voces           TEXT,
    materia         TEXT,
    id_documento    TEXT,
    sincronizado_at TEXT NOT NULL,
    UNIQUE (fallo_id, orden)
);

CREATE INDEX idx_sumarios_fallo ON sumarios (fallo_id);
CREATE INDEX idx_sumarios_materia ON sumarios (materia);

CREATE TABLE voces (
    id     INTEGER PRIMARY KEY,
    valor  TEXT NOT NULL UNIQUE,
    codigo INTEGER
);

CREATE TABLE fallo_voces (
    fallo_id INTEGER NOT NULL REFERENCES fallos (id) ON DELETE CASCADE,
    voz_id   INTEGER NOT NULL REFERENCES voces (id) ON DELETE CASCADE,
    PRIMARY KEY (fallo_id, voz_id)
);

CREATE INDEX idx_fallo_voces_voz ON fallo_voces (voz_id);
