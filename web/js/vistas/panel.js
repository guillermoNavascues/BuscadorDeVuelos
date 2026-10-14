import { api } from "../api.js";
import { miniGrafica } from "../graficas.js";
import { icono } from "../iconos.js";
import {
  $, aeropuertos, aeropuertosDe, aviso, cadaSegundos, alSalir, tablero, contarHasta, cuentaAtras, deltaHtml, destello, esc, eur, fechaHora,
  esCualquiera, estadoLegible, fechasPrecioHtml, fechasTexto, hace, limpiarPantalla, pasajerosTexto, recorridoHtml,
  rutaCualquieraHtml, topDestinosHtml, tramosViaje,
} from "../util.js";

const TIPO_AVISO = {
  presupuesto: "Dentro de presupuesto", buen_momento: "Buen momento", proximo: "Viaje próximo", final: "Último aviso",
  bajada: "Ha bajado más", bajada_fuerte: "Bajada fuerte", cerca_objetivo: "Cerca de tu objetivo", chollo: "Chollo", sin_presupuesto: "Nada dentro de presupuesto",
};

function rutaHtml(datos, b) {
  if (tramosViaje(b)) return recorridoHtml(datos, b);
  if (esCualquiera(b)) return rutaCualquieraHtml(datos, b);
  const a = (c) => datos.mapa.get(c);
  const ciudad = (c) => esc(a(c)?.es || a(c)?.m || c);
  const { origenes, destinos } = aeropuertosDe(b);
  const alternativos = (lista) => (lista.length > 1 ? `<div class="alternativos">o ${lista.slice(1).map(esc).join(" · ")}</div>` : "");
  return `
    <div class="ruta" title="${b.ida_vuelta ? "Ida y vuelta" : "Solo ida"}">
      <div class="aeropuerto"><div class="codigo">${tablero(origenes[0])}</div><div class="ciudad">${ciudad(origenes[0])}</div>${alternativos(origenes)}</div>
      <div class="trazo">${icono("avion")}</div>
      <div class="aeropuerto fin"><div class="codigo">${tablero(destinos[0])}</div><div class="ciudad">${ciudad(destinos[0])}</div>${alternativos(destinos)}</div>
    </div>`;
}

/** Texto bajo el precio: lo lejos que está de tu objetivo, o el mínimo visto. */
function etiquetaPrecio(b) {
  if (b.precio_actual == null) return b.ultima_revision ? "sin vuelos válidos ahora mismo" : "primer precio en unos minutos";
  if (b.modo_precio === "presupuesto" && b.presupuesto != null) {
    const dif = Number(b.precio_actual) - Number(b.presupuesto);
    return dif <= 0.005 ? `✓ dentro de tu objetivo de ${eur(b.presupuesto, true)}` : `a ${eur(dif)} de tu objetivo de ${eur(b.presupuesto, true)}`;
  }
  return b.mejor_precio != null ? `mínimo visto ${eur(b.mejor_precio)}` : "precio total para todos";
}

/** Cuándo toca la siguiente revisión ("en cola" si ya debería haberse hecho). */
function textoProxima(b) {
  if (!b.activa) return "en pausa";
  const falta = new Date(b.proxima_revision) - Date.now();
  if (falta > 60000) return `próxima ${hace(b.proxima_revision)}`;
  return falta > -3 * 60000 ? "revisándose ahora" : `en cola desde ${hace(b.proxima_revision)}`;
}

function precioInicial(b) {
  if (b.precio_actual != null) return eur(b.precio_actual);
  return b.ultima_revision ? "—" : '<span class="buscando"><span class="anillo-mini"></span>Buscando…</span>';
}

/** Las fechas solo valen si son de la revisión que dio el precio actual (y no de antes de editar la búsqueda). */
const fechasDe = (b, p) =>
  b.precio_actual == null || !p || (b.historial_desde && p.revisado < b.historial_desde) ? "" : fechasPrecioHtml(p);

function tarjetaBusqueda(b, datos, mejor) {
  const variacion = b.info?.variacion;
  const presupuesto = b.modo_precio === "presupuesto"
    ? `<span class="chip ${b.precio_actual != null && Number(b.precio_actual) <= Number(b.presupuesto) ? "ok" : ""}">${icono("euro")}Objetivo ${eur(b.presupuesto, true)}</span>`
    : `<span class="chip primario">${icono("baja")}Lo más barato</span>`;
  const tipo = b.modo === "chollo" ? `<span class="chip alerta">${icono("llama")}Chollo</span>` : "";
  return `
    <article class="tarjeta interactiva busqueda ${b.activa ? "" : "pausada"} ${b.ultimo_aviso_precio != null ? "resaltada" : ""}" data-id="${b.id}">
      <div class="busqueda-cabecera">
        <div>
          <a href="#/busqueda/${b.id}" class="busqueda-nombre">${esc(b.nombre)}</a>
          <div class="fila" style="gap:.35rem;margin-top:.4rem">${tipo}${presupuesto}${b.activa ? "" : `<span class="chip mal">${icono("pausa")}En pausa</span>`}</div>
        </div>
        <button class="icono pequeno fantasma" data-pausar="${b.id}" title="${b.activa ? "Pausar" : "Reanudar"}">${icono(b.activa ? "pausa" : "play")}</button>
      </div>
      ${rutaHtml(datos, b)}
      <div class="fila pequeno suave" style="gap:.9rem">
        <span class="fila" style="gap:.3rem">${icono("calendario")}${esc(fechasTexto(b))}</span>
        <span class="fila" style="gap:.3rem">${icono("personas")}${esc(pasajerosTexto(b))}</span>
      </div>
      <div class="precio-bloque">
        <div>
          <div class="precio-grande" data-precio>${precioInicial(b)}</div>
          <div class="precio-etiqueta" data-etiqueta>${esc(etiquetaPrecio(b))}</div>
          <div class="precio-delta" data-delta>${variacion != null ? deltaHtml(variacion) : ""}</div>
        </div>
        <div class="precio-fechas" data-fechas>${fechasDe(b, mejor)}</div>
      </div>
      <div data-top>${esCualquiera(b) ? topDestinosHtml(datos, b) : ""}</div>
      <div class="mini-grafica"><canvas data-grafica="${b.id}" aria-label="Evolución del precio"></canvas></div>
      <div class="busqueda-pie">
        <span class="pequeno suave" data-estado>${esc(estadoLegible(b.estado) || "Pendiente de la primera revisión")}</span>
        <span class="pequeno tenue" data-revisado>${textoProxima(b)}</span>
      </div>
      <div class="acciones">
        <a class="boton pequeno primario" href="#/busqueda/${b.id}">${icono("grafica")}En directo</a>
        <a class="boton pequeno" href="#/editar/${b.id}">${icono("editar")}Editar</a>
        <a class="boton pequeno fantasma" href="#/duplicar/${b.id}">${icono("duplicar")}Duplicar</a>
      </div>
    </article>`;
}

export async function vistaPanel(app) {
  const recargar = () => {
    limpiarPantalla();
    return vistaPanel(app);
  };
  let tiempoRealActivo = false;
  const [busquedas, historial, avisos, perfil, datos] = await Promise.all([
    api.busquedas(), api.historialTodas(), api.avisosRecientes(), api.perfil(), aeropuertos(),
  ]);
  // Fechas y horas de la mejor opción de cada búsqueda (si falla, el panel se ve igual sin ellas)
  const mejores = new Map((await api.ultimosMejores(busquedas.map((b) => b.id)).catch(() => [])).map((p) => [p.busqueda, p]));
  const activas = busquedas.filter((b) => b.activa);
  const conPrecio = activas.filter((b) => b.precio_actual != null);
  const mejor = conPrecio.sort((x, y) => x.precio_actual - y.precio_actual)[0];
  const semana = Date.now() - 7 * 86400000;
  const avisosSemana = avisos.filter((a) => new Date(a.enviado) > semana).length;
  const proxima = activas.map((b) => b.proxima_revision).filter(Boolean).sort()[0];
  const horaDia = new Date().getHours();
  const saludo = horaDia < 13 ? "Buenos días" : horaDia < 21 ? "Buenas tardes" : "Buenas noches";

  app.innerHTML = `
    <div>
      <div class="cabecera-pagina">
        <div>
          <h1>${saludo}${perfil.nombre ? `, ${esc(perfil.nombre)}` : ""} ✈️</h1>
          <p class="subtitulo">${activas.length ? `Vigilando ${activas.length} búsqueda${activas.length > 1 ? "s" : ""} sin parar.` : "Crea tu primera búsqueda y el robot se pondrá a vigilarla."}</p>
        </div>
        <a class="boton primario grande" href="#/nueva">${icono("mas")}Nueva búsqueda</a>
      </div>

      <div class="kpis escalonado">
        <div class="tarjeta kpi"><div class="kpi-icono ok">${icono("etiqueta")}</div>
          <div><div class="valor" id="kpi-mejor">—</div><div class="etiqueta">${mejor ? `mejor precio · ${esc(mejor.nombre)}` : "mejor precio actual"}</div></div></div>
        <div class="tarjeta kpi"><div class="kpi-icono">${icono("lupa")}</div>
          <div><div class="valor" id="kpi-activas">0</div><div class="etiqueta">búsquedas activas</div></div></div>
        <div class="tarjeta kpi"><div class="kpi-icono alerta">${icono("campana")}</div>
          <div><div class="valor" id="kpi-avisos">0</div><div class="etiqueta">avisos en 7 días</div></div></div>
        <div class="tarjeta kpi"><div class="kpi-icono">${icono("reloj")}</div>
          <div><div class="valor cuenta-atras" id="kpi-proxima">${proxima ? cuentaAtras(proxima) : "—"}</div><div class="etiqueta">para la próxima revisión</div></div></div>
      </div>

      ${busquedas.length
        ? `<div class="rejilla escalonado" style="margin-top:1.3rem" id="rejilla">${busquedas.map((b) => tarjetaBusqueda(b, datos, mejores.get(b.id))).join("")}</div>`
        : `<div class="tarjeta vacio" style="margin-top:1.3rem">
             <div class="ilustracion">${icono("avion")}</div>
             <h2>Aún no vigilas ningún vuelo</h2>
             <p>Elige aeropuertos, fechas, horarios, pasajeros y maletas. El robot revisará los precios sin parar
               y te avisará por Telegram en el mejor momento.</p>
             <a class="boton primario grande" href="#/nueva">${icono("mas")}Crear mi primera búsqueda</a>
           </div>`}

      ${avisos.length ? `
        <section class="tarjeta" style="margin-top:1.3rem">
          <div class="tarjeta-titulo"><h2>${icono("campana")}Últimos avisos</h2><span class="chip">${avisos.length}</span></div>
          <ul class="linea-tiempo">${avisos.map((a) => {
            const b = busquedas.find((x) => x.id === a.busqueda);
            return `<li class="${a.entregado ? "ok" : ""}">
              <div class="fila entre"><b>${esc(TIPO_AVISO[a.tipo] || a.tipo)} · ${eur(a.precio_total)}</b>
                <span class="cuando">${fechaHora(a.enviado)}</span></div>
              <div class="pequeno suave">${b ? `<a href="#/busqueda/${b.id}">${esc(b.nombre)}</a> · ` : ""}${esc(a.motivo)}</div>
              <div class="pequeno ${a.entregado ? "" : "tenue"}">${a.entregado ? "✓ Enviado a Telegram" : "No enviado: vincula Telegram en tu perfil"}</div>
            </li>`;
          }).join("")}</ul>
        </section>` : ""}
    </div>`;

  contarHasta($("#kpi-mejor"), mejor ? Number(mejor.precio_actual) : null);
  contarHasta($("#kpi-activas"), activas.length, { formato: (n) => String(Math.round(n)), duracion: 600 });
  contarHasta($("#kpi-avisos"), avisosSemana, { formato: (n) => String(Math.round(n)), duracion: 600 });
  if (proxima) cadaSegundos(1, () => { $("#kpi-proxima").textContent = cuentaAtras(proxima); });

  // Precios y minigráficas
  const graficas = new Map();
  for (const b of busquedas) {
    const tarjeta = app.querySelector(`[data-id="${b.id}"]`);
    if (b.precio_actual != null) contarHasta(tarjeta.querySelector("[data-precio]"), Number(b.precio_actual));
    const puntos = historial.filter((h) => h.busqueda === b.id && (!b.historial_desde || h.revisado >= b.historial_desde));
    graficas.set(b.id, miniGrafica(tarjeta.querySelector("canvas"), puntos, {
      presupuesto: b.modo_precio === "presupuesto" ? b.presupuesto : null,
    }));
  }
  alSalir(() => graficas.forEach((g) => g?.destruir()));

  // Tiempo real: cada búsqueda revisada actualiza su tarjeta al momento
  alSalir(api.suscribir("busquedas", ({ new: b }) => {
    tiempoRealActivo = true;
    const tarjeta = b && app.querySelector(`[data-id="${b.id}"]`);
    if (!tarjeta) return;
    const precioEl = tarjeta.querySelector("[data-precio]");
    const antes = Number(String(precioEl.dataset.valor ?? "")) || null;
    const ahora = b.precio_actual != null ? Number(b.precio_actual) : null;
    if (ahora === null) precioEl.innerHTML = precioInicial(b);
    else contarHasta(precioEl, ahora, { desde: antes ?? 0 });
    precioEl.dataset.valor = ahora ?? "";
    tarjeta.querySelector("[data-etiqueta]").textContent = etiquetaPrecio(b);
    if (antes != null && ahora != null && antes !== ahora) destello(tarjeta, ahora - antes);
    tarjeta.querySelector("[data-delta]").innerHTML = b.info?.variacion != null ? deltaHtml(b.info.variacion) : "";
    const local = busquedas.find((x) => x.id === b.id);
    if (local) Object.assign(local, b);
    tarjeta.querySelector("[data-fechas]").innerHTML = fechasDe(b, mejores.get(b.id));
    if (esCualquiera(b)) {
      tarjeta.querySelector("[data-top]").innerHTML = topDestinosHtml(datos, b);
      tarjeta.querySelector(".ruta").outerHTML = rutaCualquieraHtml(datos, b);
    }
    tarjeta.querySelector("[data-estado]").textContent = estadoLegible(b.estado);
    tarjeta.querySelector("[data-revisado]").textContent = textoProxima(b);
  }));
  alSalir(api.suscribir("precios", ({ new: p }) => {
    tiempoRealActivo = true;
    if (!p || p.es_mejor === false) return;
    // Revisión nueva: sus fechas y horas pasan a ser las del precio
    if (p.fecha_ida && (p.detalle || p.ida)) {
      mejores.set(p.busqueda, p);
      const b = busquedas.find((x) => x.id === p.busqueda);
      const caja = app.querySelector(`[data-id="${p.busqueda}"] [data-fechas]`);
      if (b && caja) caja.innerHTML = fechasDe({ ...b, precio_actual: p.precio_total }, p);
    }
    if (graficas.get(p.busqueda)) return graficas.get(p.busqueda).añadir(p);
    const b = busquedas.find((x) => x.id === p.busqueda);
    const canvas = app.querySelector(`[data-id="${p.busqueda}"] canvas`);
    if (!b || !canvas) return;
    historial.push(p);
    const puntos = historial.filter((h) => h.busqueda === b.id && (!b.historial_desde || h.revisado >= b.historial_desde));
    graficas.set(b.id, miniGrafica(canvas, puntos, { presupuesto: b.modo_precio === "presupuesto" ? b.presupuesto : null }));
  }));
  for (const b of busquedas) app.querySelector(`[data-id="${b.id}"] [data-precio]`).dataset.valor = b.precio_actual ?? "";
  // Respaldo por si el tiempo real no está activado en Supabase: recargar cada 2 minutos
  cadaSegundos(120, () => !tiempoRealActivo && recargar());

  app.querySelectorAll("[data-pausar]").forEach((boton) =>
    boton.addEventListener("click", async () => {
      const b = busquedas.find((x) => x.id === boton.dataset.pausar);
      try {
        await api.actualizarBusqueda(b.id, { activa: !b.activa });
        aviso(b.activa ? "Búsqueda en pausa" : "Búsqueda reanudada: el robot la revisa en un minuto");
        recargar();
      } catch (e) {
        aviso(e.message, "error");
      }
    }),
  );
}
