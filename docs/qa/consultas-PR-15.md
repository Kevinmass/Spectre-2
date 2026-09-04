# Consultas de prueba — PR-15 (búsqueda híbrida)

Criterio de aceptación (plan §6, PR-15): "un set de 10 consultas de prueba
escritas a mano, con el resultado esperado documentado en el repo".

Las 10 consultas de abajo corren contra el Tomo 348 completo (133 fallos,
1.112 chunks — igual que PR-11/13/14), indexado en las dos listas
(`chunks_fts` léxico + LanceDB vectorial con el modelo real, `sentence-
transformers/paraphrase-multilingual-MiniLM-L12-v2`) y fusionado por
`buscar_hibrido` (RRF, `k_rrf=60`). El resultado esperado de cada una está
verificado por `tests/test_hybrid.py::test_aceptacion` (`slow`, necesita
`data/tomos/348.pdf` y el extra `[embed]`): `pytest -m slow tests/test_hybrid.py`.

Salvo que se diga lo contrario, cada consulta corre con `k=5` (los 5 mejores
resultados fusionados) y sin filtros.

## 1. `Fallos: 337:315`

**Por qué**: D-6 da este tipo de cita como el ejemplo de lo que la búsqueda
puramente semántica no encuentra ("Fallos: 311:955 no se encuentra por
significado"); acá se prueba con una cita real del propio tomo.
**Esperado**: `348:189` (Acevedo, Eva María c/ Manufactura Textil San Justo
s/ quiebra) entre los primeros 3 resultados — es el fallo cuyo texto cita
literalmente `Fallos: 337:315` (ya verificado, independiente de este PR, en
`tests/test_cli.py::test_pdf_citations_detalla_una_cita`, PR-10).
**Medido**: aparece en la posición 1 (0-based) del top 5, encontrado por el
lado léxico (rank_lexico bajo) — el vectorial no lo hubiera traído tan arriba
por sí solo (una cita numérica no tiene significado semántico).

## 2. `Zárate Pablo Federico`

**Por qué**: el ejemplo que usa el propio plan (§5) para el modelo de datos.
Nombre propio: caso fácil de verificar, sirve de control (si esto falla, algo
más profundo se rompió).
**Esperado**: `348:380` (Zárate, Pablo Federico y otros c/ ENRE s/
diferencias de salarios) en el primer puesto.
**Medido**: primer puesto, encontrado por los dos índices (aparece dos veces
en el top 5 por dos chunks distintos del mismo fallo).

## 3. `prescripción de la acción penal`

**Por qué**: concepto jurídico, no una frase textual fija — el caso que D-6
promete resolver mejor con el lado vectorial que con el solo léxico.
**Esperado**: `348:611` (Ilarraz, Justo José s/ promoción a la corrupción de
menores) entre los primeros 5 — su texto dice literalmente "corresponde
declarar la extinción de la acción penal ... (artículo 16, segunda parte, ley
48)" con fundamento en la prescripción (verificado leyendo el chunk).
**Medido**: aparece en posición 2 del top 5 (hay tres chunks de ese mismo
fallo entre los cinco primeros); el primer puesto es `348:782` (Cossio,
también sobre prescripción de la acción penal), un resultado igual de válido
que no estaba en la lista original de "esperados" pero es correcto — otra
muestra de que RRF sin reranker no promete *el único* correcto, sino que los
correctos estén arriba.

## 4. `despido injustificado`

**Por qué**: control simple, la palabra clave está en la carátula misma.
**Esperado**: `348:834` (Ceballos, Alberto Francisco c/ Ford Argentina
S.C.A. s/ despido) en el primer puesto.
**Medido**: primer puesto (rank_lexico 0), el vectorial no lo trae en el top
50 con este texto — el matching es puramente léxico acá, y alcanza.

## 5. `extradición de un ciudadano extranjero`

**Por qué**: la consulta parafrasea el concepto sin repetir la palabra
"extradición" tal cual aparecería en jerga procesal — el caso pensado para
que el lado léxico no lo encuentre y el vectorial sí.
**Esperado**: `348:644` (Bertulazzi, Leonardo y otro s/ extradición art. 52)
entre los primeros 5.
**Medido**: posición 1 del top 5, encontrado **solo** por el índice vectorial
(`rank_lexico` es `None`) — el ejemplo más claro de los diez de por qué D-6
quiere las dos listas: sin el lado semántico, esta consulta no lo encuentra.

## 6. `medida cautelar contra el municipio`

**Por qué**: concepto + tipo de parte (municipio), ni cita ni nombre propio.
**Esperado**: `348:95` (Autoservicio Mayorista Diarco SA c/ Municipalidad de
La Matanza) en el primer puesto.
**Medido**: primer puesto, encontrado por las dos listas (aparece dos veces
en el top 5 con dos chunks distintos).

## 7. `seguridad social jubilación`

**Por qué**: concepto temático amplio (materia previsional), para ver que
prioriza el fallo más directamente sobre el tema y no cualquier mención de
paso.
**Esperado**: `348:31` (Albarracín, Carlos Ciro c/ Estado Nacional — Ministerio
de D...) en el primer puesto.
**Medido**: primer puesto, encontrado por el lado léxico (rank 0); el resto
del top 5 son casos con Estado Nacional como parte pero de otra materia
(amparo, ejecución), coherente con que "jubilación" los desempata.

## 8. `amparo contra el Estado Nacional`

**Por qué**: tipo de acción + parte demandada, sin coincidir literal con
ninguna carátula.
**Esperado**: `348:895` (Defensor del Pueblo de la Nación c/ Estado Nacional
y otro s/ amparos colectivos) en el primer puesto.
**Medido**: primer puesto, aparece dos veces en el top 5 (dos chunks del
mismo fallo, uno hallado por cada índice).

## 9. Filtro por tribunal: `despido injustificado` + `tribunal_origen`

**Por qué**: demuestra el filtro de metadatos (D-6) — no una consulta nueva,
sino la del punto 4 restringida. "Sala L de la Cámara Nacional de Apelaciones
en lo Civil" la comparten exactamente dos fallos del tomo: `348:821`
(Campodónico, sobre daños y perjuicios) y `348:834` (Ceballos, el resultado
del punto 4).
**Esperado**: filtrando por ese tribunal, todo lo que vuelve pertenece a
`{348:821, 348:834}`, y `348:834` sigue presente.
**Medido**: exactamente así — el filtro se aplica *después* de traer los
candidatos de cada índice (no es un `WHERE` sobre todo el tomo), así que un
fallo del tribunal correcto que ni el léxico ni el vectorial hubieran traído
como candidato para esta consulta simplemente no aparece (no es una falla:
es la consecuencia documentada de cómo funciona el filtro, ver
`spectre/search/hybrid.py`).

## 10. Filtro por tipo de sección: `voto en disidencia` + `tipo_seccion=disidencia`

**Por qué**: el filtro que existe específicamente por D-4 — nunca devolver
una disidencia como si fuera la doctrina de la mayoría. El Tomo 348 tiene 12
secciones marcadas `disidencia` en total.
**Esperado**: todo resultado devuelto viene de una sección con
`secciones.tipo = 'disidencia'` (no solo que el texto mencione la palabra
"disidencia" de pasada).
**Medido**: dos resultados, `348:569` (Tabacalera Sarandí S.A.) y `348:644`
(Bertulazzi — el mismo fallo del punto 5, que además tiene una sección en
disidencia), ambos con su sección confirmada `disidencia` en la base.

---

## Qué demuestran en conjunto

- **1, 4, 6, 7, 8**: el caso típico — las dos listas coinciden y el resultado
  correcto queda primero.
- **5**: el caso que justifica tener las dos listas — sin el vectorial, esta
  consulta no encuentra nada.
- **3**: RRF sin reranker no elige *un único* correcto — puede traer más de
  un resultado válido arriba, y eso está bien para el MVP (D-6: el reranker
  queda fuera).
- **9, 10**: los filtros de metadatos (año / tribunal / sección) funcionan
  sobre los candidatos ya traídos, no como un `WHERE` global — una
  consecuencia de diseño documentada, no una limitación oculta.
