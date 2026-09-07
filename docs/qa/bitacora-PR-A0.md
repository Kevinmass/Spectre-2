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
