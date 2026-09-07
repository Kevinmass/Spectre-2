"use strict";

const ETIQUETAS_SECCION = {
  mayoria: "Mayoría",
  voto: "Voto",
  disidencia: "Disidencia",
  dictamen: "Dictamen",
};

// Palabras vacías del castellano (§2.3 del plan v2): artículos,
// preposiciones, conjunciones, pronombres y determinantes. No se resaltan —
// antes "del", "por" o "sin" se marcaban como si fueran el término buscado.
const PALABRAS_VACIAS = new Set([
  "el", "la", "lo", "los", "las", "un", "una", "unos", "unas", "al", "del",
  "de", "a", "ante", "bajo", "cabe", "con", "contra", "desde", "durante",
  "en", "entre", "hacia", "hasta", "mediante", "para", "por", "según", "sin",
  "so", "sobre", "tras",
  "y", "e", "o", "u", "ni", "que", "pero", "mas", "sino", "aunque", "porque",
  "pues", "como", "si", "cuando", "mientras", "donde",
  "yo", "tú", "él", "ella", "ello", "nosotros", "vosotros", "ellos", "ellas",
  "me", "te", "se", "nos", "os", "le", "les",
  "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros",
  "nuestras", "vuestro", "vuestra",
  "este", "esta", "esto", "estos", "estas", "ese", "esa", "eso", "esos",
  "esas", "aquel", "aquella", "aquello", "aquellos", "aquellas",
  "cual", "cuales", "quien", "quienes", "cuyo", "cuya", "cuyos", "cuyas",
  "otro", "otra", "otros", "otras", "mismo", "misma", "mismos", "mismas",
  "tan", "tanto", "tanta", "tantos", "tantas", "todo", "toda", "todos",
  "todas", "cada", "algún", "alguna", "alguno", "algunos", "algunas",
  "ningún", "ninguna", "ninguno", "mucho", "mucha", "muchos", "muchas",
  "poco", "poca", "pocos", "pocas", "más", "menos", "muy",
  "no", "sí", "ya", "así", "también", "tampoco", "siempre", "nunca", "solo",
  "sólo", "aún", "aun",
  "es", "son", "ser", "fue", "fueron", "era", "eran", "sea", "sean",
  "ha", "han", "haber", "hay", "había", "habían", "hubo",
  "está", "están", "estaba", "estar",
]);

// Sondea `/api/estado` cada 2s mientras la pestaña Biblioteca está a la
// vista, para que el progreso de una indexación en curso (PR-23) se vea
// avanzar solo. Se corta al salir de la pestaña: nadie necesita seguir
// pidiéndolo mientras mira otra cosa.
let intervaloBiblioteca = null;

function activarTab(nombre) {
  for (const boton of document.querySelectorAll(".tab")) {
    boton.setAttribute("aria-current", String(boton.dataset.tab === nombre));
  }
  for (const panel of document.querySelectorAll(".panel")) {
    panel.hidden = panel.id !== `tab-${nombre}`;
  }

  if (intervaloBiblioteca !== null) {
    clearInterval(intervaloBiblioteca);
    intervaloBiblioteca = null;
  }
  if (nombre === "biblioteca") {
    intervaloBiblioteca = setInterval(cargarEstado, 2000);
  }
}

function renderProgresoTomo(tomo) {
  const contenedor = document.createElement("div");

  const texto = document.createElement("span");
  texto.textContent = `${tomo.etapas_hechas}/${tomo.etapas_total}`;
  contenedor.appendChild(texto);

  if (tomo.calidad === "requiere_ocr") {
    const nota = document.createElement("p");
    nota.className = "vacio progreso-nota";
    nota.textContent = "Requiere OCR: no se sigue procesando (D-10).";
    contenedor.appendChild(nota);
  } else if (tomo.error) {
    const error = document.createElement("p");
    error.className = "progreso-error";
    error.textContent = `Falló en "${tomo.error.etapa}": ${tomo.error.mensaje}`;
    contenedor.appendChild(error);
  }
  return contenedor;
}

function pintarBiblioteca(estado) {
  const vacio = document.getElementById("biblioteca-vacio");
  const tabla = document.getElementById("biblioteca-tabla");
  const filas = document.getElementById("biblioteca-filas");

  if (estado.tomos.length === 0) {
    vacio.hidden = false;
    tabla.hidden = true;
    return;
  }

  vacio.hidden = true;
  tabla.hidden = false;
  filas.textContent = "";
  for (const tomo of estado.tomos) {
    const tr = document.createElement("tr");
    for (const valor of [tomo.numero, tomo.estado, tomo.calidad]) {
      const td = document.createElement("td");
      td.textContent = valor;
      tr.appendChild(td);
    }
    const tdProgreso = document.createElement("td");
    tdProgreso.appendChild(renderProgresoTomo(tomo));
    tr.appendChild(tdProgreso);

    const tdSumarios = document.createElement("td");
    tdSumarios.textContent = tomo.sumarios ?? 0;
    tr.appendChild(tdSumarios);

    filas.appendChild(tr);
  }
}

function habilitarBuscador(estado) {
  const campo = document.getElementById("campo-consulta");
  const boton = document.querySelector("#form-buscar button");
  const aviso = document.getElementById("buscar-aviso");
  const filtros = document.querySelectorAll("#filtros input, #filtros select, #filtros button");

  if (estado.chunks === 0) {
    campo.disabled = true;
    boton.disabled = true;
    for (const f of filtros) f.disabled = true;
    aviso.textContent =
      "No hay nada indexado todavía. Corré `spectre ingest <numero>` " +
      "para cargar un tomo.";
    return;
  }

  campo.disabled = false;
  boton.disabled = false;
  for (const f of filtros) f.disabled = false;
  aviso.textContent =
    `Hay ${estado.chunks} fragmentos indexados en ${estado.tomos.length} ` +
    "tomo(s). Escribí algo y buscá.";
}

async function cargarEstado() {
  const aviso = document.getElementById("buscar-aviso");
  try {
    const resp = await fetch("/api/estado");
    if (!resp.ok) {
      throw new Error(`${resp.status} ${resp.statusText}`);
    }
    const estado = await resp.json();
    habilitarBuscador(estado);
    pintarBiblioteca(estado);
    cargarMaterias(); // no-op una vez que hay materias; se puebla tras un sync
  } catch (err) {
    aviso.textContent = `No se pudo consultar el estado del servidor (${err.message}).`;
  }
}

function terminosDe(consulta) {
  const vistos = new Set();
  // Tokeniza por letras/dígitos Unicode: "acción" es un término, no "acci".
  for (const t of consulta.toLowerCase().match(/[\p{L}\p{N}]+/gu) || []) {
    if (t.length > 2 && !PALABRAS_VACIAS.has(t)) {
      vistos.add(t);
    }
  }
  return Array.from(vistos);
}

function escaparRegex(texto) {
  return texto.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function resaltarEn(contenedor, texto, terminos) {
  contenedor.textContent = "";
  if (terminos.length === 0) {
    contenedor.textContent = texto;
    return;
  }
  // Límites de palabra Unicode-aware: "sin" no matchea dentro de "sino",
  // "estado" no matchea dentro de "estados". `\b` de JS es solo ASCII y
  // rompería con acentos ("café", "área"), así que se usan lookarounds
  // contra letra/dígito.
  const alternativas = terminos.map(escaparRegex).join("|");
  const patron = new RegExp(
    `(?<![\\p{L}\\p{N}])(${alternativas})(?![\\p{L}\\p{N}])`,
    "giu",
  );
  let ultimo = 0;
  let m;
  while ((m = patron.exec(texto)) !== null) {
    if (m.index > ultimo) {
      contenedor.appendChild(document.createTextNode(texto.slice(ultimo, m.index)));
    }
    const marca = document.createElement("mark");
    marca.textContent = m[0];
    contenedor.appendChild(marca);
    ultimo = m.index + m[0].length;
    if (patron.lastIndex === m.index) {
      patron.lastIndex += 1; // evita loop infinito con matches vacíos
    }
  }
  contenedor.appendChild(document.createTextNode(texto.slice(ultimo)));
}

function renderPasaje(p, terminos) {
  const div = document.createElement("div");
  div.className = "pasaje";

  if (p.seccion_tipo) {
    const badge = document.createElement("span");
    badge.className = `badge badge-${p.seccion_tipo}`;
    badge.textContent = ETIQUETAS_SECCION[p.seccion_tipo] || p.seccion_tipo;
    div.appendChild(badge);
  }

  const extracto = document.createElement("p");
  extracto.className = "extracto";
  resaltarEn(extracto, p.extracto, terminos);
  div.appendChild(extracto);

  return div;
}

// Sumarios oficiales de la CSJN (PR-C2b). `compacto` (en la lista de
// resultados) muestra solo el primero + un contador; la vista de fallo los
// muestra todos.
function renderSumarios(sumarios, { compacto = false } = {}) {
  const contenedor = document.createElement("div");
  contenedor.className = "sumarios";
  if (!sumarios || sumarios.length === 0) {
    return contenedor;
  }

  const h = document.createElement(compacto ? "p" : "h3");
  h.className = "sumarios-titulo";
  h.textContent = "Sumario oficial de la CSJN";
  contenedor.appendChild(h);

  const mostrados = compacto ? sumarios.slice(0, 1) : sumarios;
  for (const s of mostrados) {
    const div = document.createElement("div");
    div.className = "sumario";

    const texto = document.createElement("p");
    texto.className = "sumario-texto";
    texto.textContent = s.texto;
    div.appendChild(texto);

    if (s.materia) {
      const materia = document.createElement("p");
      materia.className = "sumario-materia";
      materia.textContent = s.materia;
      div.appendChild(materia);
    }

    if (s.voces && s.voces.length > 0) {
      const voces = document.createElement("p");
      voces.className = "sumario-voces";
      for (const v of s.voces) {
        const chip = document.createElement("span");
        chip.className = "voz-chip";
        chip.textContent = v;
        voces.appendChild(chip);
      }
      div.appendChild(voces);
    }
    contenedor.appendChild(div);
  }

  const ocultos = sumarios.length - mostrados.length;
  if (ocultos > 0) {
    const mas = document.createElement("p");
    mas.className = "sumarios-mas";
    mas.textContent =
      ocultos === 1 ? "1 sumario más" : `${ocultos} sumarios más`;
    contenedor.appendChild(mas);
  }
  return contenedor;
}

function renderResultado(r, terminos) {
  const li = document.createElement("li");
  li.className = "resultado";

  const encabezado = document.createElement("div");
  encabezado.className = "resultado-encabezado";

  // La página del PDF del mejor pasaje: al clickear la cita se abre el fallo
  // ahí. Saltar al pasaje exacto dentro del fallo es PR-B2.
  const paginaPrincipal =
    r.pasajes.length > 0 ? r.pasajes[0].pagina_oficial : null;

  const cita = document.createElement("button");
  cita.type = "button";
  cita.className = "cita";
  cita.textContent = r.cita ? `Fallos: ${r.cita}` : "(sin cita)";
  if (r.cita) {
    cita.addEventListener("click", () => mostrarFallo(r.cita, paginaPrincipal));
  } else {
    cita.disabled = true;
  }
  encabezado.appendChild(cita);

  if (r.fecha) {
    const fecha = document.createElement("span");
    fecha.className = "resultado-fecha";
    fecha.textContent = r.fecha;
    encabezado.appendChild(fecha);
  }
  li.appendChild(encabezado);

  if (r.caratula) {
    const caratula = document.createElement("p");
    caratula.className = "caratula";
    caratula.textContent = r.caratula;
    li.appendChild(caratula);
  }

  if (r.sumarios && r.sumarios.length > 0) {
    li.appendChild(renderSumarios(r.sumarios, { compacto: true }));
  }

  const pasajes = document.createElement("div");
  pasajes.className = "pasajes";
  for (const p of r.pasajes) {
    pasajes.appendChild(renderPasaje(p, terminos));
  }
  li.appendChild(pasajes);

  const ocultos = r.total_pasajes - r.pasajes.length;
  if (ocultos > 0) {
    const mas = document.createElement("p");
    mas.className = "pasajes-mas";
    mas.textContent =
      ocultos === 1
        ? "1 pasaje más en este fallo"
        : `${ocultos} pasajes más en este fallo`;
    li.appendChild(mas);
  }

  return li;
}

// Lee los campos de filtro y arma el query string de /api/buscar. Solo se
// mandan los que tienen valor: un filtro vacío no restringe nada.
function parametrosBusqueda(consulta) {
  const params = new URLSearchParams({ q: consulta });
  const tribunal = document.getElementById("filtro-tribunal").value.trim();
  const seccion = document.getElementById("filtro-seccion").value;
  const anioDesde = document.getElementById("filtro-anio-desde").value;
  const anioHasta = document.getElementById("filtro-anio-hasta").value;
  const voz = document.getElementById("filtro-voz").value.trim();
  const materia = document.getElementById("filtro-materia").value;
  const soloLexico = document.getElementById("filtro-solo-lexico").checked;
  if (tribunal) params.set("tribunal", tribunal);
  if (seccion) params.set("seccion", seccion);
  if (anioDesde) params.set("anio_desde", anioDesde);
  if (anioHasta) params.set("anio_hasta", anioHasta);
  if (voz) params.set("voz", voz);
  if (materia) params.set("materia", materia);
  if (soloLexico) params.set("solo_lexico", "true");
  return params;
}

async function buscar(consulta) {
  const aviso = document.getElementById("buscar-aviso");
  const lista = document.getElementById("resultados");
  lista.textContent = "";
  aviso.textContent = "Buscando…";

  try {
    const resp = await fetch(`/api/buscar?${parametrosBusqueda(consulta)}`);
    if (!resp.ok) {
      throw new Error(`${resp.status} ${resp.statusText}`);
    }
    const datos = await resp.json();

    if (datos.resultados.length === 0) {
      aviso.textContent = `No se encontraron resultados para "${consulta}".`;
      return;
    }

    aviso.textContent =
      datos.modo === "solo_lexico"
        ? `${datos.resultados.length} resultado(s) — búsqueda solo por texto ` +
          "(el modelo de significado no está disponible)."
        : `${datos.resultados.length} resultado(s).`;

    const terminos = terminosDe(consulta);
    for (const r of datos.resultados) {
      lista.appendChild(renderResultado(r, terminos));
    }
  } catch (err) {
    aviso.textContent = `No se pudo buscar (${err.message}).`;
  }
}

// --- vista de fallo (PR-22) ------------------------------------------- //

function renderMetadatos(fallo) {
  const dl = document.createElement("dl");
  dl.className = "metadatos";
  const filas = [
    ["Fecha", fallo.fecha || "—"],
    ["Tribunal de origen", fallo.tribunal_origen || "—"],
    ["Tipo de recurso", fallo.tipo_recurso || "—"],
    ["Jueces", fallo.jueces.length > 0 ? fallo.jueces.join(", ") : "—"],
  ];
  for (const [etiqueta, valor] of filas) {
    const dt = document.createElement("dt");
    dt.textContent = etiqueta;
    const dd = document.createElement("dd");
    dd.textContent = valor;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  return dl;
}

function renderEnlacePdf(fallo, paginaSolicitada) {
  const p = document.createElement("p");
  if (!fallo.pdf_disponible) {
    p.className = "vacio";
    p.textContent = "El PDF de este tomo no está disponible en este servidor.";
    return p;
  }

  const paginaOficial = paginaSolicitada ?? fallo.pagina_inicio;
  const a = document.createElement("a");
  a.target = "_blank";
  a.rel = "noopener";
  if (fallo.offset_pagina !== null && paginaOficial !== null) {
    const paginaPdf = paginaOficial + fallo.offset_pagina;
    a.href = `/api/tomos/${fallo.tomo_numero}/pdf#page=${paginaPdf}`;
    a.textContent = `Ver en el PDF (Tomo ${fallo.tomo_numero}, página ${paginaOficial})`;
  } else {
    a.href = `/api/tomos/${fallo.tomo_numero}/pdf`;
    a.textContent = `Ver el PDF del Tomo ${fallo.tomo_numero}`;
  }
  p.className = "enlace-pdf";
  p.appendChild(a);
  return p;
}

function renderSeccionFallo(sec) {
  const div = document.createElement("div");
  div.className = "seccion-fallo";

  const encabezado = document.createElement("h3");
  const badge = document.createElement("span");
  badge.className = `badge badge-${sec.tipo}`;
  badge.textContent = ETIQUETAS_SECCION[sec.tipo] || sec.tipo;
  encabezado.appendChild(badge);
  if (sec.autor) {
    const autor = document.createElement("span");
    autor.className = "seccion-autor";
    autor.textContent = sec.autor;
    encabezado.appendChild(autor);
  }
  div.appendChild(encabezado);

  const texto = document.createElement("p");
  texto.className = "seccion-texto";
  texto.textContent = sec.texto;
  div.appendChild(texto);

  return div;
}

function renderCitasSalientes(citas) {
  const contenedor = document.createElement("div");
  contenedor.className = "citas-salientes";

  const h3 = document.createElement("h3");
  h3.textContent = "Citas a otros fallos";
  contenedor.appendChild(h3);

  if (citas.length === 0) {
    const p = document.createElement("p");
    p.className = "vacio";
    p.textContent = "No se encontraron citas a otros fallos en este texto.";
    contenedor.appendChild(p);
    return contenedor;
  }

  const ul = document.createElement("ul");
  for (const c of citas) {
    const li = document.createElement("li");
    const cita = document.createElement("span");
    cita.className = "cita";
    cita.textContent = `Fallos: ${c.tomo_citado}:${c.pagina_citada}`;
    li.appendChild(cita);
    const contexto = document.createElement("p");
    contexto.className = "cita-contexto";
    contexto.textContent = c.contexto;
    li.appendChild(contexto);
    ul.appendChild(li);
  }
  contenedor.appendChild(ul);
  return contenedor;
}

function renderCitasEntrantes(citas) {
  const contenedor = document.createElement("div");
  contenedor.className = "citas-entrantes";

  const h3 = document.createElement("h3");
  h3.textContent = "Citado por";
  contenedor.appendChild(h3);

  if (!citas || citas.length === 0) {
    const p = document.createElement("p");
    p.className = "vacio";
    p.textContent =
      "Ningún otro fallo del corpus indexado cita a este. " +
      "A medida que se sumen tomos pueden aparecer citas entrantes.";
    contenedor.appendChild(p);
    return contenedor;
  }

  const ul = document.createElement("ul");
  for (const c of citas) {
    const li = document.createElement("li");

    const cita = document.createElement("button");
    cita.type = "button";
    cita.className = "cita";
    cita.textContent = c.cita ? `Fallos: ${c.cita}` : "(sin cita)";
    if (c.cita) {
      cita.addEventListener("click", () => mostrarFallo(c.cita, null));
    } else {
      cita.disabled = true;
    }
    li.appendChild(cita);

    if (c.caratula) {
      const caratula = document.createElement("p");
      caratula.className = "caratula";
      caratula.textContent = c.caratula;
      li.appendChild(caratula);
    }

    if (c.contexto) {
      const contexto = document.createElement("p");
      contexto.className = "cita-contexto";
      contexto.textContent = c.contexto;
      li.appendChild(contexto);
    }

    ul.appendChild(li);
  }
  contenedor.appendChild(ul);
  return contenedor;
}

function renderFallo(fallo, paginaSolicitada) {
  const contenedor = document.getElementById("fallo-contenido");
  contenedor.textContent = "";

  const h2 = document.createElement("h2");
  h2.textContent = fallo.cita ? `Fallos: ${fallo.cita}` : "(sin cita)";
  contenedor.appendChild(h2);

  if (fallo.caratula) {
    const caratula = document.createElement("p");
    caratula.className = "caratula";
    caratula.textContent = fallo.caratula;
    contenedor.appendChild(caratula);
  }

  contenedor.appendChild(renderMetadatos(fallo));
  contenedor.appendChild(renderEnlacePdf(fallo, paginaSolicitada));

  if (fallo.sumarios && fallo.sumarios.length > 0) {
    contenedor.appendChild(renderSumarios(fallo.sumarios));
  }

  const secciones = document.createElement("div");
  secciones.className = "secciones-fallo";
  for (const sec of fallo.secciones) {
    secciones.appendChild(renderSeccionFallo(sec));
  }
  contenedor.appendChild(secciones);

  contenedor.appendChild(renderCitasSalientes(fallo.citas_salientes));
  contenedor.appendChild(renderCitasEntrantes(fallo.citas_entrantes));
}

function renderFalloNoEncontrado(contenedor, cita) {
  contenedor.textContent = "";
  const aviso = document.createElement("p");
  aviso.className = "vacio";
  aviso.textContent =
    `No hay ningún fallo con la cita Fallos: ${cita} entre lo que está ` +
    "indexado. Puede que ese tomo todavía no esté cargado, o que la cita no " +
    "exista.";
  contenedor.appendChild(aviso);

  const comoTexto = document.createElement("button");
  comoTexto.type = "button";
  comoTexto.className = "volver";
  comoTexto.textContent = `Buscar “${cita}” como texto`;
  comoTexto.addEventListener("click", () => {
    activarTab("buscar");
    document.getElementById("campo-consulta").value = cita;
    buscar(cita);
  });
  contenedor.appendChild(comoTexto);
}

async function mostrarFallo(cita, paginaOficial) {
  activarTab("fallo");
  const contenedor = document.getElementById("fallo-contenido");
  contenedor.textContent = "Cargando…";

  try {
    const resp = await fetch(`/api/fallos/${encodeURIComponent(cita)}`);
    if (resp.status === 404) {
      renderFalloNoEncontrado(contenedor, cita);
      return;
    }
    if (!resp.ok) {
      throw new Error(`${resp.status} ${resp.statusText}`);
    }
    const fallo = await resp.json();
    renderFallo(fallo, paginaOficial);
  } catch (err) {
    contenedor.textContent = `No se pudo cargar el fallo (${err.message}).`;
  }
}

// --- biblioteca: indexar / subir (PR-23) -------------------------------- //

async function _detalleDeError(resp) {
  const cuerpo = await resp.json().catch(() => ({}));
  return cuerpo.detail || `${resp.status} ${resp.statusText}`;
}

async function indexarDesdeCsjn(numero, csjnTomoId, boton) {
  const aviso = document.getElementById("biblioteca-aviso");
  aviso.hidden = false;
  aviso.textContent = `Registrando el tomo ${numero}…`;
  boton.disabled = true;
  try {
    const resp = await fetch(`/api/tomos/${numero}/indexar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csjn_tomo_id: csjnTomoId || null }),
    });
    if (!resp.ok) {
      throw new Error(await _detalleDeError(resp));
    }
    aviso.textContent =
      `Tomo ${numero}: indexación iniciada. El progreso se actualiza solo ` +
      "acá abajo.";
    cargarEstado();
  } catch (err) {
    aviso.textContent = `No se pudo iniciar la indexación (${err.message}).`;
  } finally {
    boton.disabled = false;
  }
}

async function subirPdf(numero, archivo, boton) {
  const aviso = document.getElementById("biblioteca-aviso");
  aviso.hidden = false;
  aviso.textContent = `Subiendo el PDF del tomo ${numero}…`;
  boton.disabled = true;
  try {
    const datos = new FormData();
    datos.append("archivo", archivo);
    const resp = await fetch(`/api/tomos/${numero}/subir`, {
      method: "POST",
      body: datos,
    });
    if (!resp.ok) {
      throw new Error(await _detalleDeError(resp));
    }
    aviso.textContent = `Tomo ${numero}: PDF subido, indexación iniciada.`;
    cargarEstado();
  } catch (err) {
    aviso.textContent = `No se pudo subir el PDF (${err.message}).`;
  } finally {
    boton.disabled = false;
  }
}

async function sincronizarSumarios(numero, boton) {
  const aviso = document.getElementById("biblioteca-aviso");
  aviso.hidden = false;
  aviso.textContent = `Sincronizando sumarios del tomo ${numero}…`;
  boton.disabled = true;
  try {
    const resp = await fetch(`/api/tomos/${numero}/sumarios/sync`, {
      method: "POST",
    });
    if (!resp.ok) {
      throw new Error(await _detalleDeError(resp));
    }
    aviso.textContent =
      `Tomo ${numero}: sincronización de sumarios iniciada. Va a tardar ` +
      "(una consulta por fallo); el conteo de la columna «Sumarios» sube solo.";
    cargarEstado();
  } catch (err) {
    aviso.textContent = `No se pudieron sincronizar los sumarios (${err.message}).`;
  } finally {
    boton.disabled = false;
  }
}

// --- filtro por voz: autocompletado contra /api/voces (tabla local) ------ //

let _debounceVoces = null;

async function actualizarDatalistVoces(termino) {
  if (!termino || termino.length < 2) {
    return;
  }
  try {
    const resp = await fetch(`/api/voces?q=${encodeURIComponent(termino)}`);
    if (!resp.ok) {
      return;
    }
    const datos = await resp.json();
    const datalist = document.getElementById("voces-datalist");
    datalist.textContent = "";
    for (const v of datos.voces) {
      const opt = document.createElement("option");
      opt.value = v.valor;
      datalist.appendChild(opt);
    }
  } catch {
    // el autocompletado es una ayuda, no un bloqueante: si falla, se sigue
  }
}

let _materiasCargadas = false;

async function cargarMaterias() {
  if (_materiasCargadas) {
    return;
  }
  try {
    const resp = await fetch("/api/materias");
    if (!resp.ok) {
      return;
    }
    const datos = await resp.json();
    const select = document.getElementById("filtro-materia");
    for (const m of datos.materias) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      select.appendChild(opt);
    }
    _materiasCargadas = datos.materias.length > 0;
  } catch {
    // idem: sin materias el <select> queda con "todas" nomás
  }
}

for (const boton of document.querySelectorAll(".tab")) {
  boton.addEventListener("click", () => activarTab(boton.dataset.tab));
}

// Detecta una consulta que es una cita de Fallos —"348:145", "Fallos: 348:145",
// "Fallos 348:145"— y la normaliza a "tomo:pagina". Si no lo es, `null`. Es
// como se busca jurisprudencia de verdad: se conoce la cita y se quiere el
// fallo, no una lista.
function citaDe(consulta) {
  const m = consulta.match(/^\s*(?:fallos\s*:?\s*)?(\d{1,3})\s*:\s*(\d{1,4})\s*$/i);
  return m ? `${m[1]}:${m[2]}` : null;
}

// Dispara una búsqueda con la consulta que haya en el campo. Se llama al
// tocar cualquier filtro: los filtros no viven en una búsqueda, se aplican
// sobre la que está a la vista (y si no hay ninguna, no pasa nada).
function ejecutarBusqueda() {
  const consulta = document.getElementById("campo-consulta").value.trim();
  if (consulta) {
    buscar(consulta);
  }
}

document.getElementById("form-buscar").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const consulta = document.getElementById("campo-consulta").value.trim();
  if (!consulta) {
    return;
  }
  const cita = citaDe(consulta);
  if (cita) {
    mostrarFallo(cita, null);
  } else {
    buscar(consulta);
  }
});

for (const filtro of document.querySelectorAll(
  "#filtro-tribunal, #filtro-seccion, #filtro-anio-desde, #filtro-anio-hasta, #filtro-voz, #filtro-materia, #filtro-solo-lexico",
)) {
  filtro.addEventListener("change", ejecutarBusqueda);
}

document.getElementById("filtro-voz").addEventListener("input", (ev) => {
  clearTimeout(_debounceVoces);
  const termino = ev.target.value.trim();
  _debounceVoces = setTimeout(() => actualizarDatalistVoces(termino), 200);
});

document.getElementById("filtros-limpiar").addEventListener("click", () => {
  document.getElementById("filtro-tribunal").value = "";
  document.getElementById("filtro-seccion").value = "";
  document.getElementById("filtro-anio-desde").value = "";
  document.getElementById("filtro-anio-hasta").value = "";
  document.getElementById("filtro-voz").value = "";
  document.getElementById("filtro-materia").value = "";
  document.getElementById("filtro-solo-lexico").checked = false;
  ejecutarBusqueda();
});

document.getElementById("volver-resultados").addEventListener("click", () => {
  activarTab("buscar");
});

document.getElementById("form-indexar-csjn").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const numero = form.elements.numero.value;
  const csjnTomoId = form.elements.csjn_tomo_id.value.trim();
  if (!csjnTomoId) {
    const aviso = document.getElementById("biblioteca-aviso");
    aviso.hidden = false;
    aviso.textContent =
      "Falta el id de la CSJN (no es el número de tomo): lo da " +
      "`spectre csjn catalog`. Si ya tenés el PDF, usá «Subir un PDF propio».";
    return;
  }
  indexarDesdeCsjn(numero, csjnTomoId, form.querySelector("button"));
});

document.getElementById("form-subir-pdf").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const numero = form.elements.numero.value;
  const archivo = form.elements.archivo.files[0];
  if (!archivo) {
    return;
  }
  subirPdf(numero, archivo, form.querySelector("button"));
});

document.getElementById("form-sync-sumarios").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const numero = form.elements.numero.value;
  if (!numero) {
    return;
  }
  sincronizarSumarios(numero, form.querySelector("button"));
});

cargarEstado();
