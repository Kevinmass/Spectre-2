# Bitácora PR-A0 — Sesión de observación con la primera usuaria

## Qué pedía el plan

> **PR-A0 `[N]` Sesión de observación con la primera usuaria.** No es código.
> Sentarse a mirarla buscar cinco cosas que necesite de verdad, sin guiarla y
> sin explicarle la interfaz. Anotar dónde duda, qué escribe en el campo, qué
> esperaba que pasara al hacer clic, y qué preguntó.
> *Entrega:* `docs/qa/observacion-01.md`. *Bloquea:* toda la Tanda B.

## Qué se hizo en esta sesión de Claude Code

- **`docs/qa/observacion-01.md`** (nuevo): el instrumento de la sesión —
  encuadre, reglas del observador, checklist de preparación, la plantilla
  de captura de las cinco búsquedas, sondas opcionales, línea de tiempo
  cruda, preguntas de cierre y la sección de síntesis que consume la
  Tanda B.

Esta sesión de Claude Code **no puede correr la observación**: eso lo hace
Kevin sentándose con la primera usuaria (la abogada, §0 del plan MVP). Lo
que entrega esta PR es el instrumento listo para usar, no los hallazgos.

## Qué decidí por mi cuenta

- **Dejar la casilla de PR-A0 sin marcar en `docs/plan-v2.md`.** El criterio
  de cierre del plan es la observación hecha, no el archivo creado. La
  casilla se marca cuando Kevin corra la sesión y llene los bloques
  `_(completar en la sesión)_` y la **Síntesis** de `observacion-01.md` —
  en un commit sobre esta misma rama, antes de mergear.
- **El instrumento no trae guion de búsquedas.** El plan dice "cinco cosas
  que necesite de verdad": las cinco búsquedas salen de una única pregunta
  de contexto sobre el caso real que la usuaria tenga entre manos ese día,
  no de una lista armada por mí. Meter consultas de ejemplo habría sesgado
  justamente lo que la sesión mide.
- **Las sondas opcionales están atadas a los seis problemas del §2**, pero
  con la condición explícita de usarlas solo si el tema surge solo. Es para
  poder cruzar la sesión contra el relevamiento sin plantar las
  conclusiones.
- **Sin datos personales.** El instrumento habla de "la primera usuaria" /
  "la usuaria"; el nombre no aparece, igual que en PR-26.
- No armé un formato de export ni un script: la síntesis de `observacion-01.md`
  ya está estructurada para que un PR de la Tanda B la cite por sección
  (8.1 fricciones → problema §2 → PR; 8.3 qué le pasa a la Tanda B).

## En qué me desvié del plan

- Nada de alcance. La única diferencia con "cerrar el PR" es que la casilla
  queda sin marcar hasta que exista la observación real; la entrega
  (`docs/qa/observacion-01.md`) está.

## Qué verifiqué

- Leí `spectre/web/index.html` y `spectre/web/app.js` para que el instrumento
  nombre lo que la usuaria va a ver de verdad: el placeholder
  `"Buscar en los fallos…"`, el aviso `"N resultado(s)."` y su variante de
  solo-léxico, el botón de cita `Fallos: N:N`, las etiquetas de sección
  (Mayoría / Voto / Disidencia / Dictamen), las pestañas Buscar / Biblioteca.
- Confirmé contra `app.js` que con `estado.chunks === 0` el campo de búsqueda
  queda `disabled` — de ahí el punto de la checklist de preparación: la
  sesión necesita la base real ya indexada, no una vacía.
- Los números de la base real (2 tomos, 286 fallos, 2.199 chunks) salen del
  §2 de `docs/plan-v2.md`.
- `ruff check .` y `pytest`: esta PR no toca código; la suite quedó como en
  la línea de base de la rama (`378 passed`).

## Dudas que quedaron abiertas

- **Una sola usuaria alcanza para PR-A0** según el plan. Si la sesión deja
  dudas de si un hallazgo es de ella o del producto, puede hacer falta una
  segunda observación antes de destrabar la Tanda B — queda a criterio de
  Kevin al llenar la síntesis (§8.3).
- El instrumento asume que la usuaria trae un caso real ese día. Si no tiene
  ninguno entre manos, hay que reagendar: buscar sobre un caso inventado no
  sirve para esto.

---

## Cierre (sesión hecha)

Kevin corrió la observación y trajo la devolución al chat como **resumen de
conclusiones**, no como registro en vivo (sin búsqueda por búsqueda, sin
transcripción textual, sin línea de tiempo).

### Qué se hizo en el cierre

- `docs/qa/observacion-01.md`: se completó §7 (cierre) y §8 (síntesis) con lo
  que devolvió la usuaria; §3, §4 y §6 quedan como plantilla para una próxima
  observación con registro en vivo, con una nota explícita de por qué no se
  llenaron. Encabezado actualizado al estado "sesión hecha, registrada como
  resumen".
- `docs/plan-v2.md`: casilla de PR-A0 marcada `[x]` con una salvedad, **y los
  cambios que la observación abrió, ya decididos con Kevin en el chat**:
  - **§3 D-17** (nueva): Spectre es multi-tribunal. Limitar a CSJN limita a
    cuántos abogados les sirve. Refuerza D-16 hacia el índice compartido.
  - **§4 PR-A2**: se le suma el año como rango; se aclara que
    materia/rama/tipo-de-parte no entran acá.
  - **§6 PR-C2**: re-scope — los sumarios oficiales también son la fuente de
    los filtros por materia / rama (voces de la Secretaría). El spike suma
    ver el formato (PDF seleccionable vs. escaneado → ¿OCR?).
  - **§6 PR-C5** (nuevo): filtro por tipo de parte (persona / empresa /
    Estado / organismo) sobre `partes`.
  - **§8 Tanda E — Multi-tribunal** (nueva): PR-E0 spike de fuentes
    (`docs/qa/fuentes-multitribunal.md`), PR-E1 abstraer "tomo" → "fuente",
    PR-E2+ según el spike. Renumeró "Fuera de v2" a §9 y "Estado" a §10.
  - **§9 Fuera de v2**: OCR sigue por defecto afuera, pero puede adelantarse
    si el spike de C2 o E0 encuentra una fuente que sólo viene escaneada.

### Qué devolvió la usuaria (resumen)

- "El programa funciona bien." Ninguna objeción de que algo esté roto o sea
  confuso — todas las objeciones son de **alcance**.
- **Más filtros de búsqueda:** por tribunal, por antigüedad, por rama del
  derecho (ej. derecho administrativo), por tema/materia (ej. contratación
  pública), por tipo de parte (ej. que una parte sea una empresa).
- **Corpus multi-tribunal:** además de los Fallos de la CSJN, fallos de otras
  cortes — nombró el Tribunal Superior de Justicia de Córdoba.

### Qué decidí por mi cuenta en el cierre

- **No fabriqué el detalle que no existe.** El §2 del plan (los seis
  problemas de UX) no se confirmó ni se descartó porque la usuaria no habló
  de eso; lo dejé dicho así, sin inventar fricciones. La Tanda B queda
  marcada como "sin validar con usuaria".
- **Separé el resumen crudo (§7-§8.4) de los cambios al plan (§8.5).** El
  primer commit de esta rama sólo marcó la casilla y anotó la salvedad; los
  cambios de estructura (D-17, Tanda E, re-scope de C2, PR-C5, rango en A2)
  se aplicaron en un segundo commit, después de que Kevin los aprobara uno
  por uno en el chat. §8.5 quedó como registro de qué se decidió y por qué.
- **Corregí el supuesto "son QoL, no suma trabajo"** en la síntesis: vale
  para filtrar por tribunal y por antigüedad (el backend ya tiene el dato);
  no vale para rama / materia / tipo de parte (no hay dato estructurado) ni
  para multi-tribunal (rehace la ingesta).
- **Spike de fuentes de otras cortes:** hice un primer barrido web (está en
  §8.2.B de `observacion-01.md`) — Poder Judicial de Córdoba publica PDFs
  anuales de la Sala Civil y Comercial del TSJ; SAIJ / datos.jus.gob.ar es
  el candidato más fuerte para un corpus multi-jurisdicción normalizado.
  No es una investigación cerrada, es de dónde seguir.

### Qué verifiqué

- Los filtros que `spectre/search/hybrid.py::buscar_hibrido` soporta hoy:
  `anio`, `tribunal_origen`, `tipo_seccion` (parámetros de la función, líneas
  66-68). De ahí sale qué pedido es "exponer" y cuál es "dato nuevo".
- `spectre serve` / `app.js`: el buscador queda `disabled` con
  `estado.chunks === 0` — la sesión necesitaba la base real, se asume que
  Kevin la usó así.
- Búsquedas web (2026-09): jurisprudencia TSJ Córdoba y SAIJ jurisprudencia
  provincial — resultados y límites anotados en §8.2.B.

### Dudas abiertas

- **D-17 ya está tomada** (multi-tribunal), pero la elección de fuente —SAIJ /
  `datos.jus.gob.ar` como agregador normalizado vs. bajar PDFs corte por
  corte— no: eso lo resuelve PR-E0 (spike) con los números delante.
- **OCR**: si el spike de PR-C2 (sumarios) o el de PR-E0 encuentra que una
  fuente que queremos sí o sí viene sólo escaneada, OCR se adelanta desde
  "fuera de v2". No se decide ahora.
- **La Tanda B necesita todavía una observación con registro en vivo.** Este
  cierre no la sustituye — la observación 01 validó pedidos de alcance, no
  los seis problemas de UX del §2.
