# Bitácora PR-A5 — Buscar por cita

## Qué pedía el plan

> **PR-A5 `[N]` Buscar por cita.** `348:145`, `Fallos: 348:145` y `Fallos
> 348:145` abren ese fallo directo, sin pasar por la lista. Es como se busca
> jurisprudencia de verdad.
> *Acepta:* las tres formas resuelven al mismo fallo; una cita inexistente da
> un mensaje que dice qué pasó, no un 404 pelado.

## Qué se hizo — todo en `spectre/web/app.js`

- **`citaDe(consulta)`**: regex anclada
  `^\s*(?:fallos\s*:?\s*)?(\d{1,3})\s*:\s*(\d{1,4})\s*$` (case-insensitive).
  Devuelve `"tomo:pagina"` normalizado, o `null`. Acepta las tres formas del
  plan más variantes de espaciado y `fallos:` en minúscula / sin espacio.
  Rechaza cualquier cosa con letras u otra estructura ("daño moral", "280",
  "art. 348:145 y otros").
- **Submit del `#form-buscar`**: si `citaDe(consulta)` da algo, llama
  `mostrarFallo(cita, null)` (el flujo de la vista de fallo de PR-22) en vez
  de `buscar(consulta)`. Sin pasar por la lista.
- **`mostrarFallo`** ahora distingue el `404`:
  - `renderFalloNoEncontrado(contenedor, cita)` (helper nuevo) escribe un
    párrafo `.vacio` — "No hay ningún fallo con la cita Fallos: 348:145 entre
    lo que está indexado. Puede que ese tomo todavía no esté cargado, o que la
    cita no exista." — y un botón "Buscar «348:145» como texto" que vuelve a
    la pestaña Buscar y corre `buscar(cita)`.
  - Otros errores (500, red) siguen cayendo en el `catch` con
    `"No se pudo cargar el fallo (…)"`.
- El botón "← Volver a los resultados" del `#tab-fallo` ya estaba en el DOM;
  desde acá también sirve para salir de la pantalla de "no encontrado".

## Qué decidí por mi cuenta

- **La detección es del lado del navegador, no un modo nuevo de
  `/api/buscar`.** El plan dice "abren ese fallo directo, sin pasar por la
  lista": lo más directo es que el cliente reconozca la cita y pida
  `/api/fallos/{cita}` (que ya existe, PR-22), una sola llamada. Meter la
  lógica en `/api/buscar` agregaría un ida y vuelta y un `modo` extra sin
  ganar nada.
- **`tomo` de 1 a 3 dígitos, `pagina` de 1 a 4.** Los tomos de la CSJN van
  hasta ~350; las páginas de un tomo, hasta ~1.000 y algo. Con esas cotas,
  "1:1" es una cita válida (y si no existe, cae en el mensaje de no
  encontrado, que es el comportamiento correcto). Un número suelto como
  "280" (artículo 280) no tiene `:` y no dispara.
- **El fallback "buscar como texto"** no estaba pedido explícitamente, pero
  "un mensaje que dice qué pasó" queda cojo si no ofrece una salida. Correr
  `buscar("348:145")` hace una búsqueda léxica/híbrida por "348 999" — puede
  traer poco, pero es mejor que un callejón sin salida.
- **La cita no se normaliza contra la base** (no se prueba "348:34" ↔
  "348:034"): `get_fallo_por_cita` (PR-22) hace match exacto sobre lo que
  guardó el segmentador, y el segmentador no usa ceros a la izquierda. Si eso
  cambiara, habría que tocar las dos puntas.

## Qué verifiqué

- **`node tests/verificar_cita.mjs`** (nuevo; no lo corre pytest ni CI, igual
  que `verificar_resaltado.mjs` y los markers `slow`/`red`) — 15/15 ok:
  - `citaDe`: las tres formas del plan + `fallos:348:145`, `  348 : 145  `,
    `FALLOS:  348:145` → todas `"348:145"`.
  - `citaDe`: `"daño moral"`, `"280"`, `"responsabilidad del estado"`,
    `"art. 348:145 y otros"`, `"348"`, `""` → `null`.
  - `mostrarFallo("348:999")` con `fetch` devolviendo 404: el contenedor
    **no** muestra "404", dice "no hay ningún fallo", ofrece "como texto".
- **Contra la base real** (`data/spectre.db`): `/api/fallos/348:34` resuelve
  ("Gobierno de la Ciudad de Buenos Aires s/ incidente", 2 secciones);
  `/api/fallos/348:145` y `/api/fallos/348:99999` dan 404 con `detail` que
  incluye la cita — o sea, `348:145` del ejemplo del plan no es una cita real
  de este corpus (las citas son la página de **inicio** de cada fallo, y en
  el tomo 348 ninguno arranca en la 145). El backend 404 con `detail` ya está
  cubierto por `tests/test_api.py::test_fallo_detalle_cita_inexistente_da_404`.
- `node --check spectre/web/app.js` OK. `python -m pytest` → `394 passed`
  (sin cambios de Python). `ruff check .` / `format --check .` limpios.
- No lo abrí en un navegador real en esta sesión; el `vm` de node ejecuta el
  mismo `app.js` que sirve el servidor.

## En qué me desvié del plan

- Nada de alcance. Sumé el botón "buscar como texto" en la pantalla de "no
  encontrado" (el plan solo pide "un mensaje").

## Dudas que quedaron abiertas

- **"← Volver a los resultados"**: si se llegó por cita, no hay resultados
  atrás; el botón solo cambia de pestaña. El texto del botón queda un poco
  mentiroso en ese caso. Menor; lo puede pulir PR-B2 (vista de fallo
  navegable) o PR-B3 (sistema visual).
- **Sin historial / URL**: escribir una cita no cambia la URL, así que no se
  puede compartir el link ni usar "atrás" del navegador. Fuera del alcance de
  la Tanda A; si el producto se hostea (D-16 / Tanda D) esto se vuelve
  importante.
- **`citaDe` no reconoce rangos ni listas** ("348:145/150", "348:145 y
  349:20"). Es una cita simple o nada. Suficiente para el caso de uso.
