# Spectre — Plan de reconstrucción

> **Este archivo es la fuente de verdad y el estado del desarrollo.**
> Se marca en el mismo commit que cierra cada PR.

Definido con Kevin el 03/09/2026, después de auditar el proyecto anterior
(`document-semantic-search/`, 3.022 LOC) y analizar el corpus real
(Fallos de la CSJN, Tomo 348, 968 páginas).

Spectre es un motor de búsqueda semántica sobre jurisprudencia argentina.
Nació para la hermana de Kevin, abogada. Primera versión: monousuario, local,
sobre la colección Fallos de la Corte Suprema.

---

## 1. Cómo se ejecuta este plan

Igual que los planes de Mirage-Web y Prisma:

- **Una sesión de Claude Code por PR. No encadenar dos.**
- Cada PR cierra escribiendo `docs/qa/bitacora-PR-NN.md`: qué hizo, qué decidió
  por su cuenta, en qué se desvió del plan, qué verificó y con qué comandos
  exactos, qué dudas quedaron abiertas. **La bitácora tiene que poder leerse sin
  el diff al lado.**
- Kevin trae la bitácora de vuelta al chat para el doble chequeo contra el diff.
- Cada PR marca su casilla en este archivo, en el mismo commit.
- `CLAUDE.md` apunta a este plan.

**Marcas:**
`[N]` núcleo — sin esto no hay producto.
`[V]` puede esperar — se puede diferir sin romper la cadena.

**Criterio de verificación transversal:** el Tomo 348 (`data/tomos/348.pdf`) es
el fixture de referencia. Todo PR de la Fase 1 y 2 se verifica contra números
medidos sobre ese tomo, no contra "parece que anda".

---

## 2. Qué queda del Spectre anterior

Nada de código. El proyecto viejo se conserva como referencia y se saca del paso.

Lo que sobrevive son tres ideas: el objetivo (buscar por significado en
jurisprudencia), el pipeline conceptual (extraer → limpiar → fragmentar →
embeddings → índice → buscar) y la ambición de procesamiento local.

Lo que se descarta y por qué está en la auditoría. Resumen de los defectos que
NO hay que repetir:

| # | Defecto del proyecto anterior | Regla que impone |
|---|---|---|
| D-01 | La API leía `config.documents_path`, la config exponía `config.paths.documents_path`. Ningún endpoint devolvía 200. | Los tests corren en CI desde el PR-00. |
| D-02 | `base_path: "."` creaba las carpetas de datos donde estuvieras parado. | Las rutas se resuelven contra la raíz del paquete, nunca contra el CWD. |
| D-03 | El file watcher nunca llamaba a `.start()`. | Toda tarea de fondo tiene un test que la ve procesar algo real. |
| D-04 | El registro guardaba por `document_id` y releía por `file_hash`. | El estado va en SQLite, no en JSON escrito a mano. |
| D-05 | El procesamiento era `time.sleep(2)` y marcaba `completed` con `chunks_count=10` inventado. | **Ningún stub que reporte éxito.** Si algo no está implementado, falla ruidosamente. |
| D-06 | El control de recursos frenaba los workers cuando había *menos* de 4 GB libres. | Sin control de recursos casero. Un proceso, lotes acotados. |
| D-07 | `CMD python -m core_engine.api.app` llamaba a `uvicorn.run("app:app")`, módulo inexistente. | Un solo punto de entrada, probado. |
| D-08 | El modelo de embeddings era `all-MiniLM-L6-v2`, entrenado solo en inglés. | El modelo va detrás de una interfaz y se registra por chunk. |

---

## 3. Decisiones congeladas

**D-1. La unidad de indexación es el fallo, no el archivo.**
Un tomo es un PDF de ~968 páginas que contiene ~126 fallos. Indexar el archivo
da resultados del tipo "página 517 del Tomo 348", inservibles para citar.

**D-2. La segmentación se apoya en el índice oficial del propio tomo.**
El índice por nombres de las partes, al final del volumen, mapea cada carátula a
su página de inicio (`"Zárate, Pablo Federico y otros c/ ENRE s/ diferencias de
salarios: p. 380"`). Verificado: 126 entradas en el Tomo 348, sin solapamientos,
cubriendo de la página 1 a la 953.

Los delimitadores de texto (`FALLO DE LA CORTE`, `Autos y Vistos`,
`Buenos Aires, <fecha>`) son el plan B, y medido son un plan B malo: de las 121
páginas del Tomo 348 que tienen un delimitador, **54 caen dentro de un fallo ya
empezado** — dictámenes del Procurador, resoluciones intermedias. Delimitar por
texto sobre-parte. Por eso el índice es el plan A y el fallback necesita
validación cruzada, no confianza.

**D-3. Cada fragmento lleva su cita oficial.**
El encabezado de cada página trae tomo y página pegados (`348145`). Verificado:
recuperable en 956 de 968 páginas (98,8%) con offset constante de 6 contra la
paginación del PDF. Un resultado dice `Fallos: 348:145`.

**D-4. Un chunk nunca cruza el borde entre mayoría, voto concurrente y
disidencia.** El Tomo 348 tiene 107 menciones de "disidencia" y 32 de "según su
voto". Devolver una disidencia como doctrina de la Corte no es un bug de
calidad, es un riesgo profesional para quien lo use.

**D-5. Almacenamiento: SQLite + índice vectorial embebido.**
SQLite guarda tomos, fallos, fragmentos, texto limpio y estado de los jobs, y con
FTS5 resuelve el lado léxico de la búsqueda. Los vectores van en LanceDB, en un
archivo al lado. Sin Docker, sin servicios. Un backup es copiar una carpeta.
Descartado Qdrant: 380.000 fragmentos (la colección completa) entran de sobra en
un índice embebido.

**D-6. Búsqueda híbrida: léxica + vectorial, fusionadas por RRF.**
"Artículo 14 de la ley 48" y `Fallos: 311:955` no se encuentran por significado.
El reranker queda fuera del MVP, con la interfaz preparada.

**D-7. El modelo de embeddings es intercambiable.**
Interfaz `EmbeddingModel`, implementación por defecto multilingüe chica (384
dimensiones, CPU). **El modelo usado se registra por fragmento**, para saber qué
hay que reindexar si cambia.

**D-8. El parseo y el embedding están separados.**
El texto limpio y los fragmentos viven en SQLite. Cambiar de modelo reindexa sin
volver a abrir un solo PDF. Esta es la decisión que hace barato equivocarse en
D-7.

**D-9. Ingesta: importador de la CSJN + subida manual.**
Los 349 tomos (1863–2026) son de descarga pública. La subida manual queda como
camino paralelo permanente, para PDFs propios. Sin carpeta vigilada.

**D-10. Degradación explícita por calidad del tomo.**
Los tomos recientes tienen capa de texto limpia (Tomo 348: 2.171.758 caracteres,
2 páginas sin texto). Los antiguos casi seguro son escaneos. El sistema mide y
clasifica cada tomo en `digital` o `requiere_ocr`, indexa los primeros y deja los
segundos en una cola visible. **No se finge que un escaneo se indexó.**

**D-11. Stack: Python 3.11 + FastAPI, interfaz servida en localhost.**
El ecosistema de PDFs y embeddings vive en Python. Se acepta que Spectre no
comparta stack con el resto de Mirage. Migrable a servidor sin reescribir el
motor.

**D-12. Monousuario, sin autenticación, con las costuras marcadas.**
Todo el acceso a datos pasa por `db/repo.py`. Cuando haya multiusuario se cambia
esa capa, no el motor.

---

## 4. Arquitectura

```
Spectre/
├── docs/
│   ├── plan-spectre.md          ← este archivo
│   └── qa/bitacora-PR-NN.md
├── legacy/                       ← el proyecto anterior, solo referencia
├── data/
│   ├── tomos/                    ← PDFs descargados
│   ├── spectre.db                ← SQLite
│   └── vectors/                  ← LanceDB
└── spectre/
    ├── config.py                 ← pydantic-settings
    ├── cli.py
    ├── db/
    │   ├── schema.sql
    │   └── repo.py               ← única puerta al almacenamiento
    ├── corpus/
    │   ├── csjn/
    │   │   ├── catalog.py        ← qué tomos existen
    │   │   └── download.py
    │   ├── pdf/
    │   │   ├── extract.py        ← texto por página + página oficial
    │   │   └── clean.py          ← des-hifenado, encabezados, versalitas
    │   └── fallo/
    │       ├── index_parser.py   ← índice del final → carátula + página
    │       ├── segmenter.py      ← tomo → fallos
    │       ├── structure.py      ← fecha, jueces, secciones
    │       └── citations.py      ← Fallos: N:N
    ├── chunking/
    ├── embed/
    │   ├── base.py               ← interfaz EmbeddingModel
    │   └── local_st.py
    ├── index/
    │   ├── vectors.py            ← LanceDB
    │   └── lexical.py            ← FTS5
    ├── search/
    │   └── hybrid.py             ← RRF
    ├── jobs/
    │   └── runner.py             ← cola durable en SQLite, reanudable
    ├── api/
    └── web/                      ← estático
```

**Regla de dependencias:** `corpus/` no importa `index/` ni `embed/`.
`search/` no importa `corpus/`. Todo cruce pasa por `db/repo.py`.

---

## 5. Modelo de datos (SQLite)

```
tomos      id, numero, volumen, anio, csjn_tomo_id, pdf_path, sha256,
           calidad ('digital'|'requiere_ocr'|'desconocida'),
           paginas, offset_pagina, estado, indexado_at

paginas    id, tomo_id, pdf_page, pagina_oficial, texto_crudo, texto_limpio

fallos     id, tomo_id, caratula, cita ('348:145'), pagina_inicio, pagina_fin,
           fecha, tribunal_origen, tipo_recurso, jueces (json)

secciones  id, fallo_id, tipo ('mayoria'|'voto'|'disidencia'|'dictamen'),
           autor, orden, texto

chunks     id, fallo_id, seccion_id, orden, texto, pagina_oficial,
           modelo_embedding, embedding_at

citas      id, fallo_id, tomo_citado, pagina_citada, contexto

jobs       id, tipo, payload (json), estado, intentos, error,
           creado_at, iniciado_at, terminado_at
```

`chunks.modelo_embedding` es lo que hace posible D-7 y D-8: reindexar por tomo
sin reparsear.

---

## 6. Fases y PRs

### Fase 0 — Fundaciones (3 PRs)

- [x] **PR-00 `[N]` Esqueleto del repo**
  `pyproject.toml`, ruff, pytest, `.gitignore`, CI que corre los tests.
  Mover `document-semantic-search/` a `legacy/`. Borrar `data/`, `logs/`, `temp/`
  duplicados en la raíz (residuo del bug D-02).
  *Acepta:* `pytest` corre y pasa; `ruff check` limpio; CI en verde.

- [x] **PR-01 `[N]` Configuración y CLI**
  `pydantic-settings`, rutas resueltas contra la raíz del paquete (no el CWD),
  `spectre --help` con los subcomandos vacíos.
  *Acepta:* la config se carga desde cualquier CWD y apunta siempre a la misma
  carpeta `data/`. Test explícito de eso (es el bug D-02).

- [x] **PR-02 `[N]` Esquema SQLite y repositorio**
  `schema.sql`, migraciones versionadas simples, `db/repo.py` con las
  operaciones de tomo/página/fallo.
  *Acepta:* crear la base, insertar un tomo y leerlo; test de idempotencia de la
  migración.

- [x] **PR-03 `[N]` Runner de jobs durable**
  Cola en SQLite, un solo proceso, estados y reintentos. Sin threads, sin
  control de recursos casero.
  *Acepta:* matar el proceso a mitad de un job y reanudarlo sin perder ni
  duplicar trabajo. Test que lo demuestre.

### Fase 1 — Del PDF al texto (4 PRs) · el corazón

- [x] **PR-04 `[N]` Extracción de texto y paginación oficial**
  Texto por página; detección del número de página oficial desde el encabezado;
  cálculo del offset del tomo.
  *Acepta:* sobre el Tomo 348, ≥95% de páginas con número detectado y un único
  offset (el valor medido es 6). Medido: 956/968 = 98,76%, offset 6, 0
  discrepancias.

- [x] **PR-05 `[N]` Limpieza de texto**
  Des-hifenado (`rese -\nñados` → `reseñados`), remoción de encabezados
  repetidos, normalización de versalitas (`caRLos FERnando RosEnkRantz`).
  *Acepta:* tests con casos reales tomados del Tomo 348; el conteo de palabras
  baja ~4,5% al des-hifenar una muestra.
  Medido: des-hifenado une 7.709 de 7.712 guiones de corte del cuerpo; la
  reducción es **2,3%**, no ~4,5% (el des-hifenado se verificó completo — ver
  bitácora PR-05). El cuerpo limpio queda en 330.840 palabras, a 0,65% de las
  332.999 que el plan fija para PR-11.

- [x] **PR-06 `[N]` Parser del índice de partes**
  Localiza el índice al final del tomo y extrae carátula → página.
  *Acepta:* 126 entradas en el Tomo 348, con las páginas dentro del rango.
  Medido: **129 carátulas / 133 referencias de página** (3 carátulas aparecen en
  varios fallos), páginas citadas de 1 a 955. La diferencia con el 126 no se
  forzó — hipótesis (referencias cruzadas del índice, p. ej. "Haras El Moro s/
  queja ... en Carol ...") y verificación en la bitácora PR-06; PR-07 debería
  cerrar el número al armar los fallos y chequear solapamientos.

- [x] **PR-07 `[N]` Segmentador de fallos**
  Del índice a los rangos de página; construcción de la cita `348:145`.
  Fallback por delimitadores si el índice no parsea.
  *Acepta:* 126 fallos, sin solapamientos, cubriendo de la página 1 a la 953.
  Dos trampas medidas: el fallo más largo ocupa **57 páginas** y es legítimo (el
  fallback no debe partirlo), y la mediana es de **4 páginas**.
  Medido: **133 fallos** (129 carátulas del índice, 3 en varios fallos), 0
  solapamientos, cobertura 1→956. **Más largo 57 y mediana 4 dan exactos** (el
  método está bien); el total arrastra el gap de PR-06 (126 vs 129), a cerrar en
  PR-08/09. El fallback corta por carátula en versalita, no por `FALLO DE LA
  CORTE` (sobre-parte, D-2), y no parte el fallo de 57 páginas. Ver bitácora
  PR-07.

### Fase 2 — Estructura del fallo (3 PRs)

- [ ] **PR-08 `[N]` Metadatos del fallo**
  Fecha, tipo de recurso, tribunal de origen, jueces firmantes, partes.
  *Acepta:* ≥90% de los 126 fallos con fecha y jueces; los que fallan quedan
  marcados, no inventados.

- [ ] **PR-09 `[N]` Secciones: mayoría, votos, disidencias**
  *Acepta:* un fallo con votos concurrentes conocido (p. 145 del Tomo 348) se
  parte en las secciones correctas. Ningún texto queda huérfano.

- [ ] **PR-10 `[V]` Extracción de citas**
  Regex sobre `Fallos: N:N`, tabla de relaciones fallo → fallo citado.
  *Acepta:* 887 citas detectadas en el Tomo 348.

### Fase 3 — Índice y búsqueda (5 PRs)

- [ ] **PR-11 `[N]` Chunker consciente de secciones**
  Nunca cruza el borde de D-4. Hereda cita, sección y página.
  *Acepta:* ningún chunk con texto de dos secciones. Referencia medida: el
  cuerpo del Tomo 348 des-hifenado tiene **332.999 palabras**, que a 400 palabras
  con 80 de solape dan **~1.041 chunks**. Un resultado muy lejos de ahí indica
  que la limpieza o la segmentación se rompieron.

- [ ] **PR-12 `[N]` Interfaz de embeddings + implementación local**
  `EmbeddingModel`, implementación con sentence-transformers, registro del
  modelo por chunk.
  *Acepta:* cambiar el modelo en la config y ver que el sistema identifica los
  chunks a reindexar sin tocar los PDFs.

- [ ] **PR-13 `[N]` Índice vectorial**
  LanceDB, escritura por lotes, reanudable.
  *Acepta:* indexar el Tomo 348 completo y recuperar el vecino más cercano de un
  chunk conocido.

- [ ] **PR-14 `[N]` Índice léxico**
  FTS5 configurado para español.
  *Acepta:* buscar `"artículo 14 de la ley 48"` devuelve los fallos correctos.

- [ ] **PR-15 `[N]` Búsqueda híbrida**
  Fusión RRF de las dos listas; filtros por año, tribunal y tipo de sección.
  *Acepta:* un set de 10 consultas de prueba escritas a mano, con el resultado
  esperado documentado en el repo.

### Fase 4 — Ingesta a escala (4 PRs)

- [ ] **PR-16 `[N]` Catálogo CSJN**
  Listar los tomos disponibles (número, volumen, año, id de la CSJN).
  **Empieza con un spike:** confirmar cómo se obtiene el PDF de un tomo antes de
  construir nada. Si no hay descarga programática, este PR entrega el catálogo y
  la subida manual cubre el resto.
  *Acepta:* catálogo con los 349 tomos y el año de cada uno.

- [ ] **PR-17 `[N]` Descargador**
  Reintentos, caché en disco por sha256, ritmo respetuoso con el servidor.
  *Acepta:* descargar 3 tomos, verificar hashes, reanudar una descarga cortada.

- [ ] **PR-18 `[N]` Sonda de calidad**
  Mide caracteres por página y clasifica el tomo en `digital` /
  `requiere_ocr`.
  *Acepta:* el Tomo 348 clasifica `digital`; un tomo anterior a 1950 clasifica
  `requiere_ocr` y **no** se indexa como si estuviera vacío.

- [ ] **PR-19 `[N]` Pipeline completo como job**
  descargar → extraer → limpiar → segmentar → estructurar → fragmentar →
  embeber → indexar, reanudable por etapa, con progreso consultable.
  *Acepta:* correr el pipeline sobre 2 tomos, cortarlo a la mitad, reanudarlo y
  terminar con el mismo resultado que una corrida limpia.

### Fase 5 — Interfaz (4 PRs)

- [ ] **PR-20 `[N]` Servidor y UI base**
  FastAPI sirviendo el estático; layout, navegación, estados vacíos honestos.
  *Acepta:* `spectre serve` levanta y abre el navegador.

- [ ] **PR-21 `[N]` Búsqueda y resultados**
  Campo de consulta, resultados con cita `Fallos: 348:145`, fragmento con el
  término resaltado, etiqueta de sección (mayoría / disidencia).
  *Acepta:* buscar y llegar al fragmento correcto en menos de 3 segundos sobre
  2 tomos indexados.

- [ ] **PR-22 `[N]` Vista del fallo**
  Texto completo por secciones, metadatos, citas salientes, enlace a la página
  del PDF original.
  *Acepta:* desde un resultado se llega al fallo completo y de ahí al PDF en la
  página correcta.

- [ ] **PR-23 `[N]` Biblioteca**
  Tomos disponibles, cuáles están indexados, cuáles requieren OCR, progreso de
  indexación, botón para indexar y para subir un PDF propio.
  *Acepta:* lanzar la indexación de un tomo desde la UI y ver el progreso.

### Fase 6 — Cierre del MVP (3 PRs)

- [ ] **PR-24 `[N]` Arranque de un comando**
  Script que crea el entorno, instala, baja el modelo y levanta Spectre.
  *Acepta:* en una máquina limpia, del clone a la primera búsqueda sin leer
  documentación.

- [ ] **PR-25 `[N]` Medición end-to-end**
  Tiempos reales de indexación por tomo, tamaño del índice, memoria pico.
  Extrapolación honesta a la colección completa.
  *Acepta:* una tabla de números medidos en `docs/qa/mediciones.md`.

- [ ] **PR-26 `[N]` Documentación de uso**
  README real y una guía corta escrita para una abogada, no para un dev.
  *Acepta:* alguien que no vio el proyecto puede instalarlo y buscar.

**Total: 27 PRs.**

---

## 7. Riesgos abiertos

**R-1. Los tomos antiguos son escaneos.** "Todo lo que se pueda bajar" abarca
1863–2026. El Tomo 348 es digital y limpio; un tomo de 1900 casi seguro no.
*Mitigación:* PR-18 clasifica y difiere. El MVP indexa lo digital y muestra la
cola de pendientes. OCR es un proyecto aparte, no un extra.

**R-2. El formato del índice y del encabezado cambia entre décadas.** Los
números verificados (126 entradas, offset 6, 98,8%) valen para el Tomo 348.
*Mitigación:* PR-07 tiene fallback por delimitadores —con la advertencia
medida de D-2: sobre-parte— y cada tomo que rompa el parser entra como caso de
regresión con su fixture. Si un tomo no tiene índice parseable, se marca
`segmentacion_dudosa` y se indexa igual a nivel página, en vez de fabricar
fallos falsos.

**R-3. La descarga programática puede no existir.** El listado de tomos usa
`verTomo?tomoId=N`; falta confirmar que eso entrega el PDF.
*Mitigación:* spike al inicio de PR-16. La subida manual ya está en el MVP, así
que el proyecto no depende de esto.

**R-4. El tiempo de indexación de la colección completa es desconocido.** No
tengo una medición, y estimarlo sin medir sería inventar.
*Mitigación:* PR-25 lo mide sobre 2 tomos y extrapola. El pipeline es reanudable
por diseño (PR-03, PR-19), así que puede correr de a tramos.

**R-5. Cambiar de modelo de embeddings obliga a reindexar.**
*Mitigación:* D-8. El texto limpio y los chunks quedan en SQLite; reindexar no
vuelve a abrir un PDF.

---

## 8. Fuera del MVP, en orden de valor

1. **Reranker** sobre los primeros 50 resultados. El salto de calidad más grande
   que queda.
2. **Sumarios oficiales de la CSJN**, consultables por tomo y página — encajan
   exactamente con la cita que ya extraemos.
3. **Grafo de precedentes** a partir de la tabla de citas (887 por tomo).
4. **OCR** de tomos antiguos.
5. **Análisis con IA** de los resultados (explicar relevancia, comparar fallos).
6. **Documentos privados** de clientes: cambia el modelo de amenaza, pide
   pensar cifrado y aislamiento.
7. **Multiusuario** y despliegue en servidor.

---

## 9. Estado

PR-00 y PR-01 cerrados (02/09/2026). PR-02 a PR-07 cerrados (03/09/2026).
Próximo: **PR-08**.
