"use strict";

const ETIQUETAS_SECCION = {
  mayoria: "Mayoría",
  voto: "Voto",
  disidencia: "Disidencia",
  dictamen: "Dictamen",
};

function activarTab(nombre) {
  for (const boton of document.querySelectorAll(".tab")) {
    boton.setAttribute("aria-current", String(boton.dataset.tab === nombre));
  }
  for (const panel of document.querySelectorAll(".panel")) {
    panel.hidden = panel.id !== `tab-${nombre}`;
  }
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
    filas.appendChild(tr);
  }
}

function habilitarBuscador(estado) {
  const campo = document.getElementById("campo-consulta");
  const boton = document.querySelector("#form-buscar button");
  const aviso = document.getElementById("buscar-aviso");

  if (estado.chunks === 0) {
    campo.disabled = true;
    boton.disabled = true;
    aviso.textContent =
      "No hay nada indexado todavía. Corré `spectre ingest <numero>` " +
      "para cargar un tomo.";
    return;
  }

  campo.disabled = false;
  boton.disabled = false;
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

function renderResultado(r, terminos) {
  const li = document.createElement("li");
  li.className = "resultado";

  const encabezado = document.createElement("div");
  encabezado.className = "resultado-encabezado";

  const cita = document.createElement("span");
  cita.className = "cita";
  cita.textContent = r.cita ? `Fallos: ${r.cita}` : "(sin cita)";
  encabezado.appendChild(cita);

  if (r.seccion_tipo) {
    const badge = document.createElement("span");
    badge.className = `badge badge-${r.seccion_tipo}`;
    badge.textContent = ETIQUETAS_SECCION[r.seccion_tipo] || r.seccion_tipo;
    encabezado.appendChild(badge);
  }
  li.appendChild(encabezado);

  if (r.caratula) {
    const caratula = document.createElement("p");
    caratula.className = "caratula";
    caratula.textContent = r.caratula;
    li.appendChild(caratula);
  }

  const extracto = document.createElement("p");
  extracto.className = "extracto";
  resaltarEn(extracto, r.extracto, terminos);
  li.appendChild(extracto);

  return li;
}

async function buscar(consulta) {
  const aviso = document.getElementById("buscar-aviso");
  const lista = document.getElementById("resultados");
  lista.textContent = "";
  aviso.textContent = "Buscando…";

  try {
    const resp = await fetch(`/api/buscar?q=${encodeURIComponent(consulta)}`);
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

for (const boton of document.querySelectorAll(".tab")) {
  boton.addEventListener("click", () => activarTab(boton.dataset.tab));
}

document.getElementById("form-buscar").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const consulta = document.getElementById("campo-consulta").value.trim();
  if (consulta) {
    buscar(consulta);
  }
});

cargarEstado();
