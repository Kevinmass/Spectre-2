# Spike PR-C2 — Sumarios oficiales de la CSJN y sus voces

Fecha del recon: 07/09/2026. Sitio: Secretaría de Jurisprudencia de la CSJN,
`https://sjconsulta.csjn.gov.ar/`.

El plan (§6, PR-C2) pide arrancar con un spike que responda tres preguntas.
Respuestas cortas primero, el detalle después.

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | ¿Se pueden consultar los sumarios programáticamente? | **Sí.** Flujo HTTP de 3 pasos, público, sin credenciales. reCAPTCHA no se valida en este flujo. |
| 2 | ¿En qué formato vienen? ¿Hace falta OCR? | **JSON con texto seleccionable. No hace falta OCR.** El sumario y sus voces vienen como campos de un objeto JSON. |
| 3 | ¿Las voces vienen estructuradas? | **Sí.** Cada sumario trae `voces` como string separada por `" - "`; además hay un endpoint de autocompletado del tesauro (`getVoces`) que devuelve `{codigo, valor}`. |

---

## 1. El flujo de consulta

Backend Java (Stripes), búsqueda **stateful** en la sesión del servidor.

### Paso 1 — abrir sesión

```
GET https://sjconsulta.csjn.gov.ar/sjconsulta/consultaSumarios/consulta.html
```

Devuelve el HTML del buscador y setea dos cookies: `SJCONSULTASESSION` y `SRV`.
Sin este GET, el POST del paso 2 responde 500.

### Paso 2 — postear la búsqueda

```
POST /sjconsulta/consultaSumarios/buscar.html
Content-Type: application/x-www-form-urlencoded
(cookies del paso 1)

filter.fullText=&filter.terminos=T&filter.autos=&filter.fechaExacta=
&filter.fechaDesde=&filter.fechaHasta=&filter.tomo=348&filter.pagina=36
&g-recaptcha-response=
```

Guarda la búsqueda en la sesión y devuelve un HTML contenedor con
`var totalResultados = "N";`. **`g-recaptcha-response` va vacío**: el formulario
público tiene reCAPTCHA Enterprise (`render=6Lc9...`) pero el backend **no lo
valida en este endpoint** (confirmado: POST sin token → 200 con resultados).

Campos del form (todos presentes, como los manda el front):

| campo | qué es |
|---|---|
| `filter.fullText` | texto libre (3–4000 chars) |
| `filter.terminos` | modo del texto: `T` todas · `A` algunas · `E` frase exacta · `C` cercanas |
| `filter.autos` | carátula (≥3 chars) |
| `filter.fechaExacta` / `filter.fechaDesde` / `filter.fechaHasta` | `dd/mm/yyyy` |
| `filter.tomo` | **tomo de Fallos** (numérico) |
| `filter.pagina` | **página de inicio del fallo** (la de la cita `N:P`) |
| `filter.idsVocesElegidas` | (repetible) códigos de voz — el filtro por voz de C2b |
| `g-recaptcha-response` | vacío |

### Paso 3 — traer los resultados (JSON)

```
GET /sjconsulta/consultaSumarios/paginarSumarios.html?startIndex=0
Accept: application/json
(cookies)
```

Array JSON de sumarios, **10 por página**. Se itera `startIndex=0,10,20…` hasta
cubrir `totalResultados`.

### Autocompletado del tesauro de voces

```
POST /sjconsulta/autocomplete/getVoces.html
term=contrato administrativo
```

→ JSON `[{"codigoValor":1144,"valor":"CONTRATO ADMINISTRATIVO",...}, ...]`.
El `codigoValor` es lo que se manda en `filter.idsVocesElegidas`. El tesauro es
grande (con `term=a` devuelve ~2.350 entradas).

---

## 2. La forma del dato

Objeto de `paginarSumarios` (campos que importan; hay ~70 en total, el resto es
metadata de edición):

| campo | ejemplo (tomo 348, pág. 34) |
|---|---|
| `tomo` / `pagina` | `348` / `34` |
| `autos` | `"Recurso Queja N° 1 - ... GOBIERNO DE LA CIUDAD DE BUENOS AIRES s/INCIDENTE DE VERIFICACION DE CREDITO"` |
| `fechaString` | `"13/02/2025"` |
| `voces` | `"DEPOSITO PREVIO - INTERESES - RECURSO DE QUEJA"` |
| `texto` | `"El interés previsto en el art. 3 de la acordada 47/91 se devenga a partir de la fecha de interposición de la queja."` |
| `linkDocumento` | `"/documentos/verDocumentoByIdLinksJSP.html?idDocumento=8059511&cache=..."` |
| `analisisDocumental` | objeto anidado: `sentidoPronunciamiento`, `tipoRecurso`, `competencia`, `remision`, `materiaSecretaria`, `referenciasNormativas`, `votosAnalisisDocumental` (ministros, tipo de voto)… |

Observaciones:

- **Un fallo tiene varios sumarios.** `348:36` (Municipalidad de Villa Gesell)
  → **7 sumarios**, cada uno con su propia regla de doctrina y sus voces.
  `348:31` → 1. `349:1` → 2.
- **No todos los fallos tienen sumario.** `348:145` → `totalResultados=0`. La
  Secretaría sumaría una parte de los fallos.
- El `texto` viene con alguna etiqueta HTML suelta (`<br>`, `<i>`); se limpia
  con un strip de tags + unescape.
- `fechaString` es `dd/mm/yyyy`; se normaliza a ISO para casar con
  `fallos.fecha`.
- `autos` es la carátula **interna** de la Secretaría, con algún prefijo
  (`"Recurso Queja N° 1 - "`) que la nuestra (PR-08) no tiene. No se usa para
  cruzar: el cruce es por `tomo` + `pagina`, que es exacto.

---

## 3. El WAF

El sitio está detrás de un Web Application Firewall con firma por cliente. Un
`curl.exe` de Windows puede recibir 403 con una página "Web Application
Firewall" por su fingerprint TLS. **`urllib` de Python (stack TLS del sistema)
pasa** — verificado en esta sesión, el módulo `sumarios.py` corre con `urllib`
y los tests `red` pasan. Igual se mandan headers de navegador
(`User-Agent` Chrome, `Accept-Language`) y se respeta el flujo de cookies. El
cliente detecta la página del WAF en la respuesta y **revienta** en vez de
devolver vacío (regla del proyecto: ningún stub que reporte éxito).

---

## 4. Qué se entregó en PR-C2a (esta tanda de trabajo)

- **`spectre/corpus/csjn/sumarios.py`** — el cliente: `buscar_sumarios(tomo,
  pagina) -> list[Sumario]` (flujo de 3 pasos + bucle de paginación) y
  `buscar_voces(termino) -> list[Voz]`. `TransporteHTTP` es inyectable para los
  tests. No persiste nada (regla de dependencias).
- **`spectre csjn sumario <tomo> <pagina>`** — CLI que mide, no persiste
  (como `csjn catalog` / `pdf …`).
- **`tests/test_sumarios.py`** — parseo puro + bucle con transporte falso
  (siempre), y 3 tests `red` contra el sitio real.

## 5. Qué queda para PR-C2b

- Tabla(s) `sumarios` / `voces` (+ `fallo_voces`), migración.
- Traer los sumarios por fallo durante la ingesta (o un comando
  `spectre sumarios sync`) y persistirlos.
- `GET /api/fallos/{cita}` y los resultados de `/api/buscar` muestran el/los
  sumario(s) cuando existen.
- Filtro por voz en `/api/buscar` (`filtrar_chunks` o equivalente) + la UI
  (un input con autocompletado sobre el tesauro).
- El `analisisDocumental.materiaSecretaria` es la vía para el filtro por
  **materia / rama** que pidió la observación 01 — evaluarlo en C2b.

## Criterio de aceptación de PR-C2 (del plan)

> cada resultado muestra su sumario oficial cuando existe; se puede filtrar la
> búsqueda por al menos una voz y el conteo cambia.

**No se cumple con PR-C2a** (que es el spike + el cliente). Se cumple al cerrar
PR-C2b. La casilla de PR-C2 en `docs/plan-v2.md` queda sin marcar; se agrega
PR-C2b como continuación.
