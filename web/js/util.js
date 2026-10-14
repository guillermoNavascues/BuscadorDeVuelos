// Utilidades de la web: formato, escape de HTML, aeropuertos, avisos, modal y animaciones.
import { icono } from "./iconos.js";

export const $ = (selector, raiz = document) => raiz.querySelector(selector);
export const $$ = (selector, raiz = document) => [...raiz.querySelectorAll(selector)];

export const esc = (valor) =>
  String(valor ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const fmtEur = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });
const fmtEurRedondo = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const eur = (n, redondo = false) =>
  n === null || n === undefined || n === "" ? "—" : (redondo ? fmtEurRedondo : fmtEur).format(Number(n));

const aFecha = (d) => new Date(String(d).length === 10 ? `${d}T12:00:00` : d);
const fmtFecha = new Intl.DateTimeFormat("es-ES", { weekday: "short", day: "numeric", month: "short" });
const fmtFechaAnyo = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric" });
const fmtFechaHora = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const fmtHora = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });

export const fecha = (d) => (d ? fmtFecha.format(aFecha(d)) : "");
export const fechaAnyo = (d) => (d ? fmtFechaAnyo.format(aFecha(d)) : "");
export const fechaHora = (iso) => (iso ? fmtFechaHora.format(new Date(iso)) : "—");
export const hora = (iso) => (iso ? fmtHora.format(new Date(iso)) : "");
// Las horas de los vuelos vienen en hora local del aeropuerto, sin zona: se muestran tal cual
export const horaLocal = (iso) => (iso ? String(iso).slice(11, 16) : "");

export function hace(iso) {
  if (!iso) return "nunca";
  const seg = Math.round((Date.now() - new Date(iso)) / 1000);
  const futuro = seg < 0;
  const s = Math.abs(seg);
  if (s < 45) return futuro ? "en unos segundos" : "ahora mismo";
  const m = Math.round(s / 60);
  const texto = m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} días`;
  return futuro ? `en ${texto}` : `hace ${texto}`;
}

/** "12:34" hasta una fecha (o "ahora" si ya pasó). */
export function cuentaAtras(iso) {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((new Date(iso) - Date.now()) / 1000));
  if (s === 0) return "ahora";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const seg = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(seg).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(seg).padStart(2, "0")}`;
}

export const diasHasta = (d) => Math.round((aFecha(d) - new Date()) / 86400000);

/** Bandera emoji a partir del código de país (ES → 🇪🇸). */
export const bandera = (pais) =>
  pais && pais.length === 2 ? String.fromCodePoint(...[...pais.toUpperCase()].map((c) => 127397 + c.charCodeAt(0))) : "🌍";

// ---------------------------------------------------------------------------
// Limpieza al cambiar de pantalla (suscripciones en tiempo real, intervalos...)
// ---------------------------------------------------------------------------
let limpiezas = [];
export const alSalir = (fn) => limpiezas.push(fn);
export function limpiarPantalla() {
  limpiezas.forEach((fn) => {
    try { fn(); } catch (e) { console.warn(e); }
  });
  limpiezas = [];
}
export function cadaSegundos(segundos, fn) {
  const id = setInterval(fn, segundos * 1000);
  alSalir(() => clearInterval(id));
  return id;
}

// ---------------------------------------------------------------------------
// Animaciones
// ---------------------------------------------------------------------------
const sinMovimiento = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Anima un número de "desde" a "hasta" dentro de un elemento. */
export function contarHasta(el, hasta, { desde = 0, formato = (n) => eur(n), duracion = 900 } = {}) {
  if (!el) return;
  if (hasta === null || hasta === undefined) {
    el.textContent = "—";
    return;
  }
  if (sinMovimiento() || desde === hasta) {
    el.textContent = formato(hasta);
    return;
  }
  const inicio = performance.now();
  const paso = (t) => {
    const p = Math.min(1, (t - inicio) / duracion);
    const suave = 1 - Math.pow(1 - p, 4);
    el.textContent = formato(desde + (hasta - desde) * suave);
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}

/** Código de aeropuerto en fichas de panel de salidas (accesible como texto normal). */
export function tablero(codigo) {
  const letras = [...String(codigo || "")].map((l) => `<span class="letra" aria-hidden="true">${esc(l)}</span>`).join("");
  return `<span class="tablero" role="img" aria-label="${esc(codigo)}">${letras}</span>`;
}

/** Las fichas giran unas vueltas y se quedan en su letra, como en un aeropuerto (no con movimiento reducido). */
export function animarTableros(raiz = document) {
  if (sinMovimiento()) return;
  const abecedario = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  raiz.querySelectorAll(".tablero").forEach((t) => {
    [...t.querySelectorAll(".letra")].forEach((ficha, i) => {
      const final = ficha.textContent;
      let vueltas = 4 + i * 3;
      const id = setInterval(() => {
        ficha.classList.remove("gira");
        void ficha.offsetWidth;
        ficha.classList.add("gira");
        if (--vueltas <= 0) {
          ficha.textContent = final;
          clearInterval(id);
          return;
        }
        ficha.textContent = abecedario[Math.floor(Math.random() * abecedario.length)];
      }, 60);
      alSalir(() => {
        clearInterval(id);
        ficha.textContent = final;
      });
    });
  });
}

/** Destello verde (baja) o rojo (sube) al cambiar un precio en directo. */
export function destello(el, sentido) {
  if (!el) return;
  el.classList.remove("destello-baja", "destello-sube");
  void el.offsetWidth;
  el.classList.add(sentido < 0 ? "destello-baja" : "destello-sube");
}

/** Efecto de onda al pulsar botones. */
export function activarOndas() {
  document.addEventListener("pointerdown", (ev) => {
    const boton = ev.target.closest("button, .boton");
    if (!boton || sinMovimiento()) return;
    const r = boton.getBoundingClientRect();
    const onda = document.createElement("span");
    const lado = Math.max(r.width, r.height);
    onda.className = "onda";
    onda.style.cssText = `width:${lado}px;height:${lado}px;left:${ev.clientX - r.left - lado / 2}px;top:${ev.clientY - r.top - lado / 2}px`;
    boton.append(onda);
    setTimeout(() => onda.remove(), 650);
  });
}

// ---------------------------------------------------------------------------
// Aeropuertos (datos públicos de OurAirports, ~4000 con vuelos regulares)
// ---------------------------------------------------------------------------
let cacheAeropuertos = null;
export async function aeropuertos() {
  if (!cacheAeropuertos) {
    const lista = await fetch("data/aeropuertos.json").then((r) => r.json());
    const mapa = new Map(lista.map((a) => [a.c, a]));
    const quitarTildes = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    for (const a of lista) a._txt = quitarTildes(`${a.c} ${a.es || ""} ${a.n} ${a.m} ${a.pn} ${a.k}`);
    cacheAeropuertos = { lista, mapa, quitarTildes };
  }
  return cacheAeropuertos;
}

export function nombreAeropuerto(datos, codigo, conCodigo = true) {
  const a = datos?.mapa.get(codigo);
  if (!a) return codigo;
  const nombre = a.es || a.m || a.n;
  return conCodigo ? `${nombre} (${codigo})` : nombre;
}

/** Aeropuertos de salida y de llegada de una búsqueda: el principal y los alternativos (sin repetir). */
export function aeropuertosDe(b) {
  const unicos = (lista) => [...new Set(lista.filter(Boolean))];
  return {
    origenes: unicos([b.origen, ...(b.origenes_extra || [])]),
    destinos: [b.destino], // la llegada es siempre una (solo puede haber varias salidas)
  };
}

/** Aeropuertos a menos de `km` de otro, del más cercano al más lejano (Sevilla → Jerez, 75 km). */
export function aeropuertosCercanos(datos, codigo, { km = 150, limite = 3, excluir = [] } = {}) {
  const a = datos?.mapa.get(codigo);
  if (!a || a.la == null) return [];
  const rad = Math.PI / 180;
  const distancia = (b) => {
    const h = Math.sin(((b.la - a.la) * rad) / 2) ** 2
      + Math.cos(a.la * rad) * Math.cos(b.la * rad) * Math.sin(((b.lo - a.lo) * rad) / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  };
  return datos.lista
    .filter((b) => b.c !== codigo && b.la != null && !excluir.includes(b.c))
    .map((b) => ({ aeropuerto: b, km: Math.round(distancia(b)) }))
    .filter((x) => x.km <= km)
    .sort((x, y) => x.km - y.km)
    .slice(0, limite);
}

export function buscarAeropuertos(datos, texto, limite = 8) {
  const q = datos.quitarTildes(texto.trim());
  if (q.length < 2) return [];
  const exacto = datos.mapa.get(texto.trim().toUpperCase());
  const palabras = q.split(/\s+/);
  const encontrados = datos.lista.filter((a) => palabras.every((p) => a._txt.includes(p)));
  // Primero los que tienen nombre en español (los más habituales) y los de España
  encontrados.sort((x, y) => (y.es ? 1 : 0) - (x.es ? 1 : 0) || (y.p === "ES") - (x.p === "ES"));
  const res = exacto ? [exacto, ...encontrados.filter((a) => a !== exacto)] : encontrados;
  return res.slice(0, limite);
}

// ---------------------------------------------------------------------------
// Avisos en pantalla y confirmaciones
// ---------------------------------------------------------------------------
// Notificaciones al estilo de Sileo (ver notificaciones.js)
export { aviso } from "./notificaciones.js";

/** Ventana de confirmación bonita. Devuelve una promesa con true/false. */
export function confirmar({ titulo, texto, aceptar = "Confirmar", peligro = true }) {
  return new Promise((resolver) => {
    const fondo = document.createElement("div");
    fondo.className = "modal-fondo";
    fondo.innerHTML = `
      <div class="tarjeta modal" role="dialog" aria-modal="true" aria-labelledby="modal-titulo">
        <h2 id="modal-titulo">${peligro ? icono("aviso") : ""}${esc(titulo)}</h2>
        <p class="suave">${esc(texto)}</p>
        <div class="fila">
          <button type="button" data-no>Cancelar</button>
          <button type="button" class="${peligro ? "peligro" : "primario"}" data-si>${esc(aceptar)}</button>
        </div>
      </div>`;
    const cerrar = (valor) => {
      fondo.remove();
      document.removeEventListener("keydown", tecla);
      resolver(valor);
    };
    const tecla = (ev) => ev.key === "Escape" && cerrar(false);
    fondo.addEventListener("click", (ev) => ev.target === fondo && cerrar(false));
    fondo.querySelector("[data-no]").addEventListener("click", () => cerrar(false));
    fondo.querySelector("[data-si]").addEventListener("click", () => cerrar(true));
    document.addEventListener("keydown", tecla);
    document.body.append(fondo);
    fondo.querySelector("[data-si]").focus();
  });
}

/** Pone un botón en estado "cargando" mientras dura la promesa. */
export async function conCarga(boton, promesa) {
  boton?.classList.add("cargando");
  if (boton) boton.disabled = true;
  try {
    return await promesa;
  } finally {
    boton?.classList.remove("cargando");
    if (boton) boton.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Textos de búsquedas
// ---------------------------------------------------------------------------
export function pasajerosTexto(b) {
  const p = [`${b.adultos} adulto${b.adultos !== 1 ? "s" : ""}`];
  if (b.ninos) p.push(`${b.ninos} niño${b.ninos !== 1 ? "s" : ""}`);
  if (b.bebes) p.push(`${b.bebes} bebé${b.bebes !== 1 ? "s" : ""}`);
  return p.join(", ");
}

export function maletasTexto(b) {
  const m = [];
  if (b.maletas_cabina) m.push(`${b.maletas_cabina} de cabina`);
  if (b.maletas_20kg) m.push(`${b.maletas_20kg} de 20 kg`);
  return m.length ? `Maletas: ${m.join(", ")}` : "Sin maletas extra";
}

// ---- Cualquier destino ----
/** Países con riesgo para viajar (guerra o conflicto), que "cualquier destino" evita por defecto. Lista orientativa
 * según las recomendaciones de viaje del Ministerio de Asuntos Exteriores (las actuales, en exteriores.gob.es);
 * en cada búsqueda se pueden quitar o añadir países. */
export const PAISES_RIESGO = ["AF", "BF", "BY", "CF", "HT", "IL", "IQ", "IR", "KP", "LB", "LY", "ML", "MM", "NE", "PS",
  "RU", "SD", "SO", "SS", "SY", "UA", "VE", "YE"];
export const esCualquiera = (b) => Boolean(b?.cualquier_destino);

let mapaPaises = null;
const regiones = (() => {
  try {
    return new Intl.DisplayNames(["es"], { type: "region" });
  } catch {
    return null;
  }
})();
/** Nombre de un país por su código: en español si el navegador lo sabe; si no, el de la lista de aeropuertos. */
export function nombrePais(datos, codigo) {
  if (!mapaPaises) {
    mapaPaises = new Map();
    for (const a of datos?.lista || []) if (a.p && a.pn && !mapaPaises.has(a.p)) mapaPaises.set(a.p, a.pn);
  }
  let nombre = null;
  try {
    nombre = codigo ? regiones?.of(codigo) : null;
  } catch {}
  return (nombre && nombre !== codigo ? nombre : mapaPaises.get(codigo)) || codigo;
}
/** Países con aeropuertos (y los de riesgo), como [código, nombre], por orden alfabético. */
export const listaPaises = (datos) => {
  nombrePais(datos, "");
  return [...new Set([...mapaPaises.keys(), ...PAISES_RIESGO])]
    .map((c) => [c, nombrePais(datos, c)])
    .sort((x, y) => x[1].localeCompare(y[1], "es"));
};

/** Ruta de "cualquier destino": tus aeropuertos → un globo. */
export function rutaCualquieraHtml(datos, b, grande = false) {
  const { origenes } = aeropuertosDe(b);
  const ciudad = (c) => esc(datos?.mapa?.get(c)?.es || datos?.mapa?.get(c)?.m || c);
  const mas = origenes.length > 1 ? `<div class="alternativos">o ${origenes.slice(1).map(esc).join(" · ")}</div>` : "";
  const primero = b.info?.top_destinos?.[0];
  return `
    <div class="ruta ${grande ? "grande" : ""}" title="Cualquier destino">
      <div class="aeropuerto"><div class="codigo">${tablero(origenes[0])}</div><div class="ciudad">${ciudad(origenes[0])}</div>${mas}</div>
      <div class="trazo">${icono("avion")}</div>
      <div class="aeropuerto fin"><div class="codigo"><span class="globo-destino" aria-hidden="true">${icono("globo")}</span></div>
        <div class="ciudad">${primero ? `Ahora: ${ciudad(primero.destino)}` : "Cualquier destino"}</div></div>
    </div>`;
}

/** Top de destinos: compacto (tarjeta del panel) o completo, con "Vigilar este destino" (detalle). */
export function topDestinosHtml(datos, b, completo = false) {
  const top = b.info?.top_destinos || [];
  const ciudad = (t) => esc(datos?.mapa?.get(t.destino)?.es || datos?.mapa?.get(t.destino)?.m || t.nombre || t.destino);
  if (!top.length) {
    return completo ? `<p class="suave">${b.ultima_revision ? "Ningún destino cumple ahora tus filtros." : "El robot está mirando todos los destinos: en unos minutos verás aquí los 5 más baratos."}</p>` : "";
  }
  if (!completo) {
    return `<ol class="top-mini" aria-label="Destinos más baratos">${top.slice(0, 3).map((t, i) =>
      `<li><span class="puesto">${i + 1}</span>${ciudad(t)} <b>${eur(t.precio_total, true)}</b></li>`).join("")}</ol>`;
  }
  return `<ol class="top-destinos">${top.map((t, i) => {
    const vuelos = t.escalas ? `${t.escalas} escala${t.escalas > 1 ? "s" : ""}` : "directo";
    const fechas = `${fecha(t.fecha_ida)}${t.fecha_vuelta ? ` → ${fecha(t.fecha_vuelta)}` : ""}`;
    return `<li>
      <span class="puesto">${i + 1}</span>
      <div><span class="destino-nombre">${ciudad(t)}</span> <span class="tenue pequeno">${esc(nombrePais(datos, t.pais))} · ${esc(t.destino)}</span>
        <small>${esc(fechas)} · ${esc((t.aerolineas || []).join(", "))} · ${vuelos}</small></div>
      <div class="top-precio">${eur(t.precio_total)}</div>
      <button type="button" class="pequeno primario" data-vigilar="${esc(t.destino)}">${icono("ubicacion")}Vigilar este destino</button>
    </li>`;
  }).join("")}</ol>`;
}

/** Vuelos de un viaje con varios destinos (Sevilla → Cracovia → Zúrich → Sevilla), o null si no lo es. */
export const tramosViaje = (b) => (b?.modo === "fechas" && (b.tramos_viaje || []).length >= 2 ? b.tramos_viaje : null);

/** Recorrido de un viaje con varios destinos: fichas de panel de salidas unidas por aviones. */
export function recorridoHtml(datos, b, grande = false) {
  const tramos = tramosViaje(b);
  if (!tramos) return "";
  const paradas = [tramos[0].origen, ...tramos.map((t) => t.destino)];
  const ciudad = (c) => datos?.mapa?.get(c)?.es || datos?.mapa?.get(c)?.m || c;
  return `
    <div class="recorrido ${grande ? "grande" : ""}" role="img" aria-label="${esc(paradas.map(ciudad).join(", luego "))}">
      ${paradas.map((c, i) => `${i ? `<span class="paso-ruta" aria-hidden="true">${icono("avion")}</span>` : ""}${tablero(c)}`).join("")}
    </div>
    <div class="recorrido-ciudades">${esc(paradas.map(ciudad).join(" → "))}</div>`;
}

export function fechasTexto(b) {
  const tramos = tramosViaje(b);
  if (tramos) return `${tramos.length} vuelos · ${fecha(tramos[0].fecha)} → ${fecha(tramos.at(-1).fecha)}`;
  if (b.modo === "chollo") {
    const noches = b.ida_vuelta ? ` · ${b.noches_min}-${b.noches_max} noches` : "";
    return `Del ${fecha(b.chollo_desde)} al ${fecha(b.chollo_hasta)}${noches}`;
  }
  const flex = b.flex_dias ? ` (±${b.flex_dias} d)` : "";
  const extra = (b.fechas_extra || []).length;
  const otras = extra ? ` · y ${extra} fecha${extra > 1 ? "s" : ""} más` : "";
  return b.ida_vuelta ? `${fecha(b.fecha_ida)} → ${fecha(b.fecha_vuelta)}${flex}${otras}` : `${fecha(b.fecha_ida)}${flex} · solo ida${otras}`;
}

export function generarCodigo() {
  const letras = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return [...bytes].map((x) => letras[x % letras.length]).join("");
}

/** Variación entre dos precios para mostrar ▼/▲. */
/** Mensajes técnicos de versiones anteriores del robot, explicados (los nuevos ya vienen en español). */
export function estadoLegible(texto) {
  const t = String(texto ?? "");
  if (/^Pendiente: no dio tiempo/.test(t)) return "En cola: no dio tiempo en esta vuelta; se revisa en la siguiente, en unos minutos";
  if (/SearchParseError|ds:1 payload/i.test(t)) {
    return "No se pudo consultar en esta ronda: Google ha devuelto una página sin vuelos; suele ser un fallo puntual suyo (se reintenta en unos minutos)";
  }
  return t.replace(/:\s*[A-Z]\w*(Error|Exception):\s[\s\S]*$/, ": fallo puntual al consultar la web (se reintenta en unos minutos)");
}

/** Solo se enlaza a direcciones https:// (nunca javascript: ni similares). */
export const esHttps = (url) => /^https:\/\/[^\s"'<>]+$/.test(String(url || ""));

/** Días entre dos fechas "AAAA-MM-DD…" (horas locales de cada aeropuerto, sin zonas). */
const diasEntre = (a, b) => Math.round((Date.parse(String(b).slice(0, 10)) - Date.parse(String(a).slice(0, 10))) / 86400000);

/**
 * Fechas y horas de los vuelos que cuestan el precio mostrado (la mejor opción de la última revisión):
 * IDA vie, 16 oct · 06:40–09:15 | VUELTA dom, 18 oct · 16:35–18:55 | 2 noches.
 * Admite una fila de precios completa (con detalle) o una con solo ida/vuelta.
 */
export function fechasPrecioHtml(p) {
  if (!p?.fecha_ida) return "";
  const tramo = (etiqueta, dia, tr) => {
    const t0 = tr?.tramos?.[0];
    const t1 = tr?.tramos?.at(-1);
    const escalas = tr?.tramos?.length ? (tr.tramos.length === 1 ? "directo" : `${tr.tramos.length - 1} escala${tr.tramos.length > 2 ? "s" : ""}`) : "";
    const mas = t0 && t1 ? diasEntre(t0.salida, t1.llegada) : 0;
    const horas = t0 && t1
      ? `<span class="fp-horas" title="${escalas}">${horaLocal(t0.salida)}–${horaLocal(t1.llegada)}${mas > 0 ? `<sup>+${mas}</sup>` : ""}</span>`
      : "";
    return `<div class="fp-tramo"><span class="fp-etq">${etiqueta}</span><b class="fp-fecha">${esc(fecha(dia))}</b>${horas}</div>`;
  };
  const ida = p.ida ?? p.detalle?.ida;
  const vuelta = p.vuelta ?? p.detalle?.vuelta;
  const siguientes = p.siguientes ?? p.detalle?.siguientes ?? [];
  if (siguientes.length) {
    // Varios destinos: un hueco por vuelo y los días que dura el viaje
    const vuelos = [ida, ...siguientes];
    const dias = diasEntre(vuelos[0].tramos[0].salida, vuelos.at(-1).tramos[0].salida);
    return `
      <div class="fp varios" aria-label="Vuelos de este precio">
        ${vuelos.map((tr, i) => tramo(`Vuelo ${i + 1}`, tr.tramos[0].salida.slice(0, 10), tr)).join("")}
        <div class="fp-noches">${icono("luna")}${dias} noche${dias === 1 ? "" : "s"} de viaje</div>
      </div>`;
  }
  const noches = p.fecha_vuelta ? diasEntre(p.fecha_ida, p.fecha_vuelta) : null;
  return `
    <div class="fp ${p.fecha_vuelta ? "" : "solo-ida"}" aria-label="Vuelos de este precio">
      ${tramo("Ida", p.fecha_ida, ida)}
      ${p.fecha_vuelta ? tramo("Vuelta", p.fecha_vuelta, vuelta) : ""}
      ${noches !== null ? `<div class="fp-noches">${icono("luna")}${noches === 0 ? "Vuelves el mismo día" : `${noches} noche${noches === 1 ? "" : "s"}`}</div>` : ""}
    </div>`;
}

export function deltaHtml(diferencia, { conIcono = true } = {}) {
  if (diferencia === null || diferencia === undefined || Number.isNaN(diferencia)) return "";
  const d = Math.round(diferencia * 100) / 100;
  if (Math.abs(d) < 0.01) return `<span class="delta igual">${conIcono ? icono("igual") : ""}igual</span>`;
  const baja = d < 0;
  return `<span class="delta ${baja ? "baja" : "sube"}">${conIcono ? icono(baja ? "baja" : "sube") : ""}${baja ? "−" : "+"}${eur(Math.abs(d))}</span>`;
}
