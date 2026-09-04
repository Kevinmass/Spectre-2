-- 0003 — índice léxico FTS5 sobre chunks.texto (PR-14, decisión D-6).
--
-- `chunks_fts` es una tabla "external content": no duplica `texto`, solo
-- indexa lo que ya vive en `chunks` (content='chunks', content_rowid='id').
-- SQLite no sincroniza sola una external content table: los triggers de acá
-- abajo son los que mantienen el índice al día en cada INSERT/UPDATE/DELETE
-- sobre `chunks` (incluido el borrado en cascada desde `fallos`/`tomos`), sin
-- que `db/repo.py` ni el job runner tengan que saber que el índice existe.
--
-- Tokenizer `unicode61 remove_diacritics 2`: sin stemmer en español (SQLite
-- no trae uno), pero "artículo" y "articulo" matchean igual — lo que importa
-- para citas legales, donde quien busca no siempre tipea la tilde.
--
-- El `rebuild` de después de crear la tabla puebla el índice si `chunks` ya
-- tenía filas antes de esta migración (no debería pasar hoy — nada persiste
-- chunks todavía, eso es PR-19 — pero es gratis y correcto no asumirlo).

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    texto,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild');

CREATE TRIGGER chunks_fts_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, texto) VALUES (new.id, new.texto);
END;

CREATE TRIGGER chunks_fts_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, texto) VALUES ('delete', old.id, old.texto);
END;

CREATE TRIGGER chunks_fts_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, texto) VALUES ('delete', old.id, old.texto);
    INSERT INTO chunks_fts (rowid, texto) VALUES (new.id, new.texto);
END;
