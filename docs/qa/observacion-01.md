# Observación 01 — Primera usuaria buscando jurisprudencia

> **Estado: sesión hecha. Registrada como resumen, no con la plantilla en
> vivo.** Kevin observó a la primera usuaria y trajo la devolución como un
> resumen de conclusiones (no búsqueda por búsqueda, sin transcripción
> textual ni línea de tiempo). Lo que sí quedó claro está en la **Síntesis
> (§8)**; §4 y §6 no se pudieron completar con este formato y quedan como
> plantilla para una próxima observación. La casilla de PR-A0 en
> `docs/plan-v2.md` se marca con este archivo.
>
> **Límite de esta observación:** ninguno de los seis problemas del §2 del
> plan apareció en la devolución —ni confirmado ni desmentido—. La usuaria,
> sin que se le preguntara, fue directo a *qué se puede filtrar* y *qué
> corpus hay*. La Tanda B sigue sin validación de usuaria (ver §8.3).

Corresponde a **PR-A0** del plan v2 (§4). No es código: es sentarse a mirar a
la primera usuaria buscar cinco cosas que necesite de verdad, sin guiarla y
sin explicarle la interfaz. Bloquea a toda la Tanda B: el rediseño no arranca
hasta tener esto.

---

## 1. Por qué esta sesión

El MVP está terminado y **nadie lo usó todavía** (D-14). El relevamiento del
§2 encontró seis problemas mirando la base y el código, no mirando a una
persona. Esta sesión sirve para dos cosas:

1. **Confirmar o descartar** que esos seis problemas son los que de verdad
   frenan a alguien buscando —y con qué prioridad relativa.
2. **Encontrar lo que el relevamiento no vio**: fricciones que solo aparecen
   cuando alguien con un caso real entre manos se sienta a buscar.

Lo que **no** es: una demo, una validación de que "está bueno", ni una
sesión de feedback sobre el diseño. No hay diseño nuevo todavía —
justamente sale de acá.

---

## 2. Reglas del observador

- **No guiar.** Nada de "probá escribir tal cosa" ni "el botón está arriba a
  la derecha". Si se traba, se anota que se trabó y cuánto tardó en salir
  sola —o si no salió.
- **No explicar la interfaz.** Si pregunta "¿esto qué hace?", devolver la
  pregunta: "¿qué esperás que haga?". Explicar recién al final.
- **No defender el diseño.** Si dice "esto no se entiende", anotarlo tal
  cual, sin justificar por qué está así.
- **Pedir que piense en voz alta.** Al principio: "contame lo que vas
  pensando mientras lo usás, aunque parezca obvio". Recordarlo si se queda
  callada mucho rato.
- **Bancar el silencio.** Si duda 20 segundos frente a la pantalla, dejar
  que dure. Ese silencio es el dato.
- **Anotar textual.** Las frases de la usuaria van entre comillas y con sus
  palabras, no parafraseadas ("esto es un choclo de texto", no "le pareció
  extenso").

---

## 3. Antes de empezar

- [ ] `spectre serve` levantado contra la base real ya indexada (los 2 tomos,
      286 fallos, 2.199 chunks del relevamiento). **No** una base vacía: si
      arranca sin nada indexado, la pestaña Buscar está deshabilitada y no
      hay nada que observar.
- [ ] Navegador limpio, pestaña única, en una pantalla que Kevin también
      vea (o compartida).
- [ ] Con qué registrar: grabación de pantalla si la usuaria acepta (pedir
      permiso explícito); si no, dos personas —una maneja, otra anota— o
      Kevin anotando en vivo en este archivo.
- [ ] Una sola pregunta de contexto antes de tocar nada, anotada abajo:
      *¿qué caso o consulta tenés entre manos ahora, en el trabajo real?*
      De ahí salen las cinco búsquedas; no se inventan.

**Contexto de la usuaria** — no registrado. La devolución llegó como resumen
posterior; no se anotó el caso puntual que trajo ni cómo lo resolvería hoy
sin Spectre.

---

## 4. Las cinco búsquedas

> **No se capturó búsqueda por búsqueda en esta sesión.** La usuaria
> devolvió conclusiones, no una traza de uso. El detalle que sí quedó está
> en §8. La plantilla de abajo queda para la próxima observación —conviene
> una, con registro en vivo, antes de arrancar el rediseño de la Tanda B.

No hay guion. Se le pide: **"buscá cinco cosas que necesitarías para ese
caso"**, y se la deja. Una plantilla por búsqueda; llenar durante o
inmediatamente después de cada una.

### Búsqueda _N_ _(repetir el bloque 5 veces)_

- **Qué quería encontrar** (en sus palabras):
- **Qué tecleó, literal, en el campo** ("Buscar en los fallos…"):
- **Qué esperaba que pasara** al apretar Buscar / Enter:
- **Qué pasó** (nº de resultados que devolvió, el aviso que mostró —
  `"N resultado(s)."` o el de solo-léxico):
- **Qué hizo con los resultados**: ¿leyó el extracto?, ¿clickeó la cita
  `Fallos: N:N`?, ¿abrió el fallo completo?, ¿fue al PDF?, ¿volvió y
  reformuló?
- **Dónde dudó** y cuántos segundos (aprox.):
- **Qué preguntó** (textual):
- **Frase / gesto de frustración o alivio** (textual):
- **¿Encontró lo que buscaba?** sí / no / a medias — y cómo se dio cuenta:

---

## 5. Sondas opcionales

Solo si el tema surge **solo**, para no plantar ideas. No preguntar las que
la usuaria no rozó.

- Si mira un resultado y parece confundida sobre qué es: *"¿esto que ves es
  un caso o un pedacito de un caso?"* (problema §2.1 — fragmentos, no
  fallos).
- Si repite resultados del mismo fallo: *"¿estos son distintos o el mismo?"*.
- Si menciona una fecha, un tribunal, "solo de la Corte", "de tal año":
  *"¿cómo harías para pedir solo eso?"* (problema §2.2 — filtros ocultos).
- Si el resaltado la distrae o marca palabras de más: *"¿lo resaltado te
  sirve?"* (problema §2.3).
- Si dice un número tipo "331:1234" o "Fallos 340:...": *"¿probarías
  pegarlo en el buscador?"* (problema §2 / PR-A5 — buscar por cita).
- Si abre un fallo y hace scroll largo: *"¿cómo encontrás la parte que te
  interesa acá adentro?"* (problema §2.4 — lectura cruda).
- Si va a la pestaña Biblioteca: *"¿qué esperabas encontrar acá?"*
  (problema §2.5 — catálogo escondido).

---

## 6. Línea de tiempo cruda

Sin registro en bruto en esta sesión (ver nota del §4). Plantilla para la
próxima:

| min | qué pasó | palabras de la usuaria |
|-----|----------|------------------------|
|     |          |                        |

---

## 7. Cierre

Reconstruido del resumen de Kevin. `[textual]` = palabras de la usuaria;
`[inferido]` = lectura de Kevin / mía sobre lo que dijo.

1. **¿Qué te faltó?** — Más maneras de filtrar la búsqueda: por qué tribunal
   dictó el fallo, por si es de derecho administrativo, por antigüedad, por
   tema (ejemplo que dio: *contratación pública*) y por las partes (ejemplo:
   *que una de las partes sea una empresa*). Y que el corpus no sea sólo el
   "rejunte de fallos que recopila la Corte Suprema": pidió sumar fallos de
   otras cortes, nombró el **Tribunal Superior de Justicia de la Provincia
   de Córdoba**.
2. **¿Lo volverías a abrir?** — `[inferido]` Sí. Dijo que "el programa
   funciona bien"; las objeciones fueron todas de alcance, no de que algo
   estuviera roto o fuera confuso.
3. **¿Qué esperabas que estuviera y no estaba?** — Los filtros del punto 1 y
   jurisprudencia de tribunales fuera de la CSJN.

---

## 8. Síntesis

### 8.1 Lo que pidió la usuaria

No hubo fricciones observadas (no se registró el uso). Lo que hubo fue una
lista de faltantes. Ordenada por lo que cuesta darla, no por impacto —el
impacto relativo no se midió:

| # | Pedido | ¿Hay dato hoy? | Esfuerzo | Dónde cae |
|---|--------|----------------|----------|-----------|
| 1 | Filtrar por **tribunal de origen** | Sí — `tribunal_origen` ya se extrae y `buscar_hibrido` ya filtra por él | Bajo — es exponerlo en la UI | **PR-A2**, tal cual está escrito |
| 2 | Filtrar por **antigüedad** | Parcial — hay `anio`, pero es match exacto | Bajo-medio — pasar `anio` a rango / "últimos N años" en backend + UI | **PR-A2**, con alcance ampliado |
| 3 | Filtrar por **tipo de parte** (p. ej. "una es una empresa") | Parcial — `partes` se extraen por fallo (PR-08), pero no su naturaleza (persona / empresa / Estado / organismo) | Medio — clasificar entidades sobre los strings de partes, columna nueva, backfill | PR nuevo (Tanda C) |
| 4 | Filtrar por **área del derecho** (p. ej. "derecho administrativo") | No — nada clasifica los fallos por rama | Alto — taxonomía + clasificación + columna + backfill | PR nuevo, o re-scope de **PR-C2** |
| 5 | Filtrar por **tema / materia** (p. ej. "contratación pública") | No como faceta estructurada — hoy eso lo hace, difuso, la búsqueda semántica | Alto — misma ruta que #4; la vía realista son los **sumarios oficiales con "voces"** de la CSJN (PR-C2) | Re-scope de **PR-C2** |
| 6 | **Corpus multi-tribunal** (TSJ Córdoba y otras) | No — todo el pipeline es CSJN-específico | Muy alto — es un proyecto, no un PR | Decisión nueva (ver §8.2) |

**Nota sobre "son QoL, no debería sumar mucho trabajo":** vale para #1 y #2.
Del #3 al #6 no: #3–#5 necesitan datos que hoy no existen (clasificación de
partes, de rama, de materia), y #6 rehace la ingesta. Ver §8.2.

### 8.2 Hallazgos que el relevamiento no tenía

- **A) La batería de filtros que la usuaria quiere es más rica que la que el
  backend soporta.** Hoy `buscar_hibrido` filtra por `anio`, `tribunal_origen`
  y `tipo_seccion`. El §2.2 del plan ("la API tiene filtros que la UI no
  muestra") daba por hecho que exponer esos tres alcanzaba. Esta sesión dice
  que no: los filtros que una abogada usa para acotar jurisprudencia son
  **materia, rama del derecho y tipo de parte**, y ninguno existe como dato
  estructurado. La ruta más barata hacia materia/rama son los **sumarios
  oficiales de la CSJN (PR-C2)**, que traen descriptores ("voces") curados
  por la Secretaría de Jurisprudencia — conviene re-mirar PR-C2 no sólo como
  "texto legible por resultado" sino como **la fuente de las facetas de
  filtro**.

- **B) La usuaria quiere jurisprudencia que no es de la CSJN.** Nombró el
  Tribunal Superior de Justicia de Córdoba. Esto no está en el plan v2 —ni en
  la Tanda D, ni en "fuera de v2"— y **cambia qué es Spectre**: hoy el
  `CLAUDE.md`, el `README` y el `<title>` dicen "colección Fallos de la
  CSJN". Todo el pipeline lo asume: la unidad es el *tomo*, la cita es
  `N:N`, `csjn/catalog` + `csjn/download` bajan del sitio de la Corte, el
  `index_parser` lee el índice de un tomo Fallos. Otra corte = otra unidad,
  otro formato de cita, otra fuente, quizá sin PDF (una base de búsqueda).
  Es tier "proyecto", como OCR o documentos privados (§8 del plan).

  **Spike de fuentes (primer barrido, sin verificar a fondo):**
  - **Poder Judicial de Córdoba** publica compilaciones de jurisprudencia de
    la **Sala Civil y Comercial del TSJ** en PDF, por año (2015–2024), con
    datos del caso + sumario + enlace a la resolución completa. Es el
    análogo más cercano a "Fallos": PDFs anuales curados. Limitación: sólo
    Sala Civil y Comercial — **no** Penal ni Contencioso-Administrativo, que
    es justo lo que "derecho administrativo" (pedido #4) necesitaría.
  - **`jurisprudencia.justiciacordoba.gob.ar`** — base tipo Koha, búsqueda
    uno por uno, descarga el PDF de cada fallo; sin API ni descarga masiva
    evidente (bloquea bots).
  - **SAIJ / `datos.jus.gob.ar`** (Ministerio de Justicia) — agregador
    nacional, 900k+ documentos, jurisprudencia nacional **y provincial**,
    actualización diaria, buscador de jurisprudencia provincial. El portal
    de datos abiertos tiene datasets en CSV/JSON (los visibles son sobre
    todo *normativa* provincial; falta confirmar si hay dump de
    jurisprudencia). **Candidato más fuerte** para un corpus
    multi-jurisdicción ya normalizado — amerita spike propio.
  - Referencia: proyecto abierto `Probanza-ar/mcp-legal-ar` (conectores a
    ~15 fuentes jurídicas argentinas) como mapa de qué hay y cómo lo bajan
    otros.

### 8.3 Qué le pasa a la Tanda B

- **Se confirma tal cual:** nada con evidencia directa. La usuaria no tocó
  —en su devolución— lectura de fallo, resaltado ni agrupación de
  resultados. B1/B2/B3 siguen apoyados sólo en el relevamiento del §2.
- **Cambia de prioridad:** **PR-A2 sube** — era "exponer lo que ya existe";
  ahora es lo primero y único de lo ya planeado que la usuaria pidió
  explícitamente. Se le agrega alcance (año como rango).
- **Se descarta o recorta:** nada todavía. Hace falta la observación en vivo
  para saber si B1–B3 pegan.
- **Aparece algo nuevo:** **PR-B4 (Biblioteca con catálogo)** se cruza con el
  pedido multi-tribunal — si entran otras fuentes, "Biblioteca" deja de ser
  "tomos de la CSJN" y su diseño tiene que preverlo.
- **Pendiente fuerte:** la Tanda B **sigue sin validar con usuaria**. Este
  resumen no reemplaza la sesión de observación en vivo. Conviene correr una
  con la plantilla (§4/§6) antes de arrancar B1–B3.

### 8.4 ¿Algo de esto es urgente para la Tanda A?

- **PR-A2:** subir prioridad y ampliar alcance a **rango de años** (no sólo
  match exacto). Es lo único de la Tanda A que la usuaria tocó.
- Los pedidos #3–#5 (parte, rama, materia) **no entran en A2 como está
  escrito** (A2 = exponer filtros que ya existen). Necesitan PR propio o
  re-scope de PR-C2 — decisión de planificación, no de la Tanda A.

### 8.5 Cambios propuestos al plan v2

Para discutir antes de tocar `docs/plan-v2.md`:

1. **PR-A2** — ampliar el criterio: además de exponer `tribunal` / `sección`
   / `solo léxico`, pasar el filtro de año a **rango**.
2. **PR-C2** — re-scope explícito: los sumarios oficiales no son sólo texto
   legible por resultado, son **la fuente de los filtros por materia / rama
   del derecho** (voces de la Secretaría de Jurisprudencia).
3. **PR nuevo (Tanda C)** — clasificar el **tipo de parte** (persona /
   empresa / Estado / organismo) sobre `partes`, y exponerlo como filtro.
4. **Decisión nueva (¿D-17?)** — *¿Spectre es sólo CSJN o multi-tribunal?*
   Igual que D-16, se decide antes de planificar los PRs que dependen. Si la
   respuesta es "sí, multi-tribunal", entra un spike de fuentes (SAIJ vs.
   PDFs provinciales) como primer paso.

---

## 9. Registro de la sesión

- Fecha: _(completar — Kevin)_
- Formato: resumen traído por Kevin al chat, no observación con registro en
  vivo.
- Quién observó: Kevin.
- Usuaria: la primera usuaria (la abogada, §0 del plan MVP).
- Base usada: _(completar)_ — se asume la base real ya indexada (2 tomos).
