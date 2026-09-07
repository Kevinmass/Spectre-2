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

---

## 4. Tanda A — Que los resultados sirvan

*El salto más grande por unidad de trabajo. Casi todo es backend ya construido
y probado que hay que exponer o corregir. No depende de ninguna decisión
pendiente: se puede empezar hoy.*

- [ ] **PR-A0 `[N]` Sesión de observación con la primera usuaria**
  No es código. Sentarse a mirarla buscar cinco cosas que necesite de verdad,
  sin guiarla y sin explicarle la interfaz. Anotar dónde duda, qué escribe en
  el campo, qué esperaba que pasara al hacer clic, y qué preguntó.
  *Entrega:* `docs/qa/observacion-01.md`.
  *Bloquea:* toda la Tanda B.

- [ ] **PR-A1 `[N]` Agrupar los resultados por fallo**
  Un resultado = un caso, con sus pasajes anidados y un contador
  ("3 pasajes más en este fallo"). Toca `search/hybrid.py`, `/api/buscar` y el
  render. Conservar el mejor pasaje por tipo de sección, no solo el mejor
  absoluto: una mayoría y una disidencia del mismo fallo son cosas distintas.
  *Acepta:* las 8 consultas de referencia devuelven 10 fallos distintos cada
  una (hoy: entre 2 y 10, promedio 5,25).

- [ ] **PR-A2 `[N]` Filtros en la pantalla**
  Año, tribunal de origen, tipo de sección y "solo léxico". El backend ya los
  acepta y los tiene testeados; esto es exponerlos.
  *Acepta:* filtrar por `seccion=disidencia` desde la UI y ver que el conteo
  cambia; los filtros sobreviven a una nueva búsqueda.

- [ ] **PR-A3 `[N]` Arreglar el resaltado**
  Lista de palabras vacías del castellano y límites de palabra en el regex.
  *Acepta:* buscar "despido sin causa" no resalta "sino"; buscar
  "responsabilidad del estado" no resalta "del".

- [ ] **PR-A4 `[N]` Extractos que empiecen donde corresponde**
  Recortar en borde de palabra, y en borde de oración si hay uno cerca.
  *Acepta:* ningún extracto de las 8 consultas de referencia empieza a mitad
  de palabra.

- [ ] **PR-A5 `[N]` Buscar por cita**
  `348:145`, `Fallos: 348:145` y `Fallos 348:145` abren ese fallo directo, sin
  pasar por la lista. Es como se busca jurisprudencia de verdad.
  *Acepta:* las tres formas resuelven al mismo fallo; una cita inexistente da
  un mensaje que dice qué pasó, no un 404 pelado.

- [ ] **PR-A6 `[N]` Set de evaluación de búsqueda**
  20 consultas con el fallo esperado, versionadas en el repo, y un test que
  mide *recall@10* y *MRR*. **Sin esto no se puede decir si el reranker de la
  Tanda C mejora algo**, y tampoco si A1 rompió el ranking.
  *Entrega:* `docs/qa/eval-busqueda.md` con el número de partida.

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

- [ ] **PR-B5 `[V]` Primer uso**
  Qué ve alguien que abre Spectre por primera vez y no tiene nada indexado.
  Hoy ve una tabla vacía y dos formularios.

---

## 6. Tanda C — Que valga más

- [ ] **PR-C1 `[N]` Persistir las citas y mostrar quién cita a quién**
  Terminar el PR-10: guardar en `citas` durante el pipeline y agregar las
  citas *entrantes*. Con dos tomos ya hay grafo; con veinte es una función
  que ningún buscador gratuito da.
  *Acepta:* 887 citas para el Tomo 348 en la tabla; un fallo muestra quién lo
  cita dentro del corpus indexado.

- [ ] **PR-C2 `[N]` Sumarios oficiales de la CSJN**
  La Secretaría de Jurisprudencia publica sumarios consultables por tomo y
  página — exactamente la clave que ya extraemos. Contenido curado por la
  Corte, gratis, que hace legible cada resultado.
  *Empieza con un spike:* confirmar que se pueden consultar
  programáticamente antes de construir.

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

## 8. Fuera de v2

OCR de tomos antiguos, análisis con IA de los resultados, y documentos privados
de clientes. Los tres son proyectos, no PRs. Ninguno mejora la experiencia de
alguien que hoy busca jurisprudencia: el orden correcto es que las búsquedas
devuelvan casos antes de agregarles inteligencia.

---

## 9. Estado

Ningún PR de v2 arrancado. Próximo: **PR-A0** (observación) y **PR-A1**
(agrupar por fallo) — se pueden hacer en cualquier orden, A0 no bloquea la
Tanda A.
