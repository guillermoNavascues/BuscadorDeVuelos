import { api } from "../api.js";
import { graficaActividad } from "../graficas.js";
import { icono } from "../iconos.js";
import { $, alSalir, aviso, cadaSegundos, contarHasta, esc, fechaHora, hace } from "../util.js";

const NOMBRE_FUENTE = { google_flights: "Google Flights", ryanair: "Ryanair", skyscanner: "Skyscanner" };
const HORA = 3600000;

function ritmo(minutos) {
  if (minutos < 60) return `cada ${minutos} min`;
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return `cada ${h} h${m ? ` ${m} min` : ""}`;
}

function duracion(segundos) {
  if (segundos == null) return "en curso";
  if (segundos < 60) return `${segundos} s`;
  const m = Math.floor(segundos / 60);
  return m < 60 ? `${m} min ${segundos % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

function estadoRobot(latido) {
  const minutos = latido?.en ? (Date.now() - new Date(latido.en)) / 60000 : null;
  if (minutos !== null && minutos < 5) {
    return {
      clase: "activo", punto: "", etiqueta: "En directo", titulo: "Buscando vuelos sin parar",
      texto: "Cada minuto mira Telegram y revisa las búsquedas a las que les toca: cada una, cada 20 min. Si una web lo bloquea, descansa solo y te avisa por Telegram.",
    };
  }
  if (minutos !== null && minutos < 180) {
    return {
      clase: "aviso", punto: "aviso", etiqueta: "Cambiando de sesión", titulo: "Enlazando la siguiente sesión",
      texto: "Cada sesión de GitHub dura unas 6 horas y lanza la siguiente al terminar. Si en unos minutos no vuelve, arráncalo a mano (abajo te explico cómo).",
    };
  }
  return {
    clase: "apagado", punto: "apagado", etiqueta: "Parado", titulo: latido ? "El robot está parado" : "El robot aún no ha arrancado",
    texto: "Arráncalo en GitHub → Actions → «Robot de vuelos» → Run workflow. A partir de ahí se encadena solo, día y noche.",
  };
}

function heroe(latido) {
  const e = estadoRobot(latido);
  const fin = latido?.hasta && new Date(latido.hasta) > new Date() && e.clase === "activo"
    ? `<span>Esta sesión termina <b>${hace(latido.hasta)}</b> y enlaza la siguiente sola</span>` : "";
  return `
    <div class="robot-avatar ${e.clase}">${icono("robot")}</div>
    <div>
      <span class="vivo" style="${e.clase === "activo" ? "" : `color:var(--${e.clase === "aviso" ? "alerta" : "tenue"})`}">
        <span class="punto-vivo ${e.punto}"></span>${e.etiqueta}</span>
      <h2>${e.titulo}</h2>
      <p class="suave" style="margin-bottom:.6rem">${e.texto}</p>
      <div class="datos">
        <span>Última señal: <b>${latido?.en ? hace(latido.en) : "ninguna"}</b></span>
        ${fin}
        <span>Repositorio público: <b>minutos de GitHub ilimitados</b></span>
      </div>
    </div>`;
}

function tarjetaFuente(f) {
  const bloqueada = f.bloqueada_hasta && new Date(f.bloqueada_hasta) > new Date();
  const estado = !f.activa ? `<span class="chip">${icono("pausa")}Desactivada</span>`
    : bloqueada ? `<span class="chip mal">${icono("aviso")}En pausa hasta ${fechaHora(f.bloqueada_hasta)}</span>`
    : `<span class="chip ok"><span class="punto-vivo" style="width:7px;height:7px"></span>Funcionando</span>`;
  return `
    <article class="tarjeta fuente ${f.activa ? "" : "inactiva"}" data-tarjeta-fuente="${esc(f.fuente)}">
      <div class="fila entre"><h3 style="margin:0;display:flex;gap:.5rem;align-items:center">${icono("globo")}${esc(f.nombre || NOMBRE_FUENTE[f.fuente] || f.fuente)}</h3>${estado}</div>
      <p class="pequeno suave" style="margin:0">${esc(f.descripcion || "")}</p>
      <div class="metricas">
        <div>Ritmo<b>${ritmo(f.intervalo_min)}</b></div>
        <div>Entre peticiones<b>${f.pausa_min_s}-${f.pausa_max_s} s</b></div>
        <div>Última consulta<b>${hace(f.ultima_ronda)}</b></div>
        <div>Última correcta<b>${hace(f.ultima_ok)}</b></div>
      </div>
      ${f.bloqueos_seguidos ? `<div class="pequeno" style="color:var(--alerta)">Bloqueos seguidos: ${f.bloqueos_seguidos} (cada vez descansa el doble)</div>` : ""}
      ${f.ultimo_error ? `<div class="nota mal pequeno">${icono("aviso")}<span>${esc(f.ultimo_error)}</span></div>` : ""}
      <label class="interruptor" style="margin-top:.2rem"><input type="checkbox" data-fuente="${esc(f.fuente)}" ${f.activa ? "checked" : ""}><span class="pista"></span>Usar esta web</label>
    </article>`;
}

function filaRonda(e) {
  const r = e.resumen || {};
  const incidencias = [...(r.errores || []), ...Object.entries(r.fuentes || {}).flatMap(([n, f]) => (f?.bloqueo ? [`${NOMBRE_FUENTE[n] || n}: ${f.bloqueo}`] : []))];
  const webs = (r.fuentes_en_ronda || []).map((f) => `<span class="chip">${esc(NOMBRE_FUENTE[f] || f)}</span>`).join(" ");
  return `<tr>
    <td style="white-space:nowrap">${fechaHora(e.inicio)}${r.forzada ? ' <span class="chip primario">manual</span>' : ""}</td>
    <td class="num">${duracion(e.duracion_s)}</td>
    <td><div class="fila" style="gap:.3rem">${webs || '<span class="tenue">—</span>'}</div></td>
    <td class="num">${r.revisadas ?? 0}</td>
    <td class="num">${r.avisos ? `<span class="chip ok">${icono("campana")}${r.avisos}</span>` : "0"}</td>
    <td class="pequeno">${incidencias.length ? `<span style="color:var(--mal)">${esc(incidencias.join(" · "))}</span>` : '<span class="tenue">—</span>'}</td>
  </tr>`;
}

/** Revisiones y avisos de cada una de las últimas 24 horas. */
function porHoras(ejecuciones) {
  const ahora = new Date();
  ahora.setMinutes(0, 0, 0);
  const inicio = ahora.getTime() - 23 * HORA;
  const etiquetas = [];
  const revisiones = Array(24).fill(0);
  const avisos = Array(24).fill(0);
  for (let i = 0; i < 24; i++) etiquetas.push(`${String(new Date(inicio + i * HORA).getHours()).padStart(2, "0")}h`);
  for (const e of ejecuciones) {
    const i = Math.floor((new Date(e.inicio).getTime() - inicio) / HORA);
    if (i < 0 || i > 23) continue;
    revisiones[i] += e.resumen?.revisadas || 0;
    avisos[i] += e.resumen?.avisos || 0;
  }
  return { etiquetas, revisiones, avisos };
}

export async function vistaEstado(app) {
  let [fuentes, rondas, dia, latido] = await Promise.all([api.fuentes(), api.ejecuciones(30), api.ejecucionesDesde(1), api.latido()]);

  app.innerHTML = `
    <div>
      <div class="cabecera-pagina">
        <div>
          <h1>Estado del robot</h1>
          <p class="subtitulo">Qué está haciendo ahora mismo, qué webs consulta y cómo han ido las últimas vueltas.</p>
        </div>
      </div>

      <div class="escalonado">
        <section class="tarjeta heroe robot-heroe resaltada" id="heroe">${heroe(latido)}</section>

        <div class="kpis" style="margin-top:1.1rem">
          <div class="tarjeta kpi"><div class="kpi-icono">${icono("rayo")}</div>
            <div><div class="valor" id="k-rondas">0</div><div class="etiqueta">vueltas con trabajo (24 h)</div></div></div>
          <div class="tarjeta kpi"><div class="kpi-icono">${icono("lupa")}</div>
            <div><div class="valor" id="k-revisadas">0</div><div class="etiqueta">búsquedas revisadas (24 h)</div></div></div>
          <div class="tarjeta kpi"><div class="kpi-icono ok">${icono("campana")}</div>
            <div><div class="valor" id="k-avisos">0</div><div class="etiqueta">avisos enviados (24 h)</div></div></div>
          <div class="tarjeta kpi"><div class="kpi-icono alerta">${icono("reloj")}</div>
            <div><div class="valor" id="k-tiempo">0</div><div class="etiqueta">minutos consultando webs (24 h)</div></div></div>
        </div>

        <section class="tarjeta">
          <div class="tarjeta-titulo"><h2>${icono("grafica")}Actividad de las últimas 24 horas</h2>
            <span class="vivo"><span class="punto-vivo"></span>se actualiza sola</span></div>
          <div class="grafica-actividad"><canvas id="actividad" aria-label="Revisiones por hora"></canvas></div>
        </section>

        <div class="tarjeta-titulo" style="margin:1.6rem 0 .8rem"><h2>${icono("globo")}Webs que consulta</h2></div>
        <div class="rejilla" id="fuentes"></div>

        <section class="tarjeta" style="margin-top:1.1rem">
          <div class="tarjeta-titulo"><h2>${icono("servidor")}Últimas vueltas con trabajo</h2><span class="chip" id="num-rondas"></span></div>
          <div id="rondas"></div>
        </section>

        <section class="tarjeta">
          <div class="tarjeta-titulo"><h2>${icono("escudo")}Cómo busca</h2></div>
          <ul class="pasos">
            <li><span>Cada búsqueda se hace en una <b>sesión privada nueva</b>, sin cookies guardadas, desde una máquina de GitHub recién creada.</span></li>
            <li><span>Cada web tiene su ritmo y su pausa entre peticiones. Si alguna pide verificación anti-robots <b>no se intenta saltar</b>: descansa el doble cada vez.</span></li>
            <li><span>Las sesiones duran unas 6 horas y se encadenan solas. Si alguna vez se para, en GitHub → Actions → «Robot de vuelos» pulsa <b>Run workflow</b>.</span></li>
          </ul>
        </section>
      </div>
    </div>`;

  let grafica = null;
  alSalir(() => grafica?.destruir());

  const pintar = () => {
    const revisadas = dia.reduce((s, e) => s + (e.resumen?.revisadas || 0), 0);
    const avisos = dia.reduce((s, e) => s + (e.resumen?.avisos || 0), 0);
    const segundos = dia.reduce((s, e) => s + (e.duracion_s || 0), 0);
    const entero = { formato: (n) => String(Math.round(n)), duracion: 600 };
    contarHasta($("#k-rondas"), dia.length, entero);
    contarHasta($("#k-revisadas"), revisadas, entero);
    contarHasta($("#k-avisos"), avisos, entero);
    contarHasta($("#k-tiempo"), Math.round(segundos / 60), entero);

    const { etiquetas, revisiones, avisos: avisosHora } = porHoras(dia);
    if (grafica) grafica.actualizar(etiquetas, revisiones, avisosHora);
    else grafica = graficaActividad($("#actividad"), etiquetas, revisiones, avisosHora);

    $("#fuentes").innerHTML = fuentes.map(tarjetaFuente).join("");
    $("#num-rondas").textContent = rondas.length;
    $("#rondas").innerHTML = rondas.length
      ? `<div class="tabla-envoltura"><table>
          <thead><tr><th>Inicio</th><th>Duración</th><th>Webs</th><th>Revisadas</th><th>Avisos</th><th>Incidencias</th></tr></thead>
          <tbody>${rondas.map(filaRonda).join("")}</tbody></table></div>`
      : `<p class="suave" style="margin:0">Todavía no hay vueltas con trabajo. Arranca el robot en GitHub → Actions → «Robot de vuelos» → Run workflow.</p>`;
  };
  pintar();

  // Activar / desactivar webs
  $("#fuentes").addEventListener("change", async (ev) => {
    const caja = ev.target.closest("[data-fuente]");
    if (!caja) return;
    try {
      await api.actualizarFuente(caja.dataset.fuente, { activa: caja.checked });
      aviso(caja.checked ? "Web activada" : "Web desactivada");
      fuentes = await api.fuentes();
      pintar();
    } catch (e) {
      caja.checked = !caja.checked;
      aviso(e.message, "error");
    }
  });

  // Tiempo real: cada vuelta nueva del robot (o cambio en una web) refresca la página sin recargarla
  let pendiente = null;
  const refrescar = () => {
    clearTimeout(pendiente);
    pendiente = setTimeout(async () => {
      try {
        [fuentes, rondas, dia] = await Promise.all([api.fuentes(), api.ejecuciones(30), api.ejecucionesDesde(1)]);
        pintar();
      } catch (e) { /* se reintenta en la siguiente actualización */ }
    }, 1500);
  };
  alSalir(() => clearTimeout(pendiente));
  alSalir(api.suscribir("ejecuciones", refrescar));
  alSalir(api.suscribir("estado_fuentes", refrescar));
  cadaSegundos(60, refrescar); // respaldo por si el tiempo real no está activado
  cadaSegundos(15, async () => {
    latido = await api.latido().catch(() => latido);
    $("#heroe").innerHTML = heroe(latido);
  });
}
