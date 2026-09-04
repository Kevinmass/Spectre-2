"use strict";

function activarTab(nombre) {
  for (const boton of document.querySelectorAll(".tab")) {
    boton.setAttribute("aria-current", String(boton.dataset.tab === nombre));
  }
  for (const panel of document.querySelectorAll(".panel")) {
    panel.hidden = panel.id !== `tab-${nombre}`;
  }
}

function pintarBuscar(estado) {
  const p = document.getElementById("buscar-estado");
  if (estado.chunks === 0) {
    p.textContent =
      "No hay nada indexado todavía. Corré `spectre ingest <numero>` " +
      "para cargar un tomo.";
  } else {
    p.textContent =
      `Hay ${estado.chunks} fragmentos indexados en ${estado.tomos.length} ` +
      "tomo(s). La búsqueda llega en el próximo PR.";
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

async function cargarEstado() {
  try {
    const resp = await fetch("/api/estado");
    if (!resp.ok) {
      throw new Error(`${resp.status} ${resp.statusText}`);
    }
    const estado = await resp.json();
    pintarBuscar(estado);
    pintarBiblioteca(estado);
  } catch (err) {
    document.getElementById("buscar-estado").textContent =
      `No se pudo consultar el estado del servidor (${err.message}).`;
  }
}

for (const boton of document.querySelectorAll(".tab")) {
  boton.addEventListener("click", () => activarTab(boton.dataset.tab));
}

cargarEstado();
