"use strict";

const ETIQUETAS_SECCION = {
  mayoria: "Mayoría",
  voto: "Voto",
  disidencia: "Disidencia",
  dictamen: "Dictamen",
};

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
  } catch (err) {
    aviso.textContent = `No se pudo consultar el estado del servidor (${err.message}).`;
  }
}

function terminosDe(consulta) {
  const vistos = new Set();
  for (const t of consulta.toLowerCase().match(/\w+/g) || []) {
    if (t.length > 2) {
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
  const patron = new RegExp(`(${terminos.map(escaparRegex).join("|")})`, "gi");
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
  const soloLexico = document.getElementById("filtro-solo-lexico").checked;
  if (tribunal) params.set("tribunal", tribunal);
  if (seccion) params.set("seccion", seccion);
  if (anioDesde) params.set("anio_desde", anioDesde);
  if (anioHasta) params.set("anio_hasta", anioHasta);
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

  const secciones = document.createElement("div");
  secciones.className = "secciones-fallo";
  for (const sec of fallo.secciones) {
    secciones.appendChild(renderSeccionFallo(sec));
  }
  contenedor.appendChild(secciones);

  contenedor.appendChild(renderCitasSalientes(fallo.citas_salientes));
}

async function mostrarFallo(cita, paginaOficial) {
  activarTab("fallo");
  const contenedor = document.getElementById("fallo-contenido");
  contenedor.textContent = "Cargando…";

  try {
    const resp = await fetch(`/api/fallos/${encodeURIComponent(cita)}`);
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

for (const boton of document.querySelectorAll(".tab")) {
  boton.addEventListener("click", () => activarTab(boton.dataset.tab));
}

// Dispara una búsqueda con la consulta que haya en el campo. Se llama al
// enviar el formulario y al tocar cualquier filtro: los filtros no viven en
// una búsqueda, se aplican sobre la que está a la vista (y si no hay ninguna,
// no pasa nada).
function ejecutarBusqueda() {
  const consulta = document.getElementById("campo-consulta").value.trim();
  if (consulta) {
    buscar(consulta);
  }
}

document.getElementById("form-buscar").addEventListener("submit", (ev) => {
  ev.preventDefault();
  ejecutarBusqueda();
});

for (const filtro of document.querySelectorAll(
  "#filtro-tribunal, #filtro-seccion, #filtro-anio-desde, #filtro-anio-hasta, #filtro-solo-lexico",
)) {
  filtro.addEventListener("change", ejecutarBusqueda);
}

document.getElementById("filtros-limpiar").addEventListener("click", () => {
  document.getElementById("filtro-tribunal").value = "";
  document.getElementById("filtro-seccion").value = "";
  document.getElementById("filtro-anio-desde").value = "";
  document.getElementById("filtro-anio-hasta").value = "";
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

cargarEstado();
