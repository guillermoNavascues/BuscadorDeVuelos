import { api } from "../api.js";
import { aFecha, aIso, selectorFechas } from "../calendario.js";
import { icono } from "../iconos.js";
import {
  $, aeropuertos, aeropuertosCercanos, aviso, bandera, buscarAeropuertos, conCarga, esc, PAISES_RIESGO, esCualquiera, listaPaises, nombrePais, eur, fecha, nombreAeropuerto,
} from "../util.js";

const MAX_EXTRA = 3; // aeropuertos de salida alternativos
const MAX_FECHAS = 5; // fechas alternativas del mismo viaje
const MAX_VUELOS = 5; // vuelos de un viaje con varios destinos

const hoyMas = (dias) => {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const hh = (h) => `${String(h).padStart(2, "0")}:00`;
const sumarIso = (iso, dias) => {
  const f = aFecha(iso) || new Date();
  f.setDate(f.getDate() + dias);
  return aIso(f);
};
const nochesTxt = (n) => (n === 0 ? "mismo día" : `${n} noche${n === 1 ? "" : "s"}`);

const PREDETERMINADA = {
  nombre: "", modo: "fechas", ida_vuelta: true, origen: "", destino: "",
  fecha_ida: hoyMas(45), fecha_vuelta: hoyMas(49), flex_dias: 0,
  chollo_desde: hoyMas(7), chollo_hasta: hoyMas(150), noches_min: 2, noches_max: 5,
  ida_salida_min: 0, ida_salida_max: 24, ida_llegada_min: 0, ida_llegada_max: 24,
  vuelta_salida_min: 0, vuelta_salida_max: 24, vuelta_llegada_min: 0, vuelta_llegada_max: 24,
  adultos: 1, ninos: 0, bebes: 0, maletas_cabina: 0, maletas_20kg: 0, aplicar_descuentos: true,
  escalas_max: 1, escala_max_horas: 6, modo_precio: "mas_barato", presupuesto: null,
};

// ---------------------------------------------------------------------------
// Componentes
// ---------------------------------------------------------------------------
function montarAeropuerto(contenedor, datos, codigoInicial, alCambiar) {
  contenedor.innerHTML = `
    <div class="autocompletar">
      ${icono("ubicacion", "icono-campo")}
      <input type="text" autocomplete="off" spellcheck="false" placeholder="Ciudad, aeropuerto o código">
      <ul class="sugerencias oculto" role="listbox"></ul>
    </div>
    <div class="elegido"></div>`;
  const input = contenedor.querySelector("input");
  const lista = contenedor.querySelector(".sugerencias");
  const elegido = contenedor.querySelector(".elegido");
  let codigo = codigoInicial || "";
  let resultados = [];
  let activo = -1;

  const mostrarElegido = () => {
    const a = datos.mapa.get(codigo);
    elegido.innerHTML = a ? `${icono("check")}<span class="bandera" style="font-size:1rem">${bandera(a.p)}</span> ${esc(a.c)} · ${esc(a.es || a.n)}` : "";
    if (a) input.value = nombreAeropuerto(datos, codigo);
  };
  const cerrar = () => {
    lista.classList.add("oculto");
    activo = -1;
  };
  const elegir = (a) => {
    codigo = a.c;
    mostrarElegido();
    cerrar();
    alCambiar(codigo);
  };
  const pintar = () => {
    lista.innerHTML = resultados.map((a, i) => `
      <li data-i="${i}" class="${i === activo ? "activa" : ""}" role="option">
        <span class="bandera">${bandera(a.p)}</span><span class="codigo">${a.c}</span>
        <span><span class="nombre">${esc(a.es || a.n)}</span><span class="lugar">${a.es ? esc(a.pn) : `${esc(a.m)}, ${esc(a.pn)}`}</span></span>
      </li>`).join("") || '<li class="suave">Sin resultados</li>';
    lista.classList.remove("oculto");
  };
  input.addEventListener("input", () => {
    codigo = "";
    elegido.innerHTML = "";
    alCambiar("");
    resultados = buscarAeropuertos(datos, input.value);
    activo = resultados.length ? 0 : -1;
    if (input.value.trim().length >= 2) pintar();
    else cerrar();
  });
  input.addEventListener("keydown", (ev) => {
    if (lista.classList.contains("oculto")) return;
    if (ev.key === "ArrowDown") activo = Math.min(activo + 1, resultados.length - 1);
    else if (ev.key === "ArrowUp") activo = Math.max(activo - 1, 0);
    else if (ev.key === "Enter" && resultados[activo]) {
      ev.preventDefault();
      return elegir(resultados[activo]);
    } else if (ev.key === "Escape") return cerrar();
    else return;
    ev.preventDefault();
    pintar();
  });
  lista.addEventListener("mousedown", (ev) => {
    const li = ev.target.closest("li[data-i]");
    if (li) elegir(resultados[Number(li.dataset.i)]);
  });
  input.addEventListener("blur", () => setTimeout(cerrar, 150));
  mostrarElegido();
  return { poner: (c) => { codigo = c; input.value = ""; mostrarElegido(); } };
}

/** Fila de una salida alternativa: su aeropuerto (editable) y la llegada, que es siempre la misma. */
function filaSalida(i) {
  return `
    <div class="fila-salida" data-fila="${i}">
      <div class="campo salida-alt"><label>Otra salida</label><div class="campo-salida"></div></div>
      <span class="flecha-salida">${icono("flecha")}</span>
      <div class="campo llegada-alt"><label>Llegada</label><div class="llegada-fija" data-llegada></div></div>
      <button type="button" class="icono pequeno fantasma quitar-fila" data-quitar-fila="${i}" title="Quitar esta salida">${icono("cruz")}</button>
    </div>`;
}

function rangoDoble(nombre, titulo, min, max) {
  return `
    <div class="franja" data-rango="${nombre}">
      <div class="franja-cabecera"><span class="titulo-franja" data-normal="${titulo}" data-varios="${titulo.replace("Ida", "Cada vuelo")}">${titulo}</span><span class="valor-franja"></span></div>
      <div class="rango-doble">
        <div class="riel"></div><div class="relleno"></div>
        <input type="range" min="0" max="24" step="1" value="${min}" name="${nombre}_min" aria-label="${titulo}: desde">
        <input type="range" min="0" max="24" step="1" value="${max}" name="${nombre}_max" aria-label="${titulo}: hasta">
      </div>
      <div class="marcas-horas"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>
    </div>`;
}

function activarRango(el) {
  const [a, b] = el.querySelectorAll("input");
  const relleno = el.querySelector(".relleno");
  const valor = el.querySelector(".valor-franja");
  const pintar = (movido) => {
    let min = Number(a.value);
    let max = Number(b.value);
    if (min >= max) {
      // Los dos tiradores no pueden cruzarse: se separan una hora
      if (movido === a) { min = Math.min(min, 23); a.value = min; max = min + 1; b.value = max; } else { max = Math.max(max, 1); b.value = max; min = max - 1; a.value = min; }
    }
    relleno.style.left = `${(min / 24) * 100}%`;
    relleno.style.right = `${100 - (max / 24) * 100}%`;
    valor.textContent = min === 0 && max === 24 ? "Cualquier hora" : `${hh(min)} – ${max === 24 ? "24:00" : hh(max)}`;
  };
  a.addEventListener("input", () => pintar(a));
  b.addEventListener("input", () => pintar(b));
  pintar();
}

function contador(id, titulo, subtitulo, valor, min, max) {
  return `
    <div class="contador">
      <div class="texto"><b>${titulo}</b><small>${subtitulo}</small></div>
      <div class="control">
        <button type="button" data-restar="${id}" aria-label="Quitar">−</button>
        <output id="${id}" data-min="${min}" data-max="${max}">${valor}</output>
        <button type="button" data-sumar="${id}" aria-label="Añadir">+</button>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Pantalla
// ---------------------------------------------------------------------------
export async function vistaFormulario(app, id, duplicar = false) {
  const [datos, perfil] = await Promise.all([aeropuertos(), api.perfil()]);
  let b = { ...PREDETERMINADA };
  if (id) {
    const existente = await api.busqueda(id);
    if (!existente) throw new Error("No existe esa búsqueda.");
    b = { ...b, ...existente };
    if (duplicar) b.nombre = `${b.nombre} (copia)`;
  }
  // "Vigilar este destino" (desde una búsqueda a cualquier destino): la misma búsqueda, con ese destino
  let elegido = null;
  try {
    elegido = JSON.parse(sessionStorage.getItem("vigilarDestino") || "null");
    sessionStorage.removeItem("vigilarDestino");
  } catch {}
  if (duplicar && elegido?.desde === id && elegido.destino) {
    b = { ...b, destino: elegido.destino, cualquier_destino: false, paises_excluidos: [], nombre: "" };
  }
  const editando = id && !duplicar;
  const tipoInicial = (b.tramos_viaje || []).length >= 2 ? "varios" : b.ida_vuelta ? "ida_vuelta" : "solo_ida";
  const tieneDescuento = (perfil.familia_numerosa || "ninguna") !== "ninguna" || (perfil.residente || "ninguno") !== "ninguno";
  const opcionNumero = (desde, hasta, sel) =>
    Array.from({ length: hasta - desde + 1 }, (_, i) => desde + i).map((n) => `<option value="${n}" ${Number(sel) === n ? "selected" : ""}>${n}</option>`).join("");

  app.innerHTML = `
    <div>
      <div class="cabecera-pagina">
        <div>
          <h1>${editando ? "Ajusta tu búsqueda" : "¿Adónde quieres volar?"}</h1>
          <p class="subtitulo">El robot la revisará sin parar y te avisará por Telegram en el mejor momento.</p>
        </div>
      </div>
      <form id="form-busqueda" class="rejilla-2" novalidate>
        <div class="escalonado">
          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">1</span>Qué vigilar</h2></div>
            <div class="opciones-tarjeta" style="margin-bottom:1rem">
              <label class="opcion-tarjeta"><input type="radio" name="modo" value="fechas" ${b.modo === "fechas" ? "checked" : ""}>
                <span class="icono-opcion">${icono("calendario")}</span><span><b>Fechas concretas</b><small>Te aviso del mejor momento para comprar esas fechas.</small></span></label>
              <label class="opcion-tarjeta"><input type="radio" name="modo" value="chollo" ${b.modo === "chollo" ? "checked" : ""}>
                <span class="icono-opcion">${icono("llama")}</span><span><b>Chollo</b><small>Cualquier fecha de un periodo, si aparece un precio muy por debajo de lo normal.</small></span></label>
            </div>
            <div class="segmentado" role="radiogroup" aria-label="Tipo de viaje">
              <label><input type="radio" name="tipo_viaje" value="ida_vuelta" ${tipoInicial === "ida_vuelta" ? "checked" : ""}>${icono("intercambiar")}Ida y vuelta</label>
              <label><input type="radio" name="tipo_viaje" value="solo_ida" ${tipoInicial === "solo_ida" ? "checked" : ""}>${icono("flecha")}Solo ida</label>
              <label id="opcion-varios"><input type="radio" name="tipo_viaje" value="varios" ${tipoInicial === "varios" ? "checked" : ""}>${icono("ubicacion")}Varios destinos</label>
            </div>
            <p class="ayuda" id="ayuda-tipo"></p>
          </section>

          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">2</span><span id="titulo-ruta">Aeropuertos</span></h2></div>
            <div id="bloque-ruta">
            <div class="aeropuertos">
              <div class="campo"><label>Salida</label><div id="origen"></div></div>
              <button type="button" class="icono intercambiar" id="intercambiar" title="Intercambiar origen y destino">${icono("intercambiar")}</button>
              <div class="campo"><label>Llegada</label><div id="destino"></div>
                <div class="destino-cualquiera oculto" id="destino-cualquiera">${icono("globo")}<span><b>Cualquier destino</b>
                  <small>Te busco los 5 más baratos</small></span></div>
                <button type="button" class="chip conmutador-destino" id="conmutar-cualquiera" aria-pressed="false">${icono("globo")}<span data-etiqueta>Cualquier destino</span></button></div>
            </div>
            <div id="salidas-extra"></div>
            <button type="button" class="fantasma pequeno" id="anadir-salida" style="margin-top:.5rem">${icono("mas")}Añadir otro aeropuerto de salida</button>
            <div class="cercanos" id="cercanos"></div>
            <div class="nota" id="nota-vuelta">${icono("info")}<span></span></div>
            <p class="ayuda">¿Te vale salir de varios sitios (p. ej. Jerez o Sevilla)? Añade hasta ${MAX_EXTRA} aeropuertos de salida más:
              el robot busca desde todos a la vez hacia tu llegada. Solo se aceptan vuelos de los aeropuertos que elijas
              (ojo: París tiene CDG, Orly y Beauvais, a 85 km); las escalas intermedias dan igual.</p>
            <div id="bloque-cualquier" class="oculto">
              <label for="anadir-pais" style="margin-top:.6rem">Países que no quieres</label>
              <div class="paises-excluidos" id="paises-excluidos"></div>
              <select id="anadir-pais" style="max-width:320px"></select>
              <p class="ayuda">Por defecto, los países con riesgo para viajar (guerra o conflicto) según las recomendaciones de viaje
                de Exteriores (las de hoy, en exteriores.gob.es); quita o añade los que quieras. El robot mira todos los destinos de
                Ryanair desde tus aeropuertos de salida, comprueba los 6 más baratos con Google Flights y tus filtros (escalas,
                horarios, maletas y descuentos) y te enseña los 5 mejores. Si añades otras fechas, las mira todas y de cada
                destino te enseña la fecha más barata. Se revisa cada 2 horas.</p>
            </div>
            </div>
            <div id="bloque-varios" class="oculto">
              <ol class="vuelos-viaje" id="vuelos-viaje"></ol>
              <button type="button" class="fantasma pequeno" id="anadir-vuelo" style="margin-top:.6rem">${icono("mas")}Añadir otro vuelo</button>
              <p class="ayuda">Cada vuelo es un billete de solo ida: el robot busca el más barato de cada uno (con tus horarios,
                escalas y aerolíneas), comprueba que encajan uno detrás de otro y te avisa con el total. Hasta ${MAX_VUELOS} vuelos.</p>
            </div>
          </section>

          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">3</span>Fechas</h2></div>
            <div id="bloque-fechas">
              <div class="fechas-principal">
              <div class="campo"><label>Fechas</label><div id="fechas-principales"></div>
                <input type="hidden" id="fecha_ida" value="${b.fecha_ida || ""}"><input type="hidden" id="fecha_vuelta" value="${b.fecha_vuelta || ""}"></div>
              <div class="campo"><label for="flex_dias">Margen</label>
                <select id="flex_dias">${[0, 1, 2, 3].map((n) => `<option value="${n}" ${b.flex_dias === n ? "selected" : ""}>${n ? `± ${n} día${n > 1 ? "s" : ""}` : "Fechas exactas"}</option>`).join("")}</select>
                <div class="ayuda">Mueve ida y vuelta juntas para encontrar el día más barato.</div></div>
              </div>
              <div class="fechas-extra" id="fechas-extra"></div>
              <button type="button" class="fantasma pequeno" id="anadir-fechas" style="margin-top:.7rem">${icono("mas")}Añadir otras fechas</button>
              <p class="ayuda" id="ayuda-extra">¿Te valen varias fechas para el mismo viaje? Añade hasta ${MAX_FECHAS} más: el robot las vigila todas
                en esta búsqueda y te avisa de la más barata (cada fecha de más alarga un poco cada revisión).</p>
            </div>
            <div id="bloque-chollo">
              <div class="fechas-principal">
              <div class="campo"><label>Periodo</label><div id="fechas-chollo"></div>
                <input type="hidden" id="chollo_desde" value="${b.chollo_desde || ""}"><input type="hidden" id="chollo_hasta" value="${b.chollo_hasta || ""}">
                <div class="ayuda">Google busca hasta unos 10 meses vista.</div></div>
              <div class="campo con-vuelta"><label>Noches de estancia</label>
                <div class="fila" style="flex-wrap:nowrap"><select id="noches_min">${opcionNumero(1, 30, b.noches_min)}</select><span class="suave">a</span>
                <select id="noches_max">${opcionNumero(1, 30, b.noches_max)}</select></div></div>
              </div>
            </div>
            <div class="nota oculto" id="nota-varios-fechas">${icono("info")}<span>Cada vuelo lleva su propia fecha: elígelas arriba, en «Vuelos del viaje».</span></div>
          </section>

          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">4</span>Horarios</h2><span class="pequeno tenue">hora local de cada aeropuerto</span></div>
            ${rangoDoble("ida_salida", "Ida · salida", b.ida_salida_min, b.ida_salida_max)}
            ${rangoDoble("ida_llegada", "Ida · llegada", b.ida_llegada_min, b.ida_llegada_max)}
            <div class="con-vuelta">
              ${rangoDoble("vuelta_salida", "Vuelta · salida", b.vuelta_salida_min, b.vuelta_salida_max)}
              ${rangoDoble("vuelta_llegada", "Vuelta · llegada", b.vuelta_llegada_min, b.vuelta_llegada_max)}
            </div>
            <p class="ayuda">Si no puedes salir antes de las 9 ni llegar después de las 22, ajusta los tiradores. Una llegada pasada la medianoche cuenta como más tarde de las 24:00.</p>
          </section>

          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">5</span>Pasajeros y maletas</h2><span class="pequeno tenue">máximo 9 personas</span></div>
            <div class="rejilla-contadores">
              ${contador("adultos", "Adultos", "12 años o más", b.adultos, 1, 9)}
              ${contador("ninos", "Niños", "de 2 a 11 años", b.ninos, 0, 8)}
              ${contador("bebes", "Bebés", "menos de 2, en brazos", b.bebes, 0, 8)}
            </div>
            <div class="rejilla-contadores" style="margin-top:.7rem">
              ${contador("maletas_cabina", "Maleta de cabina", "10 kg · ¿cuántos la llevan?", b.maletas_cabina, 0, 9)}
              ${contador("maletas_20kg", "Maleta facturada", "20 kg · ¿cuántos facturan?", b.maletas_20kg, 0, 9)}
            </div>
            <p class="ayuda">Las tarifas básicas de las low cost solo incluyen un bolso bajo el asiento. El robot suma cada maleta en cada vuelo; si no sabe el precio exacto usa el máximo de esa aerolínea, así el total nunca sale por debajo del real.</p>
            <label class="interruptor ${tieneDescuento ? "" : "oculto"}" style="margin-top:.6rem"><input type="checkbox" id="aplicar_descuentos" ${b.aplicar_descuentos !== false ? "checked" : ""}><span class="pista"></span>
              Aplicar mis descuentos (familia numerosa / residente)</label>
          </section>

          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">6</span>Escalas</h2></div>
            <div class="segmentado" style="margin-bottom:1rem">
              <label><input type="radio" name="escalas_max" value="0" ${b.escalas_max === 0 ? "checked" : ""}>Solo directos</label>
              <label><input type="radio" name="escalas_max" value="1" ${b.escalas_max === 1 ? "checked" : ""}>Máx. 1 escala</label>
              <label><input type="radio" name="escalas_max" value="2" ${b.escalas_max === 2 ? "checked" : ""}>Máx. 2 escalas</label>
            </div>
            <div class="franja" id="bloque-espera">
              <div class="franja-cabecera"><span>Espera máxima en cada escala</span><span class="valor-franja" id="valor-espera"></span></div>
              <input type="range" id="escala_max_horas" min="1" max="24" step="1" value="${b.escala_max_horas}" style="padding:0;height:32px;accent-color:var(--primario)">
              <div class="ayuda">Las escalas con billetes separados (self-transfer) se descartan siempre.</div>
            </div>
          </section>

          <section class="tarjeta seccion-form">
            <div class="tarjeta-titulo"><h2><span class="numero">7</span>Precio</h2></div>
            <div class="opciones-tarjeta">
              <label class="opcion-tarjeta"><input type="radio" name="modo_precio" value="mas_barato" ${b.modo_precio === "mas_barato" ? "checked" : ""}>
                <span class="icono-opcion">${icono("baja")}</span><span><b>Lo más barato posible</b><small>El robot decide: mínimo de varias horas en la ventana más barata, chollos y un último aviso antes de las 3 semanas finales.</small></span></label>
              <label class="opcion-tarjeta"><input type="radio" name="modo_precio" value="presupuesto" ${b.modo_precio === "presupuesto" ? "checked" : ""}>
                <span class="icono-opcion">${icono("euro")}</span><span><b>Tengo un objetivo de precio</b><small>Te aviso cuando el total (billetes + maletas − descuentos) no lo supere, y antes si se queda cerca: hasta un 20 % más caro (con 30 € de objetivo, hasta 36 €).</small></span></label>
            </div>
            <div class="campo" id="bloque-presupuesto" style="max-width:300px;margin-top:1rem">
              <label for="presupuesto">Total máximo para todos</label>
              <input type="number" id="presupuesto" min="1" step="1" inputmode="decimal" value="${b.presupuesto ?? ""}" placeholder="p. ej. 200 €">
            </div>
          </section>
        </div>

        <aside class="resumen-lateral">
          <section class="tarjeta resaltada">
            <div class="tarjeta-titulo"><h2>${icono("chispas")}Resumen</h2></div>
            <ul id="resumen"></ul>
            <div class="campo"><label for="nombre">Nombre de la búsqueda</label>
              <input id="nombre" maxlength="80" value="${esc(b.nombre)}" placeholder="p. ej. Puente en París"></div>
            <div id="errores" class="error-form" role="alert"></div>
            <button class="primario grande bloque" type="submit">${icono(editando ? "check" : "rayo")}${editando ? "Guardar cambios" : "Empezar a vigilar"}</button>
            <a class="boton fantasma bloque" style="margin-top:.5rem" href="${editando ? `#/busqueda/${id}` : "#/"}">Cancelar</a>
          </section>
        </aside>
      </form>
    </div>`;

  const form = $("#form-busqueda");
  const valorRadio = (nombre) => form.querySelector(`input[name="${nombre}"]:checked`)?.value;
  const num = (idCampo) => Number($(`#${idCampo}`).value ?? $(`#${idCampo}`).textContent);
  let origen = b.origen;
  // Cualquier destino: el robot elige los más baratos (sin los países que no quieres)
  let cualquiera = esCualquiera(b);
  let destino = cualquiera ? "" : b.destino;
  let paisesExcluidos = cualquiera ? [...(b.paises_excluidos || [])] : [...PAISES_RIESGO];
  // Salidas alternativas: la llegada es siempre la misma. "" = fila recién añadida, todavía sin elegir
  let salidas = [...(b.origenes_extra || [])];
  const salidasValidas = () => [...new Set(salidas.filter((c) => c && c !== origen && c !== destino))];
  const todasSalidas = () => [origen, ...salidasValidas()].filter(Boolean);
  const nombresSalida = () => todasSalidas().map((c) => nombreAeropuerto(datos, c)).join(" o ");

  form.querySelectorAll("[data-rango]").forEach(activarRango);

  // ---- Tipo de viaje
  const tipoViaje = () => valorRadio("tipo_viaje");
  const esVarios = () => tipoViaje() === "varios" && valorRadio("modo") === "fechas";
  const esIdaVuelta = () => tipoViaje() === "ida_vuelta";
  const HOY = hoyMas(0);
  const MAXIMO = hoyMas(330); // Google busca hasta unos 11 meses vista

  // ---- Calendarios propios (los campos ocultos guardan las fechas como antes)
  const principal = selectorFechas($("#fechas-principales"), {
    inicio: b.fecha_ida, fin: b.fecha_vuelta, rango: tipoInicial === "ida_vuelta", etiquetas: ["Ida", "Vuelta"],
    duracion: nochesTxt, min: HOY, max: MAXIMO, nombre: "Fechas del viaje",
    alCambiar: (ida, vuelta) => {
      $("#fecha_ida").value = ida || "";
      $("#fecha_vuelta").value = vuelta || "";
      actualizar();
    },
  });
  selectorFechas($("#fechas-chollo"), {
    inicio: b.chollo_desde, fin: b.chollo_hasta, rango: true, etiquetas: ["Desde", "Hasta"],
    duracion: (n) => `${n + 1} días`, min: HOY, max: MAXIMO, nombre: "Periodo del chollo",
    alCambiar: (desde, hasta) => {
      $("#chollo_desde").value = desde || "";
      $("#chollo_hasta").value = hasta || "";
      actualizar();
    },
  });

  // ---- Fechas alternativas del mismo viaje
  let extras = (b.fechas_extra || []).map((p) => ({ ida: p.ida, vuelta: p.vuelta || null }));
  const pintarExtras = (enfocar = -1) => {
    const caja = $("#fechas-extra");
    caja.innerHTML = extras.map((_, i) => `
      <div class="fila-fechas" data-extra="${i}">
        <span class="num-fechas" aria-hidden="true">${i + 2}</span>
        <div class="campo" data-selector></div>
        <button type="button" class="icono pequeno fantasma" data-quitar-extra="${i}" title="Quitar estas fechas" aria-label="Quitar las fechas ${i + 2}">${icono("cruz")}</button>
      </div>`).join("");
    extras.forEach((p, i) => {
      selectorFechas(caja.querySelector(`[data-extra="${i}"] [data-selector]`), {
        inicio: p.ida, fin: p.vuelta, rango: esIdaVuelta(), etiquetas: ["Ida", "Vuelta"], duracion: nochesTxt,
        min: HOY, max: MAXIMO, nombre: `Fechas ${i + 2}`,
        alCambiar: (ida, vuelta) => {
          extras[i] = { ida, vuelta };
          actualizar();
        },
      });
    });
    if (enfocar >= 0) caja.querySelector(`[data-extra="${enfocar}"] .billete-parte`)?.focus();
    $("#anadir-fechas").classList.toggle("oculto", extras.length >= MAX_FECHAS);
  };
  const anadirFechas = () => {
    if (extras.length >= MAX_FECHAS) return;
    const base = extras.at(-1) || { ida: $("#fecha_ida").value || hoyMas(45), vuelta: $("#fecha_vuelta").value || null };
    extras.push({ ida: sumarIso(base.ida, 7), vuelta: esIdaVuelta() ? sumarIso(base.vuelta || base.ida, 7) : null });
    pintarExtras(extras.length - 1);
    actualizar();
  };

  // ---- Vuelos de un viaje con varios destinos
  let tramos = (b.tramos_viaje || []).length >= 2 ? b.tramos_viaje.map((t) => ({ ...t })) : null;
  const pintarTramos = (enfocar = -1) => {
    const lista = $("#vuelos-viaje");
    lista.innerHTML = tramos.map((_, i) => `
      <li class="vuelo-viaje" data-tramo="${i}">
        <div class="vuelo-viaje-cabecera"><span class="numero-vuelo">${icono("avion")}Vuelo ${i + 1}</span>
          ${tramos.length > 2 ? `<button type="button" class="icono pequeno fantasma" data-quitar-tramo="${i}" title="Quitar este vuelo" aria-label="Quitar el vuelo ${i + 1}">${icono("cruz")}</button>` : ""}</div>
        <div class="vuelo-viaje-campos">
          <div class="campo"><label>Sale de</label><div data-o></div></div>
          <div class="campo"><label>Llega a</label><div data-d></div></div>
          <div class="campo campo-fecha-vuelo"><label>Fecha</label><div data-f></div></div>
        </div>
      </li>`).join("");
    const salidasTramo = [];
    tramos.forEach((t, i) => {
      const fila = lista.querySelector(`[data-tramo="${i}"]`);
      salidasTramo[i] = montarAeropuerto(fila.querySelector("[data-o]"), datos, t.origen, (c) => {
        tramos[i].origen = c;
        actualizar();
      });
      montarAeropuerto(fila.querySelector("[data-d]"), datos, t.destino, (c) => {
        tramos[i].destino = c;
        // El vuelo siguiente sale, si no tiene salida, de donde llega este
        if (c && tramos[i + 1] && !tramos[i + 1].origen) {
          tramos[i + 1].origen = c;
          salidasTramo[i + 1]?.poner(c);
        }
        actualizar();
      });
      selectorFechas(fila.querySelector("[data-f]"), {
        inicio: t.fecha, rango: false, etiquetas: [`Vuelo ${i + 1}`], min: HOY, max: MAXIMO, nombre: `Fecha del vuelo ${i + 1}`,
        alCambiar: (f) => {
          tramos[i].fecha = f;
          actualizar();
        },
      });
      if (i === enfocar) fila.querySelector(`[data-${tramos[i].origen ? "d" : "o"}] input`)?.focus();
    });
    $("#anadir-vuelo").classList.toggle("oculto", tramos.length >= MAX_VUELOS);
  };
  const prepararTramos = () => {
    if (tramos) return;
    const ida = $("#fecha_ida").value || hoyMas(45);
    tramos = [
      { origen: origen || "", destino: destino || "", fecha: ida },
      { origen: destino || "", destino: "", fecha: sumarIso(ida, 3) },
    ];
    pintarTramos();
  };
  const anadirTramo = () => {
    if (tramos.length >= MAX_VUELOS) return;
    const ultimo = tramos.at(-1);
    tramos.push({ origen: ultimo.destino || "", destino: "", fecha: sumarIso(ultimo.fecha || HOY, 3) });
    pintarTramos(tramos.length - 1);
    actualizar();
  };
  const paradas = () => (tramos ? [tramos[0].origen, ...tramos.map((t) => t.destino)] : []);

  const pintarLlegadas = () => form.querySelectorAll("[data-llegada]").forEach((el) => {
    el.innerHTML = cualquiera ? `${icono("globo")}Cualquier destino`
      : destino ? `${icono("avion")}${esc(nombreAeropuerto(datos, destino))}` : '<span class="tenue">Elige la llegada arriba</span>';
  });
  const pintarPaises = () => {
    $("#paises-excluidos").innerHTML = paisesExcluidos.length
      ? paisesExcluidos.map((p) => `<button type="button" class="chip" data-quitar-pais="${esc(p)}" aria-label="Quitar ${esc(nombrePais(datos, p))}">${esc(nombrePais(datos, p))}${icono("cruz")}</button>`).join("")
      : '<span class="tenue pequeno">Ninguno: vale cualquier país.</span>';
    $("#anadir-pais").innerHTML = '<option value="">Añadir un país…</option>'
      + listaPaises(datos).filter(([c]) => !paisesExcluidos.includes(c)).map(([c, n]) => `<option value="${esc(c)}">${esc(n)}</option>`).join("");
  };
  const pintarCercanos = () => {
    const caben = Boolean(origen) && salidas.length < MAX_EXTRA;
    $("#anadir-salida").classList.toggle("oculto", !caben);
    const cerca = caben ? aeropuertosCercanos(datos, origen, { excluir: [origen, destino, ...salidas] }) : [];
    $("#cercanos").innerHTML = cerca.length
      ? `<span class="tenue">Cerca de ${esc(nombreAeropuerto(datos, origen, false))}:</span>${cerca.map(({ aeropuerto: a, km }) =>
        `<button type="button" class="chip" data-cercano="${a.c}">${icono("mas")}${esc(a.es || a.m || a.n)} (${a.c}) · ${km} km</button>`).join("")}`
      : "";
  };
  const pintarSalidas = (enfocar = -1) => {
    $("#salidas-extra").innerHTML = salidas.map((_, i) => filaSalida(i)).join("");
    salidas.forEach((codigo, i) => {
      const caja = $(`[data-fila="${i}"] .campo-salida`);
      montarAeropuerto(caja, datos, codigo, (c) => {
        salidas[i] = c;
        pintarCercanos();
        actualizar();
      });
      if (i === enfocar) caja.querySelector("input").focus();
    });
    pintarLlegadas();
    pintarCercanos();
  };
  const anadirSalida = (codigo = "") => {
    const vacia = salidas.indexOf("");
    if (codigo && vacia >= 0) salidas[vacia] = codigo; // una sugerencia rellena la fila vacía que haya
    else if (salidas.length < MAX_EXTRA) salidas.push(codigo);
    else return;
    pintarSalidas(codigo ? -1 : salidas.length - 1);
    actualizar();
  };
  form.addEventListener("click", (ev) => {
    const quitar = ev.target.closest("[data-quitar-fila]");
    const cercano = ev.target.closest("[data-cercano]");
    const quitarExtra = ev.target.closest("[data-quitar-extra]");
    const quitarTramo = ev.target.closest("[data-quitar-tramo]");
    if (quitarExtra) {
      extras.splice(Number(quitarExtra.dataset.quitarExtra), 1);
      pintarExtras();
      actualizar();
    } else if (quitarTramo) {
      tramos.splice(Number(quitarTramo.dataset.quitarTramo), 1);
      pintarTramos();
      actualizar();
    } else if (ev.target.closest("#anadir-fechas")) {
      anadirFechas();
    } else if (ev.target.closest("#anadir-vuelo")) {
      anadirTramo();
    } else if (quitar) {
      salidas.splice(Number(quitar.dataset.quitarFila), 1);
      pintarSalidas();
      actualizar();
    } else if (cercano) {
      anadirSalida(cercano.dataset.cercano);
    } else if (ev.target.closest("#anadir-salida")) {
      anadirSalida();
    }
  });

  const campoOrigen = montarAeropuerto($("#origen"), datos, origen, (c) => {
    origen = c;
    pintarCercanos();
    actualizar();
  });
  const campoDestino = montarAeropuerto($("#destino"), datos, destino, (c) => {
    destino = c;
    pintarLlegadas();
    pintarCercanos();
    actualizar();
  });
  $("#conmutar-cualquiera").addEventListener("click", () => {
    cualquiera = !cualquiera;
    pintarLlegadas();
    actualizar();
  });
  $("#paises-excluidos").addEventListener("click", (ev) => {
    const boton = ev.target.closest("[data-quitar-pais]");
    if (!boton) return;
    paisesExcluidos = paisesExcluidos.filter((p) => p !== boton.dataset.quitarPais);
    pintarPaises();
  });
  $("#anadir-pais").addEventListener("change", (ev) => {
    if (ev.target.value && !paisesExcluidos.includes(ev.target.value)) paisesExcluidos.push(ev.target.value);
    pintarPaises();
  });
  $("#intercambiar").addEventListener("click", () => {
    [origen, destino] = [destino, origen];
    campoOrigen.poner(origen);
    campoDestino.poner(destino);
    if (salidas.length) {
      salidas = []; // las salidas alternativas no tienen sentido al darle la vuelta al viaje
      aviso("Al intercambiar se han quitado las salidas alternativas");
    }
    pintarSalidas();
    actualizar();
  });

  // Contadores +/-
  form.addEventListener("click", (ev) => {
    const boton = ev.target.closest("[data-sumar], [data-restar]");
    if (!boton) return;
    const salida = $(`#${boton.dataset.sumar || boton.dataset.restar}`);
    const valor = Number(salida.textContent) + (boton.dataset.sumar ? 1 : -1);
    salida.textContent = Math.max(Number(salida.dataset.min), Math.min(Number(salida.dataset.max), valor));
    actualizar();
  });

  let tipoPintado = tipoInicial;
  function actualizar() {
    const modo = valorRadio("modo");
    // Un viaje con varios destinos va siempre con fechas concretas
    const opcionVarios = $("#opcion-varios input");
    opcionVarios.disabled = modo === "chollo" || cualquiera;
    if (opcionVarios.disabled && opcionVarios.checked) form.querySelector('input[name="tipo_viaje"][value="ida_vuelta"]').checked = true;
    const varios = esVarios();
    const idaVuelta = esIdaVuelta();
    if (tipoViaje() !== tipoPintado) {
      tipoPintado = tipoViaje();
      // Los vuelos, antes que el calendario: al cambiar de una fecha a dos, el calendario vuelve a llamar aquí
      if (varios) prepararTramos();
      principal.ponerRango(idaVuelta);
      pintarExtras();
    }
    $("#ayuda-tipo").textContent = cualquiera
      ? "Con «cualquier destino» el viaje es de ida y vuelta o solo ida."
      : modo === "chollo"
      ? "Varios destinos solo está con fechas concretas."
      : varios ? "Por ejemplo Sevilla → Cracovia → Zúrich → Sevilla: cada vuelo con su fecha." : "";
    $("#bloque-ruta").classList.toggle("oculto", varios);
    $("#destino").classList.toggle("oculto", cualquiera);
    $("#destino-cualquiera").classList.toggle("oculto", !cualquiera);
    $("#bloque-cualquier").classList.toggle("oculto", !cualquiera);
    $("#intercambiar").style.visibility = cualquiera ? "hidden" : ""; // (oculto, pero sin descolocar las columnas)
    $("#conmutar-cualquiera").setAttribute("aria-pressed", String(cualquiera));
    $("#conmutar-cualquiera [data-etiqueta]").textContent = cualquiera ? "Elegir un destino" : "Cualquier destino";
    $("#bloque-varios").classList.toggle("oculto", !varios);
    $("#titulo-ruta").textContent = varios ? "Vuelos del viaje" : "Aeropuertos";
    $("#nota-varios-fechas").classList.toggle("oculto", !varios);
    form.querySelectorAll(".titulo-franja").forEach((el) => (el.textContent = varios ? el.dataset.varios : el.dataset.normal));
    $("#bloque-fechas").classList.toggle("oculto", modo !== "fechas" || varios);
    $("#bloque-chollo").classList.toggle("oculto", modo !== "chollo");
    form.querySelectorAll(".con-vuelta").forEach((el) => el.classList.toggle("oculto", !idaVuelta));
    $("#bloque-presupuesto").classList.toggle("oculto", valorRadio("modo_precio") !== "presupuesto");
    $("#bloque-espera").classList.toggle("oculto", valorRadio("escalas_max") === "0");
    $("#valor-espera").textContent = `${$("#escala_max_horas").value} h`;
    const nota = $("#nota-vuelta");
    nota.classList.toggle("oculto", !(origen && (destino || cualquiera)));
    if (origen && cualquiera) {
      nota.querySelector("span").innerHTML = `Desde <b>${todasSalidas().map(esc).join(" o ")}</b> a los destinos más baratos`
        + (!idaVuelta ? ", solo ida." : todasSalidas().length > 1 ? "; la vuelta, al mismo aeropuerto del que salgas." : ` y vuelta a <b>${esc(origen)}</b>.`);
    } else if (origen && destino) {
      const salidasTxt = todasSalidas().map(esc).join(" o ");
      nota.querySelector("span").innerHTML = !idaVuelta
        ? `Solo ida <b>${salidasTxt} → ${esc(destino)}</b>.`
        : todasSalidas().length > 1
          ? `Ida <b>${salidasTxt} → ${esc(destino)}</b> · vuelta <b>${esc(destino)} → al mismo aeropuerto del que salgas</b>.
             Si volver al otro sale más barato, también te lo enseño, bien marcado.`
          : `Ida <b>${esc(origen)} → ${esc(destino)}</b> · vuelta <b>${esc(destino)} → ${esc(origen)}</b>: siempre a los mismos aeropuertos.`;
    }
    // Resumen en vivo
    const pax = num("adultos") + num("ninos") + num("bebes");
    const otras = extras.filter((p) => p.ida).length;
    const fechas = varios && tramos
      ? `${tramos.length} vuelos ·${fecha(tramos[0].fecha) || "—"} → ${fecha(tramos.at(-1).fecha) || "—"}`
      : modo === "fechas"
        ? `${fecha($("#fecha_ida").value) || "—"}${idaVuelta ? ` → ${fecha($("#fecha_vuelta").value) || "—"}` : ""}${num("flex_dias") ? ` (±${num("flex_dias")} d)` : ""}${otras ? ` · y ${otras} fecha${otras > 1 ? "s" : ""} más` : ""}`
        : `Del ${fecha($("#chollo_desde").value) || "—"} al ${fecha($("#chollo_hasta").value) || "—"}`;
    const recorrido = cualquiera && !varios
      ? `<b>${origen ? esc(nombresSalida()) : "Elige salida"}</b><br>cualquier destino (los 5 más baratos)${idaVuelta ? " · ida y vuelta" : " · solo ida"}`
      : varios
      ? `<b>${esc(paradas().map((c) => (c ? nombreAeropuerto(datos, c, false) : "…")).join(" → "))}</b><br>varios destinos`
      : `<b>${origen ? esc(nombresSalida()) : "Elige salida"}</b><br>${destino ? esc(nombreAeropuerto(datos, destino)) : "Elige llegada"}${idaVuelta ? " · ida y vuelta" : " · solo ida"}`;
    const precio = valorRadio("modo_precio") === "presupuesto"
      ? `Avisar si baja de ${$("#presupuesto").value ? eur($("#presupuesto").value) : "…"}`
      : "Avisar en el mejor momento";
    $("#resumen").innerHTML = `
      <li>${icono("avion")}<span>${recorrido}</span></li>
      <li>${icono("calendario")}<span>${esc(fechas)}</span></li>
      <li>${icono("personas")}<span>${pax} pasajero${pax !== 1 ? "s" : ""} · ${num("maletas_cabina")} cabina · ${num("maletas_20kg")} facturada${num("maletas_20kg") !== 1 ? "s" : ""}</span></li>
      <li>${icono("despegue")}<span>${valorRadio("escalas_max") === "0" ? "Solo directos" : `Hasta ${valorRadio("escalas_max")} escala${valorRadio("escalas_max") === "2" ? "s" : ""} de ${$("#escala_max_horas").value} h`}</span></li>
      <li>${icono("euro")}<span>${esc(precio)}</span></li>`;
  }
  form.addEventListener("input", actualizar);
  form.addEventListener("change", actualizar);
  pintarSalidas();
  pintarPaises();
  pintarExtras();
  if (tramos) pintarTramos();
  actualizar();

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const modo = valorRadio("modo");
    const varios = esVarios();
    const idaVuelta = !varios && esIdaVuelta();
    const d = {
      modo, ida_vuelta: idaVuelta, origen, destino,
      adultos: num("adultos"), ninos: num("ninos"), bebes: num("bebes"),
      maletas_cabina: num("maletas_cabina"), maletas_20kg: num("maletas_20kg"),
      escalas_max: Number(valorRadio("escalas_max")), escala_max_horas: num("escala_max_horas"),
      modo_precio: valorRadio("modo_precio"),
      presupuesto: valorRadio("modo_precio") === "presupuesto" ? Number($("#presupuesto").value) || null : null,
      aplicar_descuentos: $("#aplicar_descuentos").checked,
      fecha_ida: null, fecha_vuelta: null, flex_dias: 0, chollo_desde: null, chollo_hasta: null, noches_min: null, noches_max: null,
    };
    for (const s of ["ida", "vuelta"]) {
      for (const c of ["salida", "llegada"]) {
        const usar = s === "ida" || idaVuelta;
        d[`${s}_${c}_min`] = usar ? Number(form.querySelector(`[name="${s}_${c}_min"]`).value) : 0;
        d[`${s}_${c}_max`] = usar ? Number(form.querySelector(`[name="${s}_${c}_max"]`).value) : 24;
      }
    }
    const fechasExtra = !varios && modo === "fechas"
      ? extras.filter((p) => p.ida).map((p) => (idaVuelta ? { ida: p.ida, vuelta: p.vuelta } : { ida: p.ida }))
      : [];
    const vuelosViaje = varios ? tramos.map((t) => ({ origen: t.origen, destino: t.destino, fecha: t.fecha })) : [];
    if (cualquiera && !varios) d.destino = "XXX"; // "cualquier destino": no es ningún aeropuerto
    if (varios) {
      d.origen = vuelosViaje[0].origen || null;
      d.destino = vuelosViaje[0].destino || null;
      d.fecha_ida = vuelosViaje[0].fecha || null;
    } else if (modo === "fechas") {
      d.fecha_ida = $("#fecha_ida").value || null;
      d.fecha_vuelta = idaVuelta ? $("#fecha_vuelta").value || null : null;
      d.flex_dias = num("flex_dias");
    } else {
      d.chollo_desde = $("#chollo_desde").value || null;
      d.chollo_hasta = $("#chollo_hasta").value || null;
      if (idaVuelta) {
        d.noches_min = num("noches_min");
        d.noches_max = num("noches_max");
      }
    }

    const errores = [];
    const hoy = hoyMas(0);
    if (varios) {
      if (vuelosViaje.some((t) => !t.origen || !t.destino)) errores.push("Elige de la lista los aeropuertos de cada vuelo.");
      vuelosViaje.forEach((t, i) => {
        if (t.origen && t.origen === t.destino) errores.push(`En el vuelo ${i + 1} la salida y la llegada son el mismo aeropuerto.`);
        if (!t.fecha) errores.push(`Pon la fecha del vuelo ${i + 1}.`);
        else if (i && vuelosViaje[i - 1].fecha && t.fecha < vuelosViaje[i - 1].fecha) errores.push(`El vuelo ${i + 1} no puede ser antes que el ${i}.`);
      });
      if (vuelosViaje[0].fecha && vuelosViaje[0].fecha < hoy) errores.push("El primer vuelo ya ha pasado.");
    } else {
      if (!origen || (!destino && !cualquiera)) errores.push(cualquiera ? "Elige tu aeropuerto de salida de la lista." : "Elige los dos aeropuertos de la lista.");
      if (!cualquiera && origen && origen === destino) errores.push("El aeropuerto de salida y el de llegada no pueden ser el mismo.");
    }
    fechasExtra.forEach((p, i) => {
      if (p.ida < hoy) errores.push(`Las fechas ${i + 2} ya han pasado.`);
      if (idaVuelta && (!p.vuelta || p.vuelta < p.ida)) errores.push(`En las fechas ${i + 2}, la vuelta debe ser el mismo día o después de la ida.`);
    });
    if (varios) {
      // (fechas de cada vuelo, ya comprobadas arriba)
    } else if (modo === "fechas") {
      if (!d.fecha_ida) errores.push("Pon la fecha de ida.");
      else if (d.fecha_ida < hoy) errores.push("La fecha de ida ya ha pasado.");
      if (idaVuelta && (!d.fecha_vuelta || d.fecha_vuelta < d.fecha_ida)) errores.push("La vuelta debe ser el mismo día o después de la ida.");
    } else {
      if (!d.chollo_desde || !d.chollo_hasta || d.chollo_hasta < d.chollo_desde) errores.push("Revisa el periodo del chollo (desde / hasta).");
      if (d.chollo_hasta && d.chollo_hasta < hoy) errores.push("El periodo del chollo ya ha pasado.");
      if (idaVuelta && d.noches_max < d.noches_min) errores.push("Las noches máximas deben ser al menos las mínimas.");
    }
    const pasajeros = d.adultos + d.ninos + d.bebes;
    if (pasajeros > 9) errores.push(`Máximo 9 pasajeros en total (ahora hay ${pasajeros}).`);
    if (d.bebes > d.adultos) errores.push("Como máximo un bebé por adulto.");
    if (d.maletas_cabina > d.adultos + d.ninos || d.maletas_20kg > d.adultos + d.ninos)
      errores.push("Como máximo una maleta de cada tipo por adulto o niño.");
    if (d.modo_precio === "presupuesto" && !(d.presupuesto > 0)) errores.push("Escribe tu presupuesto máximo.");

    $("#errores").innerHTML = errores.map(esc).join("<br>");
    if (errores.length) return;

    // Solo se envían si se usan (así no hace falta haber actualizado la base de datos si no los usas)
    if (salidasValidas().length || "origenes_extra" in b) d.origenes_extra = varios ? [] : salidasValidas();
    if ("destinos_extra" in b) d.destinos_extra = []; // la llegada es siempre una
    if (fechasExtra.length || "fechas_extra" in b) d.fechas_extra = fechasExtra;
    if (varios || "tramos_viaje" in b) d.tramos_viaje = vuelosViaje;
    if (cualquiera || "cualquier_destino" in b) {
      d.cualquier_destino = cualquiera && !varios;
      d.paises_excluidos = d.cualquier_destino ? paisesExcluidos : [];
    }
    d.nombre = $("#nombre").value.trim() || (varios
      ? paradas().map((c) => nombreAeropuerto(datos, c, false)).join(" → ")
      : cualquiera ? `${nombreAeropuerto(datos, origen, false)} → cualquier destino`
      : `${nombreAeropuerto(datos, origen, false)} → ${nombreAeropuerto(datos, destino, false)}`);
    try {
      const guardada = await conCarga(ev.submitter, editando ? api.actualizarBusqueda(id, d) : api.crearBusqueda(d));
      aviso(editando ? "Cambios guardados: el robot la revisa en un minuto" : "¡Búsqueda creada! El robot la revisa en un minuto");
      location.hash = `#/busqueda/${guardada.id}`;
    } catch (e) {
      $("#errores").textContent = e.message;
    }
  });
}
