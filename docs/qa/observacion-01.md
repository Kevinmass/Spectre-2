# Observación 01 — Primera usuaria buscando jurisprudencia

> **Estado: sesión pendiente de correr.** Este archivo es el instrumento
> (encuadre + reglas + plantilla de captura). Los bloques marcados
> `_(completar en la sesión)_` y la sección **Síntesis** los llena Kevin
> después de sentarse a mirar. Recién ahí se marca la casilla de PR-A0 en
> `docs/plan-v2.md` y se cierra la PR.

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

**Contexto de la usuaria** _(completar en la sesión)_:

- Caso / tema real que trae:
- Cómo buscaría esto hoy sin Spectre (SAIJ, Google, un PDF que ya tiene, un
  colega):

---

## 4. Las cinco búsquedas

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

## 6. Línea de tiempo cruda _(completar en la sesión)_

Un renglón por fricción, con el minuto aproximado. No editar después: es el
registro en bruto.

| min | qué pasó | palabras de la usuaria |
|-----|----------|------------------------|
|     |          |                        |

---

## 7. Cierre

Después de las cinco búsquedas, recién ahí se puede conversar. Tres
preguntas, respuestas textuales:

1. **¿Qué te faltó** para resolver lo que viniste a resolver?
2. **¿Lo volverías a abrir** la próxima vez que tengas una consulta así?
   ¿Por qué sí / no?
3. **¿Qué esperabas que estuviera** y no estaba?

_(completar en la sesión)_

---

## 8. Síntesis _(completar después, con la sesión terminada)_

### 8.1 Las cinco fricciones más caras, ordenadas por impacto

Para cada una: qué es, a qué problema del §2 corresponde (o "nuevo"), y a qué
PR de la Tanda A o B toca.

1.
2.
3.
4.
5.

### 8.2 Hallazgos que el relevamiento no tenía

Cosas que aparecieron en la sesión y no están en los seis problemas del §2 ni
en los pendientes chicos.

-

### 8.3 Qué le pasa a la Tanda B

La Tanda B estaba planeada sin haber visto a nadie. Con la sesión hecha:

- **Se confirma tal cual**:
- **Cambia de prioridad** (y hacia dónde):
- **Se descarta o se recorta**:
- **Aparece algo nuevo para la Tanda B** que no estaba:

### 8.4 ¿Algo de esto es urgente para la Tanda A?

La Tanda A ya está definida y no depende de esta sesión, pero si algo salió
acá que reordena A1–A6, anotarlo.

-

---

## 9. Registro de la sesión _(completar)_

- Fecha:
- Duración:
- Quién observó:
- Cómo se registró (grabación / notas en vivo / dos personas):
- Base usada (tomos indexados):
