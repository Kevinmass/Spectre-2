# Spectre v2 — Plan

> **Este archivo es la fuente de verdad y el estado del desarrollo de v2.**
> Se marca en el mismo commit que cierra cada PR.
> El plan del MVP está cerrado y archivado en
> `docs/planes_archivados/plan-spectre.md` (27/27 PRs).

Definido con Kevin el 05/09/2026, después de relevar el MVP terminado
levantando la interfaz real contra la base indexada real.

---

## 1. Cómo se ejecuta

Igual que el plan del MVP: **una sesión de Claude Code por PR, sin encadenar
dos**; cada PR cierra con `docs/qa/bitacora-<ID>.md` (qué hizo, qué decidió
por su cuenta, en qué se desvió, qué verificó y con qué comandos, qué dudas
quedaron); Kevin trae la bitácora al chat para el doble chequeo contra el
diff; la casilla se marca en el mismo commit.

`[N]` núcleo · `[V]` puede esperar

---

## 2. De dónde partimos

El MVP funciona y está bien construido: 5.748 LOC + 6.072 de tests (397 tests),
CI en verde, metadatos por fallo con buena cobertura (fecha 100%, jueces 91%,
tipo de recurso 87%, tribunal 81%), secciones con autor, y **la regla D-05 se
respetó** — sin `sentence-transformers` la búsqueda devuelve
`modo: "solo_lexico"` y lo dice en vez de simular.

Lo que el relevamiento encontró, medido sobre la base real (2 tomos, 286
fallos, 2.199 chunks):

| # | Problema | Evidencia |
|---|---|---|
| 1 | **Los resultados son fragmentos, no fallos** | 8 consultas → 80 resultados → **42 fallos distintos (52%)**. "daño moral": 10 resultados, 2 casos, 9 del mismo. `hybrid.py` no agrupa. |
| 2 | La API tiene filtros que la UI no muestra | `/api/buscar` acepta `anio`, `tribunal`, `seccion`, `k`, `solo_lexico`; en pantalla hay un campo de texto. |
| 3 | El resaltado marca ruido | `terminosDe()` conserva toda palabra >2 letras ("del", "por"); el regex no tiene límites de palabra ("sin" resalta "**sin**o"). |
| 4 | El fallo se lee como salió del PDF | Sin reflow de párrafos; vista de 9.311 px sin índice de secciones; extractos que empiezan a mitad de palabra. |
| 5 | La Biblioteca esconde el catálogo | Pide el número de tomo de memoria y el placeholder dice ``lo da `spectre csjn catalog` ``. Los 349 tomos del PR-16 son invisibles. |
| 6 | 5,3 GB de pico de memoria | Contra el criterio de "computadoras de bajos recursos". `extraer` es además el 56% de los 106 s por tomo. |

Pendientes chicos: la tabla `citas` tiene **0 filas** (el endpoint las extrae al
vuelo y nunca las persiste — al PR-10 le falta el último paso), y hay carátulas
mal parseadas por entradas de índice de dos líneas.

---

## 3. Decisiones nuevas

**D-13. Spectre pasa a ser un producto de Mirage.** Ya no es solo la
herramienta de una persona. Eso habilita identidad visual propia, primer uso
pensado, y pone multiusuario sobre la mesa.

**D-14. Nadie lo usó todavía, y eso se arregla antes de diseñar producto.**
La primera usuaria no lo tocó aún. Diseñar identidad y onboarding sin haber
visto a nadie buscar es exactamente cómo se construye la cosa equivocada con
mucha prolijidad. **PR-A0 es una sesión de observación y bloquea a toda la
Tanda B.** Los seis problemas de arriba son objetivos y se pueden arreglar sin
esperar (Tanda A); el diseño no.

**D-15. Identidad visual propia, sin cambiar de stack.** Sigue siendo vanilla
JS sin build: el proyecto no tiene la complejidad que justifique un framework,
y un build sumaría fricción a un producto que se instala. Lo que se construye
es un sistema visual — tipografía, paleta, jerarquía, estados — no un
reemplazo tecnológico.

**D-16. `PENDIENTE DE DECISIÓN` — el modelo de distribución.**
Esta es la decisión que reordena la Tanda D y hay que tomarla antes de
empezarla. El MVP asume instalación local por usuario, y esa premisa venía de
"procesamiento local por privacidad". **Para jurisprudencia pública esa premisa
no aplica**: los fallos de la Corte son públicos, no hay nada que proteger.

Como producto, la instalación local significa que cada abogado instala Python,
descarga un modelo de varios cientos de MB, y dedica ~106 s × 349 tomos de CPU
a indexar exactamente el mismo corpus público que ya indexó todo el mundo. El
índice compartido lo construye Mirage una vez y lo sirve. Lo local recién vuelve
a tener sentido cuando entren documentos privados de clientes.

Las dos opciones están en la Tanda D. No se empieza esa tanda sin cerrar esto.

**D-17. Spectre es multi-tribunal, no solo CSJN.** Decidido el 06/09/2026 a
partir de la observación 01: la primera usuaria pidió, sin que se le
preguntara, jurisprudencia de otras cortes (nombró el Tribunal Superior de
Justicia de Córdoba). Limitar el corpus a los Fallos de la CSJN limita a
cuántos abogados les sirve la herramienta. Esto **no** entra en la Tanda A ni
B —esas arreglan lo que ya hay—: es la Tanda E, y empieza con un spike de
fuentes. Refuerza D-16 hacia la Opción 1: mantener 349 tomos + N tribunales
provinciales sincronizados es trabajo de servidor, no de cada instalación.

---

## 4. Tanda A — Que los resultados sirvan

*El salto más grande por unidad de trabajo. Casi todo es backend ya construido
y probado que hay que exponer o corregir. No depende de ninguna decisión
pendiente: se puede empezar hoy.*

- [x] **PR-A0 `[N]` Sesión de observación con la primera usuaria**
  No es código. Sentarse a mirarla buscar cinco cosas que necesite de verdad,
  sin guiarla y sin explicarle la interfaz. Anotar dónde duda, qué escribe en
  el campo, qué esperaba que pasara al hacer clic, y qué preguntó.
  *Entrega:* `docs/qa/observacion-01.md`.
  *Bloquea:* toda la Tanda B.
  *Cerrado con una salvedad:* la devolución llegó como resumen, no como
  observación con registro en vivo. Los seis problemas del §2 no se
  confirmaron ni se descartaron; la Tanda B sigue sin validación de usuaria
  y conviene una segunda sesión con la plantilla antes de arrancar B1–B3.
  Lo que salió ya está incorporado al plan: año como rango en PR-A2, filtros
  por materia/rama vía PR-C2, filtro por tipo de parte en PR-C5, y el corpus
  multi-tribunal como D-17 + Tanda E. Detalle en `observacion-01.md` §8.

- [x] **PR-A1 `[N]` Agrupar los resultados por fallo**
  Un resultado = un caso, con sus pasajes anidados y un contador
  ("3 pasajes más en este fallo"). Toca `search/hybrid.py`, `/api/buscar` y el
  render. Conservar el mejor pasaje por tipo de sección, no solo el mejor
  absoluto: una mayoría y una disidencia del mismo fallo son cosas distintas.
  *Acepta:* las 8 consultas de referencia devuelven 10 fallos distintos cada
  una (hoy: entre 2 y 10, promedio 5,25).
  *Hecho:* módulo nuevo `search/agrupar.py` (no se tocó `hybrid.py` — la
  fusión quedó como estaba, agrupar es un paso aparte). Medido sobre la base
  real con las 8 consultas versionadas de PR-15
  (`docs/qa/consultas-PR-15.md`): antes 6,75 fallos distintos de media
  (5–9), después 10/10. `total_pasajes` alimenta el contador. Detalle en
  `docs/qa/bitacora-PR-A1.md`.

- [x] **PR-A2 `[N]` Filtros en la pantalla**
  Tribunal de origen, tipo de sección y "solo léxico" — el backend ya los
  acepta y los tiene testeados, esto es exponerlos. Más el año como **rango**
  (desde / hasta, o "últimos N años"): hoy `buscar_hibrido` toma `anio` como
  match exacto y la observación 01 pidió filtrar "por antigüedad", que es un
  rango. Ese es el único cambio de backend del PR.
  *Acepta:* filtrar por `seccion=disidencia` desde la UI y ver que el conteo
  cambia; acotar a un rango de años y ver que caen los de afuera; los filtros
  sobreviven a una nueva búsqueda.
  *Nota:* los filtros por materia / rama del derecho / tipo de parte que
  también pidió la observación 01 **no** entran acá —no hay dato para eso
  todavía—: salen de PR-C2 (materia/rama) y PR-C5 (tipo de parte).
  *Hecho:* fila de filtros en la pestaña Buscar (tribunal, sección, año
  desde/hasta, "solo texto"), que se reaplican al cambiarlos. Backend:
  `anio` → `anio_desde`/`anio_hasta` inclusivos en `filtrar_chunks`,
  `buscar_hibrido`, `/api/buscar` y `spectre search buscar`. El tribunal
  quedó como texto con match exacto (un picker necesita un endpoint de
  facetas — va con PR-B3/B4). Medido sobre la base real: sección 10→1,
  `anio_hasta=2010`→0. Detalle en `docs/qa/bitacora-PR-A2.md`.

- [x] **PR-A3 `[N]` Arreglar el resaltado**
  Lista de palabras vacías del castellano y límites de palabra en el regex.
  *Acepta:* buscar "despido sin causa" no resalta "sino"; buscar
  "responsabilidad del estado" no resalta "del".
  *Hecho:* `PALABRAS_VACIAS` en `spectre/web/app.js` (~130 función-palabras);
  `terminosDe` tokeniza con `\p{L}` (antes partía "acción" en "acci") y filtra
  vacías; `resaltarEn` usa lookarounds Unicode en vez de `\b` ASCII (anda con
  acentos: "café", "área"). Verificado con `node tests/verificar_resaltado.mjs`
  (las dos de aceptación + acentos + `estado`/`estados`). `_terminos` del
  backend (posiciona el extracto) tiene el mismo bug de vacías — lo agarra
  PR-A4. Detalle en `docs/qa/bitacora-PR-A3.md`.

- [x] **PR-A4 `[N]` Extractos que empiecen donde corresponde**
  Recortar en borde de palabra, y en borde de oración si hay uno cerca.
  *Acepta:* ningún extracto de las 8 consultas de referencia empieza a mitad
  de palabra.
  *Hecho:* `_extracto` en `spectre/api/app.py` recorta en borde de palabra y
  prefiere el comienzo de la oración que contiene el término (fin de oración =
  `.`/`?`/`!` + espacio + mayúscula, para no cortar en "art. 14"). `_terminos`
  filtra palabras vacías (`spectre/search/palabras_vacias.py`, gemela de la de
  `app.js`), así no centra el extracto en un "del". Medido sobre la base real:
  **0 de 95** extractos de las 8 consultas arrancan a mitad de palabra; 64/95
  arrancan en oración limpia. Detalle en `docs/qa/bitacora-PR-A4.md`.

- [x] **PR-A5 `[N]` Buscar por cita**
  `348:145`, `Fallos: 348:145` y `Fallos 348:145` abren ese fallo directo, sin
  pasar por la lista. Es como se busca jurisprudencia de verdad.
  *Acepta:* las tres formas resuelven al mismo fallo; una cita inexistente da
  un mensaje que dice qué pasó, no un 404 pelado.
  *Hecho:* `citaDe()` en `spectre/web/app.js` detecta la consulta con forma de
  cita (regex anclada, `tomo` 1-3 dígitos `:` `página` 1-4, con "Fallos"/":"
  opcionales) y la normaliza a `tomo:pagina`; el submit del buscador llama
  `mostrarFallo` en vez de `buscar`. Ante un 404, `mostrarFallo` muestra un
  mensaje ("no hay ningún fallo con la cita … puede que el tomo no esté
  cargado…") y un botón para buscarla como texto — no "(404 Not Found)".
  Verificado con `node tests/verificar_cita.mjs`. Detalle en
  `docs/qa/bitacora-PR-A5.md`.

- [x] **PR-A6 `[N]` Set de evaluación de búsqueda**
  20 consultas con el fallo esperado, versionadas en el repo, y un test que
  mide *recall@10* y *MRR*. **Sin esto no se puede decir si el reranker de la
  Tanda C mejora algo**, y tampoco si A1 rompió el ranking.
  *Entrega:* `docs/qa/eval-busqueda.md` con el número de partida.
  *Hecho:* `tests/fixtures/eval-busqueda.jsonl` (20 consultas + cita
  esperada), `tests/test_eval_busqueda.py` (`slow`, contra `data/spectre.db`)
  y `docs/qa/eval-busqueda.md`. **Línea de base (tomos 348+349): recall@10 =
  0,90 · MRR = 0,7125.** Dos consultas fallan hoy (previsional y una consulta
  penal de dos ejes) — candidatas a mejorar con PR-C3.

---

## 5. Tanda B — Que se lea, se navegue y se parezca a algo

*Bloqueada por PR-A0. Acá entra el rediseño.*

- [ ] **PR-B1 `[N]` Reflow de párrafos**
  Rearmar párrafos al limpiar, sin romper la numeración de considerandos
  (`1°)`, `2°)`) ni las firmas. **Se puede hacer sin recalcular embeddings**:
  el texto crudo por página ya está en SQLite (D-8).
  *Acepta:* un fallo conocido se lee sin cortes a mitad de oración; los
  considerandos siguen numerados; los chunks no cambian de cantidad de forma
  significativa.

- [ ] **PR-B2 `[N]` Vista de fallo navegable**
  Índice lateral de secciones, salto a la disidencia, medida de lectura
  acotada (~70 caracteres), y los pasajes que matchearon marcados en el texto.
  *Acepta:* desde un resultado se llega al pasaje exacto dentro del fallo, no
  al principio del documento.

- [ ] **PR-B3 `[N]` Sistema visual**
  Tipografía, paleta, jerarquía, estados (vacío, cargando, error, sin
  resultados) y el resultado como objeto de diseño: carátula clickeable,
  fecha, tribunal. Documentado en `docs/sistema-visual.md`.
  *Acepta:* ninguna cadena de la interfaz habla como un dev — se va
  `"10 resultado(s)."` y el placeholder con el comando de terminal.

- [ ] **PR-B4 `[N]` Biblioteca con catálogo**
  Los 349 tomos buscables por año, con estado, y selección múltiple para
  encolar varios. Separar "subir un documento propio" de la noción de tomo.
  *Acepta:* indexar un tomo sin saber su número de antemano.
  *Parche interino (fuera del plan, rama `fix-indexar-sin-csjn-tomo-id`,
  07/09/2026):* mientras el catálogo no esté en la UI, `POST
  /api/tomos/{n}/indexar` sin `csjn_tomo_id` devuelve **400** con un mensaje
  legible en vez de registrar un tomo que revienta en `descargar` (bug
  reportado). El id sigue habiendo que tipearlo a mano — eso lo resuelve este
  PR.

- [ ] **PR-B5 `[V]` Primer uso**
  Qué ve alguien que abre Spectre por primera vez y no tiene nada indexado.
  Hoy ve una tabla vacía y dos formularios.

- [ ] **PR-B6 `[N]` Más resultados, con paginación**
  Hoy la búsqueda muestra 10 fallos y no hay forma de ver más (el backend ya
  acepta `k` hasta 50 — `/api/buscar`, `Query(10, ge=1, le=50)`). Traer
  **hasta 20** y paginarlos de a 10, con un paginador **arriba y abajo** de la
  lista, de modo que al llegar al final —o al principio— se pueda saltar a la
  otra página sin scrollear de vuelta. Cambio de frontend (pedir `k=20`,
  partir la lista, render del paginador); el backend no se toca salvo subir el
  tope de `k` si 20 no alcanza.
  *No depende de PR-A0:* es mecánico, no una decisión de rediseño — se puede
  adelantar antes que B1–B5 (el estilo del paginador lo revisa PR-B3 cuando
  llegue).
  *Acepta:* una consulta con más de 10 fallos muestra el paginador; ir a la
  página 2 muestra los resultados 11–20; el paginador está tanto arriba como
  abajo de la lista y los filtros y la consulta sobreviven al cambio de
  página.

---

## 6. Tanda C — Que valga más

- [x] **PR-C1 `[N]` Persistir las citas y mostrar quién cita a quién**
  Terminar el PR-10: guardar en `citas` durante el pipeline y agregar las
  citas *entrantes*. Con dos tomos ya hay grafo; con veinte es una función
  que ningún buscador gratuito da.
  *Acepta:* 887 citas para el Tomo 348 en la tabla; un fallo muestra quién lo
  cita dentro del corpus indexado.
  *Hecho:* la etapa `estructurar` del pipeline corre `extraer_citas` (PR-10)
  sobre el `texto_del_fallo` y vuelca a `citas` una fila por precedente
  (`repo.insert_citas`, borrando antes las del fallo para que un reintento no
  duplique). Sin migración ni estado nuevo. `GET /api/fallos/{cita}` devuelve
  ahora `citas_entrantes` además de `citas_salientes` (`repo.citas_entrantes`
  cruza `tomo_citado` con el número de tomo y `pagina_citada` con el rango de
  páginas del fallo, excluye la auto-cita); la vista de fallo muestra "Citado
  por" con carátula + cita clickeable. Las salientes se leen de la tabla, con
  fallback al recálculo al vuelo para tomos indexados antes de PR-C1.
  *Salvedad del número:* el criterio dice "887 citas en la tabla", pero 887 es
  el conteo de *referencias* `Fallos:` (PR-10, `contar_referencias`); la tabla
  guarda una fila **por precedente citado**, así que el Tomo 348 da ~2.006
  filas (medido en PR-10). No se fuerza. Sobre el fixture chico
  (`tomo348_cuerpo_p31-40.pdf`, en la suite rápida) el pipeline persiste 8
  citas y el test lo fija. Detalle en `docs/qa/bitacora-PR-C1.md`.

- **PR-C2 `[N]` Sumarios oficiales de la CSJN — y las voces como filtro**
  La Secretaría de Jurisprudencia publica sumarios consultables por tomo y
  página — exactamente la clave que ya extraemos. Contenido curado por la
  Corte, gratis, que hace dos cosas: hace legible cada resultado **y** trae
  los descriptores ("voces") con los que la propia Corte clasifica cada
  fallo. Esas voces son la vía realista para los filtros por **materia y rama
  del derecho** que pidió la observación 01 (p. ej. "derecho administrativo",
  "contratación pública") — no hay que inventar una taxonomía, ya existe.
  *Acepta:* cada resultado muestra su sumario oficial cuando existe; se puede
  filtrar la búsqueda por al menos una voz y el conteo cambia.
  **Partido en dos por tamaño (07/09/2026):**

  - [x] **PR-C2a — spike + cliente de sumarios.**
    Spike (`docs/qa/spike-C2-sumarios.md`): los sumarios **sí** se consultan
    programáticamente, en un flujo HTTP de 3 pasos (GET sesión → POST
    `buscar.html` con `filter.tomo`/`filter.pagina` → GET `paginarSumarios`
    JSON); vienen como **JSON con texto seleccionable — no hace falta OCR**;
    las **voces vienen estructuradas** (string `" - "` por sumario, + un
    tesauro con autocompletado `getVoces` que da `{codigo, valor}`). Un fallo
    puede tener varios sumarios. Público, sin credenciales, reCAPTCHA no
    validado en ese flujo; WAF con firma de cliente que `urllib` pasa.
    *Entregado:* `spectre/corpus/csjn/sumarios.py` (`buscar_sumarios(tomo,
    pagina)`, `buscar_voces(termino)`; `TransporteHTTP` inyectable), el
    comando `spectre csjn sumario <tomo> <pagina>` (mide, no persiste), y
    `tests/test_sumarios.py` (parseo puro + `red` contra el sitio real).
    Detalle en `docs/qa/bitacora-PR-C2a.md`.

  - [ ] **PR-C2b — persistir + mostrar el sumario + filtro por voz.**
    Tabla(s) `sumarios`/`voces` (+ `fallo_voces`) con su migración; traer los
    sumarios por fallo en la ingesta (o un `spectre sumarios sync`) y
    persistirlos; `/api/fallos/{cita}` y los resultados de `/api/buscar`
    muestran el/los sumario(s); filtro por voz en `/api/buscar` + la UI (input
    con autocompletado sobre el tesauro). Evaluar `analisisDocumental.
    materiaSecretaria` para el filtro por materia/rama. **Acá se cumple el
    criterio de aceptación de PR-C2.**

- [ ] **PR-C5 `[N]` Filtro por tipo de parte**
  La observación 01 pidió filtrar por "las partes, p. ej. que una sea una
  empresa". Las partes ya se extraen por fallo (PR-08), pero como texto libre;
  falta clasificar su naturaleza: persona física / empresa / Estado /
  organismo público. Clasificación sobre los strings de partes (reglas +
  listas, o modelo si no alcanza), columna nueva, backfill del corpus
  indexado, y el filtro en `buscar_hibrido` + la UI.
  *Acepta:* filtrar "una parte es el Estado" y "una parte es una empresa"
  desde la UI y ver que el conteo cambia; medir la cobertura de la
  clasificación sobre el fixture (Tomo 348) y anotarla, no forzarla.

- [ ] **PR-C3 `[V]` Reranker sobre los primeros 50**
  Depende de PR-A6: sin el set de evaluación no hay forma de afirmar que
  mejoró.
  *Acepta:* recall@10 y MRR mejores que la línea de base, con el costo en
  segundos por consulta medido.

- [ ] **PR-C4 `[V]` Ingesta por lotes de páginas**
  Ataca el pico de 5,3 GB y el 56% del tiempo de una sola vez.
  *Acepta:* pico de memoria por debajo de 2 GB indexando el Tomo 348, con el
  mismo resultado que la corrida actual.

---

## 7. Tanda D — Producto

**No se empieza sin cerrar D-16.** Las dos opciones:

**Opción 1 — Índice compartido, Spectre hosteado.** Mirage indexa los 349
tomos una vez en un servidor y sirve la búsqueda por web. El usuario no
instala nada. Alineado con la infra que Mirage ya corre (Postgres en Render);
implica migrar el almacenamiento de SQLite+LanceDB a Postgres+pgvector, que la
capa `db/repo.py` ya aísla (D-12).

**Opción 2 — Instalación local, como hoy.** Cada usuario indexa su propia
copia. Tiene sentido solo si el corpus deja de ser público — es decir, si el
producto es "tus expedientes", no "la jurisprudencia".

Los PRs de esta tanda se escriben una vez elegida la opción.

---

## 8. Tanda E — Multi-tribunal

*Sale de D-17. El corpus deja de ser solo los Fallos de la CSJN. Es la tanda
más grande y la que más incertidumbre tiene: no se planifica en detalle hasta
tener el spike. Se cruza con D-16 (si el corpus es N tribunales, el índice
compartido deja de ser una opción y pasa a ser el único camino sensato).*

- [ ] **PR-E0 `[N]` Spike de fuentes**
  No es corpus todavía: es el relevamiento. Para el TSJ de Córdoba y para el
  agregador nacional (SAIJ / `datos.jus.gob.ar`), responder: qué tribunales y
  qué rango de fechas cubre cada fuente, en qué formato entrega (PDF
  seleccionable, PDF escaneado, HTML, JSON), si hay descarga masiva o API o
  sólo consulta de a uno, qué metadatos trae por fallo (fecha, sala, partes,
  voces), y bajo qué licencia. Comparar contra bajar PDFs corte por corte.
  *Entrega:* `docs/qa/fuentes-multitribunal.md` con una recomendación —
  fuente única normalizada vs. varias fuentes— y si hace falta OCR.
  *Bloquea:* al resto de la Tanda E.

- [ ] **PR-E1 `[N]` Abstraer "tomo" a "fuente"**
  Hoy la unidad de ingesta es el tomo de la CSJN y la cita es `N:N`. Generalizar:
  un fallo pertenece a una *fuente* (CSJN Fallos, TSJ Córdoba Sala Civil, …)
  con su propio identificador de cita, su propio parser de estructura y su
  propia forma de descargar. `corpus/csjn/` pasa a ser una implementación de
  una interfaz, no *la* implementación.
  *Acepta:* indexar un fallo de una fuente no-CSJN de punta a punta sin tocar
  el código de la fuente CSJN; la búsqueda y la vista de fallo funcionan
  igual para las dos.

- [ ] **PR-E2+ — según el spike.** Ingesta de la primera fuente provincial,
  ajuste del parser de citas para reconocer formatos no-CSJN, y la Biblioteca
  (PR-B4) mostrando fuentes además de tomos. El detalle se escribe con PR-E0
  cerrado.

*Nota de identidad:* con la Tanda E, "colección Fallos de la CSJN" en
`CLAUDE.md`, el `README` y el `<title>` deja de ser exacto. El cambio de
copy va con el primer PR de la tanda que toque UI, no antes.

---

## 9. Fuera de v2

Análisis con IA de los resultados y documentos privados de clientes: son
proyectos, no PRs, y ninguno mejora la experiencia de alguien que hoy busca
jurisprudencia.

OCR de tomos/fuentes escaneados sigue acá **por defecto**, pero puede entrar
antes si el spike de PR-C2 o el de PR-E0 encuentran que una fuente que
queremos sí o sí viene sólo como imagen. Esa decisión se toma con el número
del spike delante, no ahora. **El spike de PR-C2 (PR-C2a, 07/09/2026) ya
respondió por su lado: los sumarios de la CSJN vienen como JSON con texto
seleccionable, no disparan OCR.** Queda el spike de PR-E0.

---

## 10. Estado

Tanda A: **cerrada** (PR-A0 a PR-A6). Los resultados agrupan por fallo, hay
filtros (con año por rango), el resaltado y los extractos están limpios, se
busca por cita, y hay un set de evaluación con línea de base (recall@10 0,90 ·
MRR 0,71) para medir lo que venga.

En curso: **Tanda C.** La segunda sesión de observación no se pudo hacer
todavía, así que la Tanda B sigue esperando y se avanza por C (decidido con
Kevin el 07/09/2026). **PR-C1 cerrado** (citas). **PR-C2a cerrado**: spike de
sumarios + el cliente `spectre/corpus/csjn/sumarios.py` (los sumarios y sus
voces se consultan por tomo/página, JSON, sin OCR; detalle en
`docs/qa/spike-C2-sumarios.md`). Próximo a elección: **PR-C2b** (persistir el
sumario + mostrarlo + filtro por voz — cierra el criterio de PR-C2), PR-C5
(filtro por tipo de parte), o los `[V]` PR-C3 (reranker, ya tiene el set de
PR-A6) / PR-C4 (memoria de la ingesta).

Tanda B: bloqueada por PR-A0 en el papel, pero la observación 01 llegó como
resumen y no validó los seis problemas del §2 — conviene una segunda sesión
con registro en vivo antes de arrancar B1–B3. Excepciones que no dependen de
eso y se pueden adelantar: **PR-B1** (reflow de párrafos) y **PR-B6** (más
resultados con paginación).

Tanda C: **en curso**. PR-C1 y PR-C2a cerrados; PR-C2b / C5 / C3 / C4 sin
arrancar.

Tandas D, E: sin arrancar. D espera la decisión D-16. E arranca por
PR-E0 (spike) en cuanto se le quiera dar prioridad; D-17 ya está tomada.
