-- 0006 — partes del fallo y su clasificación (PR-C5).
--
-- PR-08 parte la carátula en actor / demandado pero nunca los persistió (la
-- etapa `estructurar` guardaba solo fecha / jueces / tribunal / recurso). Acá
-- se agregan las columnas: el string crudo de cada parte y su tipo
-- (persona_fisica / empresa / estado / organismo), para el filtro por tipo de
-- parte de `/api/buscar` (observación 01).
--
-- `ALTER TABLE ADD COLUMN` alcanza: SQLite lo soporta y las FK entrantes de
-- `fallos` no se tocan (no es como 0002 / 0004, que reconstruyen la tabla por
-- un CHECK sobre una columna existente). El CHECK de dominio va en la propia
-- cláusula ADD COLUMN.

ALTER TABLE fallos ADD COLUMN actor TEXT;
ALTER TABLE fallos ADD COLUMN actor_tipo TEXT
    CHECK (actor_tipo IN ('persona_fisica', 'empresa', 'estado', 'organismo')
           OR actor_tipo IS NULL);
ALTER TABLE fallos ADD COLUMN demandado TEXT;
ALTER TABLE fallos ADD COLUMN demandado_tipo TEXT
    CHECK (demandado_tipo IN ('persona_fisica', 'empresa', 'estado', 'organismo')
           OR demandado_tipo IS NULL);

CREATE INDEX idx_fallos_actor_tipo ON fallos (actor_tipo);
CREATE INDEX idx_fallos_demandado_tipo ON fallos (demandado_tipo);
