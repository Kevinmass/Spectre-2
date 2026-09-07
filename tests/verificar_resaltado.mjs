// PR-A3 — verificación del resaltado de `spectre/web/app.js` sin navegador.
//
// No corre con pytest ni en CI (es JS): se corre a mano con
//   node tests/verificar_resaltado.mjs
// Igual que los markers `slow` / `red` de pytest, es una verificación que
// existe pero no la mira CI. Carga `app.js` con un DOM de mentira y ejerce
// `terminosDe` / `resaltarEn` contra el criterio de aceptación del plan v2
// (§ Tanda A, PR-A3): "despido sin causa" no resalta "sino"; "responsabilidad
// del estado" no resalta "del".
import { readFileSync } from "node:fs";
import vm from "node:vm";

const src = readFileSync(new URL("../spectre/web/app.js", import.meta.url), "utf8");

// --- DOM mínimo, solo lo que app.js toca al cargar ---------------------- //
function nodoFalso() {
  const n = {
    _hijos: [],
    _text: "",
    className: "",
    hidden: false,
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
        ? this._hijos.map((h) => h.textContent ?? h._text ?? "").join("")
        : this._text;
    },
  };
  return n;
}
const ctx = {
  document: {
    createElement: () => nodoFalso(),
    createTextNode: (t) => ({ nodeType: 3, textContent: t, _text: t }),
    getElementById: () => nodoFalso(),
    querySelector: () => nodoFalso(),
    querySelectorAll: () => [],
  },
  window: {},
  fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
  setInterval: () => 0,
  clearInterval: () => {},
  console,
};
vm.createContext(ctx);
vm.runInContext(src, ctx);

// Reconstruye el string con [..] donde app.js pondría <mark>.
function marcado(texto, consulta) {
  const cont = nodoFalso();
  ctx.resaltarEn(cont, texto, ctx.terminosDe(consulta));
  return cont._hijos
    .map((h) => (h.nodeType === 3 ? h.textContent : `[${h.textContent}]`))
    .join("");
}

let fallas = 0;
function chequear(desc, obtenido, esperado) {
  const ok = obtenido === esperado;
  if (!ok) fallas++;
  console.log(`${ok ? "ok  " : "FAIL"}  ${desc}`);
  if (!ok) console.log(`        esperado: ${esperado}\n        obtenido: ${obtenido}`);
}

const j = JSON.stringify;

console.log("# terminosDe");
chequear("saca 'sin'", j(ctx.terminosDe("despido sin causa")), j(["despido", "causa"]));
chequear("saca 'del'", j(ctx.terminosDe("responsabilidad del estado")), j(["responsabilidad", "estado"]));
chequear("no parte acentos", j(ctx.terminosDe("acción penal")), j(["acción", "penal"]));
chequear("todo vacías -> []", j(ctx.terminosDe("el de la por")), j([]));

console.log("\n# resaltarEn");
chequear(
  "'despido sin causa' no resalta 'sino'",
  marcado("hubo despido pero no sino una renuncia; la causa es otra", "despido sin causa"),
  "hubo [despido] pero no sino una renuncia; la [causa] es otra",
);
chequear(
  "'responsabilidad del estado' no resalta 'del'",
  marcado("la responsabilidad del Estado y del particular", "responsabilidad del estado"),
  "la [responsabilidad] del [Estado] y del particular",
);
chequear(
  "límite de palabra: 'estado' no resalta 'estados'",
  marcado("el Estado y los estados provinciales", "estado"),
  "el [Estado] y los estados provinciales",
);
chequear(
  "acento: 'acción' no resalta 'reacción'",
  marcado("la acción y la reacción", "acción"),
  "la [acción] y la reacción",
);
chequear(
  "case-insensitive",
  marcado("PENAL penal Penal", "penal"),
  "[PENAL] [penal] [Penal]",
);

console.log(`\n${fallas === 0 ? "TODO OK" : fallas + " FALLA(S)"}`);
process.exit(fallas === 0 ? 0 : 1);
