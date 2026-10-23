import { api } from "../api.js";
import { botonComprado, yaHeComprado } from "../comprado.js";
import { graficaPrecios } from "../graficas.js";
import { icono } from "../iconos.js";
import {
  $, aeropuertos, aeropuertosDe, alSalir, animarTableros, tablero, aviso, cadaSegundos, confirmar, contarHasta, cuentaAtras, deltaHtml, destello, esc, eur,
  esCualquiera, esHttps, estadoLegible, fecha, recorridoHtml, rutaCualquieraHtml, topDestinosHtml, tramosViaje, fechaHora, fechasPrecioHtml, fechasTexto, hace, horaLocal, limpiarPantalla, maletasTexto, pasajerosTexto,
} from "../util.js";

const NOMBRE_FUENTE = { google_flights: "Google Flights", ryanair: "Ryanair", skyscanner: "Skyscanner" };
const TIPO_AVISO = {
  presupuesto: "Dentro de presupuesto", buen_momento: "Buen momento para comprar", proximo: "Viaje próximo",
  final: "Último aviso", bajada: "Ha bajado todavía más", bajada_fuerte: "Bajada fuerte de precio", cerca_objetivo: "Muy cerca de tu objetivo", chollo: "Chollo", sin_presupuesto: "Nada dentro de presupuesto",
};
const PERIODOS = { "24h": 1, "7d": 7, todo: null };

// ---------------------------------------------------------------------------
// Vuelos como tarjeta de embarque
// ---------------------------------------------------------------------------
function lineaTrayecto(etiqueta, tr, aerolineas) {
  if (!tr) return "";
  const t0 = tr.tramos[0];
  const t1 = tr.tramos[tr.tramos.length - 1];
  const vuelos = tr.tramos.map((t) => {
    const vende = aerolineas.get(t.aerolinea)?.nombre || t.aerolinea;
    const opera = t.operadora && t.operadora !== t.aerolinea ? ` · opera ${aerolineas.get(t.operadora)?.nombre || t.operadora}` : "";
    return `${esc(vende)} ${esc(t.aerolinea)}${esc(t.numero)}${esc(opera)}`;
  }).join(" + ");
  const minutos = Math.round((new Date(t1.llegada) - new Date(t0.salida)) / 60000);
  const duracion = minutos > 0 ? `${Math.floor(minutos / 60)} h ${String(minutos % 60).padStart(2, "0")} min` : "";
  const escalas = tr.tramos.length === 1 ? "Directo" : `${tr.tramos.length - 1} escala${tr.tramos.length > 2 ? "s" : ""} · ${tr.tramos.slice(0, -1).map((t) => esc(t.destino)).join(", ")}`;
  const puntosEscala = tr.tramos.slice(0, -1).map((_, i) => `<i style="left:${((i + 1) / tr.tramos.length) * 100}%"></i>`).join("");
  const diaSiguiente = t1.llegada.slice(0, 10) > t0.salida.slice(0, 10) ? ' <span class="chip alerta">+1 día</span>' : "";
  return `
    <div class="trayecto-fila">
      <div class="sentido">${etiqueta}<b>${fecha(t0.salida.slice(0, 10))}</b></div>
      <div>
        <div class="linea-vuelo">
          <div class="hora">${horaLocal(t0.salida)}<small>${esc(t0.origen)}</small></div>
          <div class="camino">${duracion}<div class="barra">${puntosEscala}${icono("avion")}</div>${escalas}</div>
          <div class="hora fin">${horaLocal(t1.llegada)}${diaSiguiente}<small>${esc(t1.destino)}</small></div>
        </div>
        <div class="pequeno tenue" style="margin-top:.35rem">${vuelos}</div>
      </div>
    </div>`;
}

/** Botones de compra: la página de reserva de Google Flights con esos vuelos ya elegidos. */
function botonesComprar(p, { grande = false } = {}) {
  const d = p?.detalle || {};
  const clase = `boton primario ${grande ? "" : "pequeno"}`;
  if (d.comprar?.length) {
    return d.comprar.map((e) =>
      esHttps(e.url) ? `<a class="${clase}" href="${esc(e.url)}" target="_blank" rel="noopener">${icono("etiqueta")}${esc(e.texto)}</a>` : "").join("");
  }
  return d.google_flights
    ? `<a class="${clase}" href="${esc(d.google_flights)}" target="_blank" rel="noopener">${icono("etiqueta")}Ver en Google Flights</a>` : "";
}

/** Si sales de un aeropuerto (p. ej. Jerez) y la vuelta llega a otro (p. ej. Sevilla). */
function vueltaAOtro(d) {
  const sales = d.ida?.tramos?.[0]?.origen;
  const llegas = d.vuelta?.tramos?.at(-1)?.destino;
  return sales && llegas && sales !== llegas ? { sales, llegas } : null;
}

function tarjetaVuelo(p, aerolineas, esMejor) {
  const d = p.detalle || {};
  const enlaces = (d.enlaces || []).map((e) =>
    esHttps(e.url) ? `<a class="boton pequeno" href="${esc(e.url)}" target="_blank" rel="noopener">${icono("externo")}${esc(e.aerolinea)}</a>` : "").join("");
  return `
    <div class="vuelo ${esMejor ? "mejor" : ""}">
      <div class="vuelo-cabecera">
        <div class="total">${eur(p.precio_total)}</div>
        <div class="fila" style="gap:.35rem">
          ${esMejor ? `<span class="chip ok">${icono("check")}La mejor</span>` : ""}
          <span class="chip">${esc(NOMBRE_FUENTE[p.fuente] || p.fuente)}</span>
          ${d.billetes_separados ? `<span class="chip alerta">${icono("aviso")}${(d.siguientes || []).length ? (d.siguientes.length + 1) : 2} billetes</span>` : ""}
          ${vueltaAOtro(d) ? `<span class="chip alerta">${icono("intercambiar")}Vuelves a ${esc(vueltaAOtro(d).llegas)}</span>` : ""}
        </div>
      </div>
      ${(d.siguientes || []).length
        ? [d.ida, ...d.siguientes].map((tr, i) => lineaTrayecto(`Vuelo ${i + 1}`, tr, aerolineas)).join("")
        : lineaTrayecto("Ida", d.ida, aerolineas)}
      ${d.vuelta ? lineaTrayecto("Vuelta", d.vuelta, aerolineas) : ""}
      <div class="vuelo-pie">
        <div class="desglose">
          <span>Billetes ${eur(p.precio_billetes)}${Number(p.precio_maletas) ? ` · maletas ${eur(p.precio_maletas)} <span class="chip alerta" title="${esc((d.desglose_maletas || []).join("\n"))}">máx. estimado</span>` : ""}${Number(p.descuento) ? ` · descuento −${eur(p.descuento)}` : ""}</span>
          ${vueltaAOtro(d) ? `<span style="color:var(--alerta)">Sales de ${esc(vueltaAOtro(d).sales)} y vuelves a ${esc(vueltaAOtro(d).llegas)}: más barato así.</span>` : ""}
          ${(d.notas || []).map((n) => `<span class="tenue">${esc(n)}</span>`).join("")}
        </div>
        <div class="acciones">${botonesComprar(p)}${enlaces}
          ${d.google_flights && d.comprar?.length && !(d.siguientes || []).length ? `<a class="boton pequeno fantasma" href="${esc(d.google_flights)}" target="_blank" rel="noopener">${icono("lupa")}Ver los más baratos</a>` : ""}</div>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Estadísticas, veredicto e historial de precios
// ---------------------------------------------------------------------------
function cambiosDePrecio(puntos) {
  const cambios = [];
  for (let i = 1; i < puntos.length; i++) {
    const antes = Number(puntos[i - 1].precio_total);
    const ahora = Number(puntos[i].precio_total);
    if (Math.abs(ahora - antes) >= 0.01) cambios.push({ en: puntos[i].revisado, antes, ahora });
  }
  return cambios.reverse();
}

function filaCambio(c) {
  const baja = c.ahora < c.antes;
  return `<li class="${baja ? "baja" : "sube"}">
    <span class="icono-cambio">${icono(baja ? "baja" : "sube")}</span>
    <div><b class="num">${eur(c.antes)} → ${eur(c.ahora)}</b><div class="pequeno tenue">${fechaHora(c.en)}</div></div>
    ${deltaHtml(c.ahora - c.antes, { conIcono: false })}
  </li>`;
}

/** Una fila por revisión: el precio de ese momento y si subió, bajó o siguió igual. */
function filaRevision(p, anterior) {
  const precio = Number(p.precio_total);
  const dif = anterior ? precio - Number(anterior.precio_total) : null;
  const clase = dif === null ? "primero" : Math.abs(dif) < 0.01 ? "igual" : dif < 0 ? "baja" : "sube";
  const icon = { primero: "chispas", igual: "igual", baja: "baja", sube: "sube" }[clase];
  const etiqueta = dif === null ? '<span class="chip primario">Primer precio</span>'
    : clase === "igual" ? '<span class="delta igual">sin cambios</span>' : deltaHtml(dif, { conIcono: false });
  return `<li class="${clase}">
    <span class="icono-cambio">${icono(icon)}</span>
    <div><b class="num">${eur(precio)}</b><div class="pequeno tenue">${fechaHora(p.revisado)}</div></div>
    ${etiqueta}
  </li>`;
}

function pintarEstadisticas(cont, puntos) {
  if (!puntos.length) {
    cont.innerHTML = '<p class="suave" style="grid-column:1/-1;margin:0">Las estadísticas aparecerán con el primer precio.</p>';
    return;
  }
  const valores = puntos.map((p) => Number(p.precio_total));
  const actual = valores.at(-1);
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const media = valores.reduce((a, b) => a + b, 0) / valores.length;
  const total = actual - valores[0];
  cont.innerHTML = `
    <div class="estadistica"><div class="etiqueta">Ahora</div><div class="valor">${eur(actual)}</div></div>
    <div class="estadistica"><div class="etiqueta">Mínimo</div><div class="valor" style="color:var(--ok)">${eur(min)}</div></div>
    <div class="estadistica"><div class="etiqueta">Máximo</div><div class="valor" style="color:var(--mal)">${eur(max)}</div></div>
    <div class="estadistica"><div class="etiqueta">Media</div><div class="valor">${eur(media)}</div></div>
    <div class="estadistica"><div class="etiqueta">Desde el inicio</div><div class="valor">${valores.length > 1 ? deltaHtml(total) : "—"}</div></div>
    <div class="estadistica"><div class="etiqueta">Revisiones</div><div class="valor">${valores.length}</div></div>`;
}

/** ¿Está cerca de tu objetivo? ¿Es buen precio comparado con lo visto? Para decidir si comprar ya. */
function veredictoHtml(actual, puntos, presupuesto) {
  if (actual === null || actual === undefined) return "";
  const partes = [];
  if (presupuesto) {
    const objetivo = Number(presupuesto);
    const dif = actual - objetivo;
    if (dif <= 0.005) {
      partes.push(`<span class="chip ok">${icono("check")}Dentro de tu objetivo de ${eur(objetivo, true)}${dif < -0.5 ? ` · ${eur(-dif)} por debajo` : ""}</span>`);
    } else {
      partes.push(`<span class="chip alerta">${icono("euro")}A ${eur(dif)} de tu objetivo de ${eur(objetivo, true)} (+${Math.round((dif / objetivo) * 100)} %)</span>`);
      partes.push(`<div class="medidor" title="Lo cerca que está de tu objetivo"><span style="width:${Math.max(4, Math.min(100, Math.round((objetivo / actual) * 100)))}%"></span></div>`);
    }
  }
  const valores = puntos.map((p) => Number(p.precio_total));
  if (valores.length >= 3) {
    const min = Math.min(...valores);
    const media = valores.reduce((a, b) => a + b, 0) / valores.length;
    const pct = Math.round((Math.abs(actual - media) / media) * 100);
    if (actual <= min + 0.005) partes.push(`<span class="chip ok">${icono("llama")}El precio más bajo visto hasta ahora</span>`);
    else if (pct === 0) partes.push(`<span class="chip">${icono("igual")}Justo en la media de lo visto</span>`);
    else if (actual < media) partes.push(`<span class="chip ok">${icono("baja")}${pct} % por debajo de la media</span>`);
    else partes.push(`<span class="chip mal">${icono("sube")}${pct} % por encima de la media</span>`);
    if (actual > min + 0.005) partes.push(`<span class="chip">${icono("etiqueta")}Mínimo visto: ${eur(min)}</span>`);
  } else {
    partes.push(`<span class="chip">${icono("info")}Tras unas cuantas revisiones te diré si es buen precio</span>`);
  }
  return partes.join("");
}

// ---------------------------------------------------------------------------
// Pantalla
// ---------------------------------------------------------------------------
export async function vistaDetalle(app, id) {
  const [busqueda, historialTodo, opcionesTodas, avisos, listaAerolineas, datos] = await Promise.all([
    api.busqueda(id), api.historial(id), api.ultimasOpciones(id), api.avisos(id), api.aerolineas(), aeropuertos(),
  ]);
  if (!busqueda) throw new Error("Esa búsqueda no existe.");
  let b = busqueda;
  const recargar = () => {
    limpiarPantalla();
    return vistaDetalle(app, id);
  };
  // Tras editar el viaje solo cuenta lo nuevo
  const historial = b.historial_desde ? historialTodo.filter((h) => h.revisado >= b.historial_desde) : historialTodo;
  const opciones = b.historial_desde ? opcionesTodas.filter((o) => o.revisado >= b.historial_desde) : opcionesTodas;
  const opcionesAntiguas = opciones.length && b.ultima_revision
    && new Date(b.ultima_revision) - new Date(opciones[0].revisado) > 10 * 60000;
  const aerolineas = new Map(listaAerolineas.map((a) => [a.codigo, a]));
  const info = b.info || {};
  const ciudad = (c) => esc(datos.mapa.get(c)?.es || datos.mapa.get(c)?.m || c);
  const { origenes, destinos } = aeropuertosDe(b);
  const alternativos = (lista) => (lista.length > 1
    ? `<div class="alternativos">o ${lista.slice(1).map((c) => `${esc(c)} · ${ciudad(c)}`).join(", ")}</div>` : "");
  const presupuesto = b.modo_precio === "presupuesto" ? b.presupuesto : null;
  const notaRechazos = (r) => {
    const lista = Object.entries(r || {});
    return lista.length ? `${icono("aviso")}<span><b>Vuelos descartados por tus filtros:</b> ${lista.map(([m, n]) => `${esc(m)} (${n})`).join(" · ")}</span>` : "";
  };
  const placeholderGrafica = `<div class="vacio" style="padding:2rem 1rem"><div class="ilustracion">${icono("grafica")}</div>
    <p>El robot está buscando tu vuelo con tus filtros. El primer precio aparecerá aquí solo, en unos minutos,
      y cada revisión añadirá un punto a la gráfica, suba, baje o se mantenga.</p></div>`;
  let periodo = historial.length > 72 ? "7d" : "todo";

  app.innerHTML = `
    <div>
      <section class="tarjeta heroe">
        <div class="fila entre" style="align-items:flex-start">
          <div>
            <h1 style="margin:0">${esc(b.nombre)}</h1>
          </div>
          <div class="acciones">
            ${botonComprado(b)}
            <a class="boton" href="#/editar/${b.id}">${icono("editar")}Editar</a>
            <button id="pausar">${icono(b.activa ? "pausa" : "play")}${b.activa ? "Pausar" : "Reanudar"}</button>
            <button id="borrar" class="peligro icono" title="Borrar">${icono("papelera")}</button>
          </div>
        </div>
        ${esCualquiera(b) ? `<div style="margin:1.4rem 0 1.2rem">${rutaCualquieraHtml(datos, b, true)}</div>` : tramosViaje(b) ? `<div class="ruta" style="display:block;margin:1.4rem 0 1.2rem">${recorridoHtml(datos, b, true)}</div>` : `
        <div class="ruta grande" style="margin:1.4rem 0 1.2rem">
          <div class="aeropuerto"><div class="codigo">${tablero(b.origen)}</div><div class="ciudad">${ciudad(b.origen)}</div>${alternativos(origenes)}</div>
          <div class="trazo">${icono("avion")}</div>
          <div class="aeropuerto fin"><div class="codigo">${tablero(b.destino)}</div><div class="ciudad">${ciudad(b.destino)}</div>${alternativos(destinos)}</div>
        </div>`}
        <div class="fila" style="gap:.45rem">
          ${b.modo === "chollo" ? `<span class="chip">${icono("llama")}Chollo: cualquier fecha</span>` : ""}
          <span class="chip">${icono("calendario")}${esc(fechasTexto(b))}</span>
          <span class="chip">${icono("personas")}${esc(pasajerosTexto(b))}</span>
          <span class="chip">${icono("maleta")}${esc(maletasTexto(b))}</span>
          <span class="chip">${icono("despegue")}${b.escalas_max === 0 ? "Solo directos" : `Máx. ${b.escalas_max} escala${b.escalas_max > 1 ? "s" : ""} de ${b.escala_max_horas} h`}</span>
          ${presupuesto ? `<span class="chip primario">${icono("euro")}Objetivo ${eur(presupuesto)}</span>` : `<span class="chip primario">${icono("baja")}Lo más barato</span>`}
          ${b.activa ? "" : `<span class="chip mal">${icono("pausa")}En pausa</span>`}
        </div>
      </section>
      ${esCualquiera(b) ? `
      <section class="tarjeta" style="margin-top:1.1rem">
        <div class="tarjeta-titulo"><h2>${icono("globo")}Los destinos más baratos</h2>
          <span class="pequeno tenue">con tus filtros · se revisa cada 2 horas</span></div>
        <div id="top-destinos">${topDestinosHtml(datos, b, true)}</div>
        <p class="ayuda">Pulsa «Vigilar este destino» y se crea una búsqueda normal a ese destino con tus mismos filtros y fechas.</p>
      </section>` : ""}

      <section class="tarjeta" style="margin-top:1.1rem">
        <div class="tarjeta-titulo">
          <div>
            <h2>${icono("grafica")}Precio en directo</h2>
            <div class="fila pequeno suave" style="margin-top:.35rem;gap:.9rem">
              ${b.activa ? '<span class="vivo"><span class="punto-vivo"></span>En directo</span>' : '<span class="chip mal">En pausa</span>'}
              <span>Próxima revisión <b class="cuenta-atras" id="cuenta">${b.activa ? cuentaAtras(b.proxima_revision) : "—"}</b></span>
              <span id="revisado"></span>
            </div>
          </div>
          <div class="fila">
            <div class="buscando oculto" id="buscando"></div>
            <div class="precio-grande gigante" id="precio-actual">—</div>
            <span id="delta-actual">${info.variacion != null ? deltaHtml(info.variacion) : ""}</span>
            <div class="precio-fechas" id="fechas-actual">${opciones.length && !opcionesAntiguas && b.precio_actual != null ? fechasPrecioHtml(opciones[0]) : ""}</div>
          </div>
        </div>
        <div class="fila-compra">
          <div class="veredicto" id="veredicto"></div>
          <div class="acciones" id="comprar-ya">${opciones.length && !opcionesAntiguas ? botonesComprar(opciones[0], { grande: true }) : ""}</div>
        </div>
        <div class="selector" id="selector" style="margin-bottom:.8rem">
          ${Object.keys(PERIODOS).map((p) => `<button type="button" data-periodo="${p}">${p === "24h" ? "24 h" : p === "7d" ? "7 días" : "Todo"}</button>`).join("")}
        </div>
        <div id="zona-grafica">${historial.length ? '<div class="grafica"><canvas id="grafica" aria-label="Evolución del precio total"></canvas></div>' : placeholderGrafica}</div>
        <div class="estadisticas" id="estadisticas" style="margin-top:1.1rem"></div>
        <div class="nota alerta ${Object.keys(info.rechazos || {}).length ? "" : "oculto"}" id="rechazos">${notaRechazos(info.rechazos)}</div>
        <div class="nota ${b.estado ? "" : "oculto"}" style="margin-top:.8rem">${icono("info")}<span id="estado">${esc(estadoLegible(b.estado))}</span></div>
      </section>

      <div class="rejilla-2" style="margin-top:1.1rem">
        <section class="tarjeta">
          <div class="tarjeta-titulo"><h2>${icono("avion")}Mejores vuelos ahora</h2>
            <span class="pequeno tenue" id="opciones-fecha">${opciones.length ? fechaHora(opciones[0].revisado) : ""}</span></div>
          <div id="opciones">
            ${opcionesAntiguas ? `<div class="nota alerta">${icono("aviso")}<span>Son de la revisión del ${fechaHora(opciones[0].revisado)}: en la última no hubo ninguna válida.</span></div>` : ""}
            ${opciones.length
              ? opciones.map((p, i) => tarjetaVuelo(p, aerolineas, i === 0)).join("")
              : '<p class="suave">Todavía no hay resultados: aparecerán aquí solos con la primera revisión.</p>'}
          </div>
          <p class="pequeno tenue" style="margin:.9rem 0 0">Precio total para todos los pasajeros. Puedes comprar cuando quieras, aunque no
            haya llegado a tu objetivo: compra siempre en la web oficial y comprueba el precio final antes de pagar.</p>
        </section>
        <div>
          <section class="tarjeta">
            <div class="tarjeta-titulo"><h2>${icono("reloj")}Historial de precios</h2>
              <div class="selector" id="vista-historial">
                <button type="button" data-vista="todas" class="activo">Todas</button>
                <button type="button" data-vista="cambios">Solo cambios</button>
              </div></div>
            <p class="pequeno suave" id="resumen-historial" style="margin-top:-.4rem"></p>
            <ul class="cambios" id="cambios"></ul>
          </section>
          <section class="tarjeta">
            <div class="tarjeta-titulo"><h2>${icono("campana")}Avisos enviados</h2></div>
            ${avisos.length ? `<ul class="linea-tiempo">${avisos.map((a) => `
              <li class="${a.entregado ? "ok" : ""}">
                <div class="fila entre"><b>${esc(TIPO_AVISO[a.tipo] || a.tipo)}</b><span class="cuando">${fechaHora(a.enviado)}</span></div>
                <div class="pequeno suave">${eur(a.precio_total)} · ${esc(a.motivo)}</div>
                <div class="pequeno ${a.entregado ? "" : "tenue"}">${a.entregado ? "✓ Enviado a Telegram" : "No enviado (Telegram sin vincular)"}</div>
              </li>`).join("")}</ul>` : '<p class="suave">Aún no hay avisos. Te escribiré por Telegram en cuanto sea buen momento.</p>'}
          </section>
        </div>
      </div>
    </div>`;

  animarTableros($(".ruta"));

  // ---- Precio actual (o "buscando…") y veredicto ----
  const precioEl = $("#precio-actual");
  const buscandoEl = $("#buscando");
  let precioMostrado = null;
  const mostrarPrecio = (ahora) => {
    const hay = ahora !== null && ahora !== undefined;
    precioEl.classList.toggle("oculto", !hay);
    buscandoEl.classList.toggle("oculto", hay);
    if (!hay) {
      buscandoEl.innerHTML = b.ultima_revision
        ? `${icono("aviso")}Sin vuelos válidos ahora mismo`
        : '<span class="anillo-mini"></span>Buscando tu vuelo…';
    } else if (ahora !== precioMostrado) {
      contarHasta(precioEl, ahora, { desde: precioMostrado ?? 0 });
      if (precioMostrado !== null) destello(precioEl.closest(".tarjeta"), ahora - precioMostrado);
    }
    precioMostrado = hay ? ahora : null;
    $("#veredicto").innerHTML = veredictoHtml(precioMostrado, historial, presupuesto);
  };
  mostrarPrecio(b.precio_actual != null ? Number(b.precio_actual) : null);
  pintarEstadisticas($("#estadisticas"), historial);

  // ---- Historial: todas las revisiones o solo los cambios ----
  let vistaHistorial = "todas";
  const listaCambios = $("#cambios");
  const pintarHistorial = (marcarNuevo = false) => {
    const cambios = cambiosDePrecio(historial);
    $("#resumen-historial").textContent = historial.length
      ? `${historial.length} revisi${historial.length === 1 ? "ón" : "ones"} · ${cambios.length} cambio${cambios.length === 1 ? "" : "s"} de precio`
      : "";
    if (vistaHistorial === "cambios") {
      listaCambios.innerHTML = cambios.length
        ? cambios.slice(0, 200).map(filaCambio).join("")
        : '<li class="suave" style="display:block">Sin cambios todavía: el precio se mantiene igual en cada revisión.</li>';
    } else {
      const ultimas = historial.slice(-200);
      const desplazamiento = historial.length - ultimas.length;
      listaCambios.innerHTML = ultimas.length
        ? ultimas.map((p, i) => filaRevision(p, historial[desplazamiento + i - 1])).reverse().join("")
        : '<li class="suave" style="display:block">Cada revisión del robot aparecerá aquí, haya cambiado el precio o no.</li>';
    }
    if (marcarNuevo) listaCambios.firstElementChild?.classList.add("nuevo");
  };
  pintarHistorial();
  app.querySelectorAll("[data-vista]").forEach((boton) =>
    boton.addEventListener("click", () => {
      vistaHistorial = boton.dataset.vista;
      app.querySelectorAll("[data-vista]").forEach((x) => x.classList.toggle("activo", x === boton));
      pintarHistorial();
    }),
  );

  // ---- Gráfica con periodos ----
  let grafica = null;
  const pintarGrafica = () => {
    grafica?.destruir();
    grafica = null;
    app.querySelectorAll("[data-periodo]").forEach((x) => x.classList.toggle("activo", x.dataset.periodo === periodo));
    const canvas = $("#grafica");
    if (!canvas) return;
    const dias = PERIODOS[periodo];
    const desde = dias ? new Date(Date.now() - dias * 86400000).toISOString() : null;
    const puntos = desde ? historial.filter((h) => h.revisado >= desde) : historial;
    grafica = graficaPrecios(canvas, puntos.length ? puntos : historial, { presupuesto });
  };
  pintarGrafica();
  alSalir(() => grafica?.destruir());
  app.querySelectorAll("[data-periodo]").forEach((boton) =>
    boton.addEventListener("click", () => {
      periodo = boton.dataset.periodo;
      pintarGrafica();
    }),
  );

  // ---- Cuenta atrás y "revisado hace…" ----
  const textoRevisado = () => (b.ultima_revision ? `Revisado ${hace(b.ultima_revision)}` : "Aún sin revisar");
  $("#revisado").textContent = textoRevisado();
  if (b.activa) cadaSegundos(1, () => { $("#cuenta").textContent = cuentaAtras(b.proxima_revision); });
  cadaSegundos(30, () => { $("#revisado").textContent = textoRevisado(); });

  // ---- Tiempo real: cada revisión añade su punto (suba, baje o siga igual) ----
  let tiempoRealActivo = false;
  alSalir(api.suscribir("precios", ({ new: p }) => {
    if (!p || p.busqueda !== id || p.es_mejor === false) return;
    if (historial.some((h) => h.revisado === p.revisado)) return;
    tiempoRealActivo = true;
    historial.push(p);
    if (!$("#grafica")) {
      $("#zona-grafica").innerHTML = '<div class="grafica"><canvas id="grafica" aria-label="Evolución del precio total"></canvas></div>';
      pintarGrafica();
    } else if (grafica) {
      grafica.añadir(p);
    } else {
      pintarGrafica();
    }
    pintarEstadisticas($("#estadisticas"), historial);
    pintarHistorial(true);
    mostrarPrecio(Number(p.precio_total));
  }, `busqueda=eq.${id}`));
  // Cualquier destino: "Vigilar este destino" abre el formulario con ese destino y tus mismos filtros
  const vigilar = (ev) => {
    const boton = ev.target.closest("[data-vigilar]");
    if (!boton) return;
    try {
      sessionStorage.setItem("vigilarDestino", JSON.stringify({ desde: id, destino: boton.dataset.vigilar }));
    } catch {}
    location.hash = `#/duplicar/${id}`;
  };
  app.addEventListener("click", vigilar);
  alSalir(() => app.removeEventListener("click", vigilar));
  alSalir(api.suscribir("busquedas", async ({ eventType, old, new: nueva }) => {
    // El robot la ha borrado (ha llegado el día del viaje) o se ha borrado desde Telegram
    if (eventType === "DELETE") {
      if (old?.id === id && location.hash.includes(id)) {
        aviso("Esta búsqueda se ha borrado");
        location.hash = "#/";
      }
      return;
    }
    if (!nueva || nueva.id !== id) return;
    tiempoRealActivo = true;
    b = { ...b, ...nueva };
    if (esCualquiera(b) && $("#top-destinos")) $("#top-destinos").innerHTML = topDestinosHtml(datos, b, true);
    $("#revisado").textContent = textoRevisado();
    $("#estado").textContent = estadoLegible(nueva.estado);
    $("#estado").closest(".nota").classList.toggle("oculto", !nueva.estado);
    const rechazos = $("#rechazos");
    rechazos.innerHTML = notaRechazos(nueva.info?.rechazos);
    rechazos.classList.toggle("oculto", !rechazos.innerHTML);
    mostrarPrecio(nueva.precio_actual != null ? Number(nueva.precio_actual) : null);
    $("#delta-actual").innerHTML = nueva.info?.variacion != null ? deltaHtml(nueva.info.variacion) : "";
    // Vuelos de la revisión nueva
    const nuevas = await api.ultimasOpciones(id);
    $("#fechas-actual").innerHTML = nuevas.length && nueva.precio_actual != null ? fechasPrecioHtml(nuevas[0]) : "";
    if (nuevas.length) {
      $("#opciones").innerHTML = nuevas.map((p, i) => tarjetaVuelo(p, aerolineas, i === 0)).join("");
      $("#comprar-ya").innerHTML = botonesComprar(nuevas[0], { grande: true });
      $("#opciones-fecha").textContent = fechaHora(nuevas[0].revisado);
    }
  }, `id=eq.${id}`));
  // Respaldo por si el tiempo real no está activado: recargar cada 90 s
  cadaSegundos(90, () => !tiempoRealActivo && recargar());

  // ---- Acciones ----
  $("#pausar").addEventListener("click", async () => {
    await api.actualizarBusqueda(b.id, { activa: !b.activa });
    aviso(b.activa ? "Búsqueda en pausa" : "Búsqueda reanudada: el robot la revisa en un minuto");
    recargar();
  });
  $("[data-comprado]").addEventListener("click", async () => {
    if (await yaHeComprado(b)) location.hash = "#/";
  });
  $("#borrar").addEventListener("click", async () => {
    const ok = await confirmar({
      titulo: "¿Borrar esta búsqueda?",
      texto: `Se borrarán "${b.nombre}" y todo su historial de precios. No se puede deshacer.`,
      aceptar: "Borrar",
    });
    if (!ok) return;
    try {
      await api.borrarBusqueda(b.id);
      aviso("Búsqueda borrada");
      location.hash = "#/";
    } catch (e) {
      aviso(e.message, "error");
    }
  });
}
