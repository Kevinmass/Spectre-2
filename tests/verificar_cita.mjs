// PR-A5 — verificación de "buscar por cita" de `spectre/web/app.js` sin
// navegador. No corre con pytest ni en CI (es JS): se corre a mano con
//   node tests/verificar_cita.mjs
// Carga `app.js` con un DOM de mentira y chequea:
//  - `citaDe` normaliza las tres formas del plan a "tomo:pagina" y no matchea
//    consultas que no son citas;
//  - `mostrarFallo` ante un 404 muestra un mensaje, no "404".
import { readFileSync } from "node:fs";
import vm from "node:vm";

const src = readFileSync(new URL("../spectre/web/app.js", import.meta.url), "utf8");

// --- DOM mínimo ------------------------------------------------------------ //
function nodoFalso() {
  return {
    _hijos: [],
    _text: "",
    className: "",
    hidden: false,
    value: "",
    type: "",
    appendChild(h) {
      this._hijos.push(h);
      return h;
    },
    addEventListener() {},
    setAttribute() {},
    querySelector: () => nodoFalso(),
    querySelectorAll: () => [],
    get dataset() {
      return {};
    },
    set textContent(v) {
      this._text = v;
      this._hijos = [];
    },
    get textContent() {
      return this._hijos.length
        ? this._hijos.map((h) => h.textContent ?? h._text ?? "").join(" ")
        : this._text;
    },
  };
}
const elementos = new Map();
function el(id) {
  if (!elementos.has(id)) elementos.set(id, nodoFalso());
  return elementos.get(id);
}

let respuestaFetch = { ok: false, status: 500, json: async () => ({}) };
const ctx = {
  document: {
    createElement: () => nodoFalso(),
    createTextNode: (t) => ({ nodeType: 3, textContent: t, _text: t }),
    getElementById: el,
    querySelector: () => nodoFalso(),
    querySelectorAll: () => [],
  },
  window: {},
  fetch: async () => respuestaFetch,
  setInterval: () => 0,
  clearInterval: () => {},
  console,
};
vm.createContext(ctx);
vm.runInContext(src, ctx);

let fallas = 0;
function chequear(desc, ok, extra = "") {
  if (!ok) fallas++;
  console.log(`${ok ? "ok  " : "FAIL"}  ${desc}${extra ? "  — " + extra : ""}`);
}

// --- citaDe ------------------------------------------------------------- //
console.log("# citaDe");
const norm = "348:145";
for (const forma of [
  "348:145",
  "Fallos: 348:145",
  "Fallos 348:145",
  "fallos:348:145",
  "  348 : 145  ",
  "FALLOS:  348:145",
]) {
  const got = ctx.citaDe(forma);
  chequear(`"${forma}" -> ${norm}`, got === norm, `dio ${JSON.stringify(got)}`);
}
for (const noCita of [
  "daño moral",
  "280",
  "responsabilidad del estado",
  "art. 348:145 y otros",
  "348",
  "",
]) {
  const got = ctx.citaDe(noCita);
  chequear(`"${noCita}" -> null`, got === null, `dio ${JSON.stringify(got)}`);
}

// --- mostrarFallo con 404 -------------------------------------------------- //
console.log("\n# mostrarFallo (cita inexistente)");
respuestaFetch = { ok: false, status: 404, json: async () => ({ detail: "x" }) };
await ctx.mostrarFallo("348:999", null);
const txt = el("fallo-contenido").textContent;
chequear("no muestra '404' crudo", !/\b404\b/.test(txt), JSON.stringify(txt.slice(0, 40)));
chequear("dice que no hay ese fallo", /no hay ning[uú]n fallo/i.test(txt));
chequear("ofrece buscarlo como texto", /como texto/i.test(txt));

console.log(`\n${fallas === 0 ? "TODO OK" : fallas + " FALLA(S)"}`);
process.exit(fallas === 0 ? 0 : 1);
