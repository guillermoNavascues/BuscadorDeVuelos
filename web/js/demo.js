// Datos de ejemplo para ver la web sin base de datos (?demo). Los cambios no se guardan.
// Simula el robot en directo: cada pocos segundos cambia algún precio.

const MIN = 60000;
const DIA = 86400000;
const iso = (ms) => new Date(ms).toISOString();
const soloFecha = (ms) => iso(ms).slice(0, 10);

function tramo(aerolinea, numero, origen, destino, fechaMs, salida, llegada) {
  const d = soloFecha(fechaMs);
  return { aerolinea, operadora: null, numero, origen, destino, salida: `${d}T${salida}`, llegada: `${d}T${llegada}` };
}

/** Serie de precios con altibajos realistas (cada 20 min durante varios días). */
function serie(busqueda, inicio, base, pasos, semilla) {
  let precio = base;
  let s = semilla;
  const aleatorio = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  const puntos = [];
  for (let i = 0; i < pasos; i++) {
    const r = aleatorio();
    if (r < 0.12) precio += Math.round((aleatorio() - 0.62) * 40);
    else if (r < 0.2) precio += Math.round((aleatorio() - 0.45) * 12);
    precio = Math.max(base * 0.72, Math.min(base * 1.25, precio));
    puntos.push({ busqueda, revisado: iso(inicio + i * 20 * MIN), precio_total: Math.round(precio * 100) / 100, fuente: "google_flights" });
  }
  return puntos;
}

function crearDatos() {
  const ahora = Date.now();
  const ida1 = ahora + 46 * DIA;
  const vuelta1 = ida1 + 4 * DIA;
  const ida3 = ahora + 12 * DIA;
  const historial = [
    ...serie("demo-1", ahora - 3 * DIA, 620, 3 * 72, 7),
    ...serie("demo-2", ahora - 3 * DIA, 92, 3 * 24, 3).map((p, i) => ({ ...p, revisado: iso(ahora - 3 * DIA + i * 60 * MIN) })),
    ...serie("demo-3", ahora - 2 * DIA, 214, 2 * 72, 11),
    ...serie("demo-4", ahora - 2 * DIA, 260, 2 * 72, 5),
    ...serie("demo-5", ahora - 2 * DIA, 150, 2 * 12, 9).map((p, i) => ({ ...p, revisado: iso(ahora - 2 * DIA + i * 120 * MIN) })),
  ];
  const ultimo = (id) => historial.filter((h) => h.busqueda === id).at(-1).precio_total;
  const penultimo = (id) => historial.filter((h) => h.busqueda === id).at(-2).precio_total;
  const minimo = (id) => Math.min(...historial.filter((h) => h.busqueda === id).map((h) => h.precio_total));
  const comun = {
    usuario: "demo", origenes_extra: [], destinos_extra: [], fechas_extra: [], tramos_viaje: [], flex_dias: 0, chollo_desde: null, chollo_hasta: null, noches_min: null, noches_max: null,
    ida_salida_min: 0, ida_salida_max: 24, ida_llegada_min: 0, ida_llegada_max: 24,
    vuelta_salida_min: 0, vuelta_salida_max: 24, vuelta_llegada_min: 0, vuelta_llegada_max: 24,
    ninos: 0, bebes: 0, maletas_cabina: 0, maletas_20kg: 0, aplicar_descuentos: true, escalas_max: 1, escala_max_horas: 6,
    activa: true, aviso_final_enviado: false, historial_desde: null, ultimo_aviso_precio: null, ultimo_aviso_en: null,
  };
  const busquedas = [
    {
      ...comun, id: "demo-1", nombre: "Puente en París", modo: "fechas", ida_vuelta: true, origen: "SVQ", destino: "ORY", origenes_extra: ["XRY"],
      fecha_ida: soloFecha(ida1), fecha_vuelta: soloFecha(vuelta1), flex_dias: 1, ida_salida_min: 6, ida_salida_max: 14,
      adultos: 2, ninos: 1, maletas_cabina: 1, maletas_20kg: 1, escala_max_horas: 4, modo_precio: "presupuesto", presupuesto: 600,
      proxima_revision: iso(ahora + 14 * MIN), ultima_revision: iso(ahora - 6 * MIN),
      mejor_precio: minimo("demo-1"), precio_actual: ultimo("demo-1"), ultimo_aviso_precio: minimo("demo-1"), ultimo_aviso_en: iso(ahora - 2 * DIA),
      estado: "27 opciones válidas", creada: iso(ahora - 12 * DIA),
      info: { variacion: ultimo("demo-1") - penultimo("demo-1"), rechazos: { "horario fuera de tus franjas": 12, "escala demasiado larga": 4 }, habitual: [480, 610] },
    },
    {
      ...comun, id: "demo-3", nombre: "Navidad en Palma", modo: "fechas", ida_vuelta: true, origen: "MAD", destino: "PMI",
      fecha_ida: soloFecha(ida3), fecha_vuelta: soloFecha(ida3 + 5 * DIA), adultos: 2, maletas_20kg: 1, modo_precio: "mas_barato", presupuesto: null,
      fechas_extra: [{ ida: soloFecha(ida3 + 7 * DIA), vuelta: soloFecha(ida3 + 12 * DIA) }, { ida: soloFecha(ida3 + 14 * DIA), vuelta: soloFecha(ida3 + 19 * DIA) }],
      proxima_revision: iso(ahora + 3 * MIN), ultima_revision: iso(ahora - 17 * MIN),
      mejor_precio: minimo("demo-3"), precio_actual: ultimo("demo-3"), estado: "14 opciones válidas", creada: iso(ahora - 5 * DIA),
      info: { variacion: ultimo("demo-3") - penultimo("demo-3"), rechazos: {} },
    },
    {
      ...comun, id: "demo-2", nombre: "Lisboa cuando sea barata", modo: "chollo", ida_vuelta: true, origen: "SVQ", destino: "LIS",
      chollo_desde: soloFecha(ahora + 7 * DIA), chollo_hasta: soloFecha(ahora + 150 * DIA), noches_min: 2, noches_max: 4,
      adultos: 1, escalas_max: 0, modo_precio: "mas_barato", presupuesto: null,
      proxima_revision: iso(ahora + 41 * MIN), ultima_revision: iso(ahora - 19 * MIN),
      mejor_precio: minimo("demo-2"), precio_actual: ultimo("demo-2"), estado: "8 opciones válidas", creada: iso(ahora - 20 * DIA),
      info: { variacion: ultimo("demo-2") - penultimo("demo-2"), rechazos: {}, habitual: [70, 115] },
    },
    {
      ...comun, id: "demo-4", nombre: "Cracovia y Zúrich", modo: "fechas", ida_vuelta: false, origen: "SVQ", destino: "KRK",
      fecha_ida: soloFecha(ida1 + 10 * DIA), fecha_vuelta: null, adultos: 1, modo_precio: "mas_barato", presupuesto: null,
      tramos_viaje: [
        { origen: "SVQ", destino: "KRK", fecha: soloFecha(ida1 + 10 * DIA) },
        { origen: "KRK", destino: "ZRH", fecha: soloFecha(ida1 + 13 * DIA) },
        { origen: "ZRH", destino: "SVQ", fecha: soloFecha(ida1 + 16 * DIA) },
      ],
      proxima_revision: iso(ahora + 27 * MIN), ultima_revision: iso(ahora - 9 * MIN),
      mejor_precio: minimo("demo-4"), precio_actual: ultimo("demo-4"), estado: "3 opciones válidas", creada: iso(ahora - 2 * DIA),
      info: { variacion: ultimo("demo-4") - penultimo("demo-4"), rechazos: {} },
    },
    {
      ...comun, id: "demo-5", nombre: "Escapada a donde sea", modo: "fechas", ida_vuelta: true, origen: "SVQ", destino: "XXX",
      origenes_extra: ["XRY"], cualquier_destino: true, paises_excluidos: ["RU", "UA", "BY", "IL", "LB", "SY"],
      fecha_ida: soloFecha(ida1 - 20 * DIA), fecha_vuelta: soloFecha(ida1 - 17 * DIA), adultos: 1, maletas_20kg: 1,
      modo_precio: "mas_barato", presupuesto: null,
      proxima_revision: iso(ahora + 94 * MIN), ultima_revision: iso(ahora - 26 * MIN),
      mejor_precio: minimo("demo-5"), precio_actual: ultimo("demo-5"), creada: iso(ahora - 2 * DIA),
      estado: `5 destinos con tus filtros · el más barato: Palma de Mallorca (PMI) ${ultimo("demo-5").toFixed(2).replace(".", ",")} €`,
      info: {
        variacion: ultimo("demo-5") - penultimo("demo-5"), rechazos: {},
        top_destinos: [["PMI", "ES", 0], ["RBA", "MA", 1], ["VIT", "ES", 14.5], ["NTE", "FR", 29.1], ["LIS", "PT", 31]].map(([destino, pais, extra]) => ({
          destino, pais, nombre: destino, precio_total: Math.round((ultimo("demo-5") + extra) * 100) / 100,
          fecha_ida: soloFecha(ida1 - 20 * DIA), fecha_vuelta: soloFecha(ida1 - 17 * DIA), escalas: 0, aerolineas: ["FR"],
        })),
      },
    },
  ];

  const opcion = (id, total, billetes, maletas, ida, vuelta, separados, fuente = "google_flights") => ({
    id, busqueda: "demo-1", revisado: iso(ahora - 6 * MIN), fuente, fecha_ida: soloFecha(ida1), fecha_vuelta: soloFecha(vuelta1),
    precio_billetes: billetes, precio_maletas: maletas, descuento: 0, precio_total: total, maletas_estimadas: maletas > 0, es_mejor: id === 1,
    detalle: {
      fuente, billetes_separados: separados, precio_billetes: billetes, precio_maletas: maletas, descuento: 0, precio_total: total,
      ida: { tramos: ida, escalas: ida.length - 1 }, vuelta: { tramos: vuelta, escalas: vuelta.length - 1 },
      desglose_maletas: maletas ? ["Ida (Vueling): (1 cabina × 50,00 € + 1 de 20 kg × 96,00 €) = 146,00 €"] : [],
      notas: [], enlaces: [{ aerolinea: "Vueling", url: "https://www.vueling.com" }, { aerolinea: "Transavia France", url: "https://www.transavia.com" }],
      google_flights: "https://www.google.com/travel/flights?q=Flights%20to%20ORY%20from%20SVQ",
      comprar: separados
        ? [{ texto: "Comprar la ida", url: "https://www.google.com/travel/flights?q=One%20way%20flights%20to%20ORY%20from%20SVQ" },
          { texto: "Comprar la vuelta", url: "https://www.google.com/travel/flights?q=One%20way%20flights%20to%20SVQ%20from%20ORY" }]
        : [{ texto: "Comprar ya", url: "https://www.google.com/travel/flights?q=Flights%20to%20ORY%20from%20SVQ" }],
    },
  });
  const p1 = ultimo("demo-1");
  const opciones = [
    opcion(1, p1, p1 - 232, 232, [tramo("VY", "8073", "SVQ", "ORY", ida1, "06:40", "09:15")], [tramo("TO", "4605", "ORY", "SVQ", vuelta1, "16:35", "18:55")], true),
    opcion(2, p1 + 22, p1 - 210, 232, [tramo("VY", "8073", "SVQ", "ORY", ida1, "06:40", "09:15")], [tramo("VY", "8076", "ORY", "SVQ", vuelta1, "19:55", "22:25")], false),
    opcion(3, p1 + 66, p1 + 66, 0, [tramo("IB", "5101", "SVQ", "MAD", ida1, "07:10", "08:15"), tramo("IB", "3402", "MAD", "ORY", ida1, "09:35", "11:40")], [tramo("IB", "3405", "ORY", "MAD", vuelta1, "13:00", "15:05"), tramo("IB", "5110", "MAD", "SVQ", vuelta1, "16:20", "17:25")], false),
  ];
  // El chollo de Lisboa: solo 2 noches y la vuelta llega pasada la medianoche
  const idaLis = ahora + 23 * DIA;
  const vueltaLis = idaLis + 2 * DIA;
  const p2 = ultimo("demo-2");
  const lisboa = opcion(4, p2, p2, 0, [tramo("FR", "7114", "SVQ", "LIS", idaLis, "06:15", "06:25")],
    [{ ...tramo("FR", "7115", "LIS", "SVQ", vueltaLis, "22:50", "00:55"), llegada: `${soloFecha(vueltaLis + DIA)}T00:55` }], false);
  const p3 = ultimo("demo-3");
  const palma = opcion(5, p3, p3 - 60, 60, [tramo("UX", "6011", "MAD", "PMI", ida3, "08:05", "09:20")],
    [tramo("UX", "6020", "PMI", "MAD", ida3 + 5 * DIA, "19:45", "21:05")], false);
  // El viaje con varios destinos: un billete por vuelo
  const p4 = ultimo("demo-4");
  const v1 = ida1 + 10 * DIA;
  const varios = opcion(6, p4, p4, 0, [tramo("FR", "7144", "SVQ", "KRK", v1, "06:30", "10:20")], [], true);
  varios.detalle.vuelta = null;
  varios.detalle.siguientes = [
    { tramos: [tramo("LX", "1367", "KRK", "ZRH", v1 + 3 * DIA, "13:05", "15:00")], escalas: 0 },
    { tramos: [tramo("VY", "6271", "ZRH", "BCN", v1 + 6 * DIA, "17:40", "19:30"), tramo("VY", "2224", "BCN", "SVQ", v1 + 6 * DIA, "21:00", "22:30")], escalas: 1 },
  ];
  varios.detalle.comprar = [1, 2, 3].map((n) => ({ texto: `Comprar el vuelo ${n}`, url: "https://www.google.com/travel/flights" }));
  opciones.push({ ...varios, busqueda: "demo-4", revisado: iso(ahora - 9 * MIN), es_mejor: true, fecha_ida: soloFecha(v1), fecha_vuelta: soloFecha(v1 + 6 * DIA) });
  opciones.push(
    { ...lisboa, busqueda: "demo-2", revisado: iso(ahora - 19 * MIN), es_mejor: true, fecha_ida: soloFecha(idaLis), fecha_vuelta: soloFecha(vueltaLis) },
    { ...palma, busqueda: "demo-3", revisado: iso(ahora - 17 * MIN), es_mejor: true, fecha_ida: soloFecha(ida3), fecha_vuelta: soloFecha(ida3 + 5 * DIA) },
  );

  // Cualquier destino: los 5 más baratos desde Sevilla o Jerez
  const p5 = ultimo("demo-5");
  const ida5 = ida1 - 20 * DIA;
  [["PMI", 0, "5512"], ["RBA", 1, "7212"], ["VIT", 14.5, "2061"], ["NTE", 29.1, "4321"], ["LIS", 31, "7114"]].forEach(([destino, extra, numero], i) => {
    const total = Math.round((p5 + extra) * 100) / 100;
    const o = opcion(7 + i, total, total, 0, [tramo("FR", numero, "SVQ", destino, ida5, "07:05", "09:10")],
      [tramo("FR", String(Number(numero) + 1), destino, "SVQ", ida5 + 3 * DIA, "18:20", "20:25")], false, "ryanair");
    opciones.push({
      ...o, busqueda: "demo-5", revisado: iso(ahora - 26 * MIN), es_mejor: i === 0, fecha_ida: soloFecha(ida5), fecha_vuelta: soloFecha(ida5 + 3 * DIA),
      detalle: { ...o.detalle, enlaces: [{ aerolinea: "Ryanair", url: "https://www.ryanair.com" }], google_flights: "https://www.google.com/travel/flights",
        comprar: [{ texto: "Comprar ya", url: "https://www.ryanair.com" }] },
    });
  });

  const avisos = [
    { id: 1, busqueda: "demo-1", usuario: "demo", enviado: iso(ahora - 2 * DIA), tipo: "presupuesto", motivo: `Total ${minimo("demo-1")} € para todos, sin pasar de tu máximo de 600 €.`, precio_total: minimo("demo-1"), entregado: true },
    { id: 2, busqueda: "demo-3", usuario: "demo", enviado: iso(ahora - 5 * 3600000), tipo: "proximo", motivo: "Sales en 12 días: a partir de ahora el precio casi siempre sube.", precio_total: ultimo("demo-3"), entregado: true },
  ];

  const aerolineas = [
    { codigo: "FR", nombre: "Ryanair", permitida: true, criterio: "Grupo Ryanair: AirlineRatings 2026: top 25 low cost (nº18), certificada en la UE", web_oficial: "https://www.ryanair.com", cabina_max: 40, facturada_nacional_max: 59.99, facturada_europa_max: 59.99, facturada_largo_max: 59.99, cobra_por: "tramo", bebe_tasa: 25, notas: "Basic solo incluye bolso 40x30x20." },
    { codigo: "VY", nombre: "Vueling", permitida: true, criterio: "AirlineRatings 2026: top 25 low cost (nº12)", web_oficial: "https://www.vueling.com", cabina_max: 50, facturada_nacional_max: 96, facturada_europa_max: 96, facturada_largo_max: 99, cobra_por: "tramo", bebe_tasa: null, notas: "" },
    { codigo: "IB", nombre: "Iberia", permitida: true, criterio: "AirlineRatings 2026: top 25 tradicionales (nº20)", web_oficial: "https://www.iberia.com", cabina_max: 0, facturada_nacional_max: 57, facturada_europa_max: 95, facturada_largo_max: 135, cobra_por: "trayecto", bebe_tasa: null, notas: "Maleta de cabina incluida." },
    { codigo: "TO", nombre: "Transavia France", permitida: true, criterio: "AirlineRatings 2026: top 25 low cost (nº20, grupo Transavia)", web_oficial: "https://www.transavia.com", cabina_max: 45, facturada_nacional_max: 70, facturada_europa_max: 70, facturada_largo_max: 70, cobra_por: "tramo", bebe_tasa: null, notas: "" },
    { codigo: "KM", nombre: "KM Malta Airlines", permitida: true, criterio: "AirlineRatings 7/7 y auditoría IOSA", web_oficial: "https://kmmaltairlines.com", cabina_max: 0, facturada_nacional_max: 70, facturada_europa_max: 70, facturada_largo_max: 120, cobra_por: "trayecto", bebe_tasa: null, notas: "" },
  ];

  const fuentes = [
    { fuente: "google_flights", nombre: "Google Flights", activa: true, intervalo_min: 5, pausa_min_s: 6, pausa_max_s: 16, max_peticiones: 60, ultima_ronda: iso(ahora - 6 * MIN), ultima_ok: iso(ahora - 6 * MIN), bloqueada_hasta: null, bloqueos_seguidos: 0, ultimo_error: null, descripcion: "Fuente principal: compara casi todas las aerolíneas." },
    { fuente: "ryanair", nombre: "Ryanair (web oficial)", activa: true, intervalo_min: 30, pausa_min_s: 120, pausa_max_s: 140, max_peticiones: 3, ultima_ronda: iso(ahora - 26 * MIN), ultima_ok: iso(ahora - 26 * MIN), bloqueada_hasta: null, bloqueos_seguidos: 0, ultimo_error: null, descripcion: "Confirma el precio en la propia Ryanair." },
    { fuente: "skyscanner", nombre: "Skyscanner", activa: false, intervalo_min: 740, pausa_min_s: 30, pausa_max_s: 60, max_peticiones: 2, ultima_ronda: null, ultima_ok: null, bloqueada_hasta: null, bloqueos_seguidos: 0, ultimo_error: null, descripcion: "Desactivada: bloquea a los robots desde la primera petición." },
  ];

  const ejecuciones = Array.from({ length: 30 }, (_, i) => ({
    id: 300 - i, inicio: iso(ahora - (i * 22 + 6) * MIN), fin: iso(ahora - (i * 22 + 4) * MIN),
    duracion_s: 70 + ((i * 37) % 110),
    resumen: { revisadas: 1 + (i % 3 === 0), avisos: i === 7 ? 1 : 0, errores: [], fuentes_en_ronda: i % 3 ? ["google_flights"] : ["google_flights", "ryanair"] },
  }));

  const perfil = { id: "demo", nombre: "Demo", familia_numerosa: "general", residente: "ninguno", telegram_chat_id: null, telegram_codigo: "K7PM4QXR", telegram_prueba: false, ntfy_tema: "vuelos-demo7k2pq9xw4m", alarma_chollos: false, alarma_prueba: false, ntfy_pausa: false, ntfy_pausa_desde: "09:00:00", ntfy_pausa_hasta: "14:00:00", ntfy_pausa_dias: [1, 2, 3, 4, 5, 6, 7], zona_horaria: "Europe/Madrid", perfil_completado: true };
  return { busquedas, historial, opciones, avisos, aerolineas, fuentes, ejecuciones, perfil };
}

export function crearDemo() {
  const d = crearDatos();
  let sesion = { id: "demo", email: "demo@ejemplo.com" };
  const oyentes = [];
  const suscriptores = new Set();
  const copia = (x) => structuredClone(x);
  const emitir = (tabla, evento, fila) => suscriptores.forEach((s) => s.tabla === tabla && s.cb({ eventType: evento, new: copia(fila) }));

  // El "robot" de demostración: cada 9 s revisa una búsqueda y, a veces, cambia el precio
  let turno = 0;
  setInterval(() => {
    const b = d.busquedas.filter((x) => x.activa)[turno++ % d.busquedas.length];
    if (!b) return;
    const anterior = b.precio_actual != null ? Number(b.precio_actual) : null;
    const r = Math.random();
    const nuevo = anterior === null
      ? Math.round((120 + Math.random() * 260) * 100) / 100
      : Math.round((r < 0.45 ? anterior : anterior + (Math.random() - 0.58) * anterior * 0.06) * 100) / 100;
    const punto = { busqueda: b.id, revisado: new Date().toISOString(), precio_total: nuevo, fuente: "google_flights", es_mejor: true };
    d.historial.push(punto);
    Object.assign(b, {
      precio_actual: nuevo, mejor_precio: b.mejor_precio != null ? Math.min(Number(b.mejor_precio), nuevo) : nuevo,
      ultima_revision: punto.revisado, proxima_revision: new Date(Date.now() + 20 * MIN).toISOString(),
      info: { ...b.info, variacion: anterior === null ? null : nuevo - anterior },
      estado: `Revisada: la mejor opción cuesta ${nuevo.toFixed(2).replace(".", ",")} €`,
    });
    emitir("precios", "INSERT", punto);
    emitir("busquedas", "UPDATE", b);
  }, 9000);

  return {
    usuario: async () => sesion,
    alCambiarSesion: (cb) => oyentes.push(cb),
    async entrar(email) {
      sesion = { id: "demo", email };
      oyentes.forEach((cb) => cb(sesion));
    },
    async registrar() {
      return { user: null };
    },
    async recuperar() {},
    async cambiarPassword() {},
    async salir() {
      sesion = null;
      oyentes.forEach((cb) => cb(null));
    },
    perfil: async () => copia(d.perfil),
    async guardarPerfil(campos) {
      Object.assign(d.perfil, campos);
      if (campos.alarma_prueba) setTimeout(() => (d.perfil.alarma_prueba = false), 5000);
      return copia(d.perfil);
    },
    async pedirPruebaTelegram() {
      d.perfil.telegram_prueba = true;
      setTimeout(() => (d.perfil.telegram_prueba = false), 5000);
      return copia(d.perfil);
    },
    busquedas: async () => copia(d.busquedas),
    busqueda: async (id) => copia(d.busquedas.find((b) => b.id === id)),
    async crearBusqueda(datos) {
      const b = { ...datos, id: `demo-${Date.now()}`, usuario: "demo", activa: true, info: {}, estado: "Pendiente de la primera revisión", proxima_revision: new Date().toISOString(), creada: new Date().toISOString() };
      d.busquedas.unshift(b);
      return copia(b);
    },
    async actualizarBusqueda(id, campos) {
      const b = d.busquedas.find((x) => x.id === id);
      Object.assign(b, campos);
      return copia(b);
    },
    async borrarBusqueda(id) {
      d.busquedas = d.busquedas.filter((b) => b.id !== id);
    },
    historial: async (id, desde = null) => copia(d.historial.filter((h) => h.busqueda === id && (!desde || h.revisado >= desde))),
    historialTodas: async () => copia(d.historial.filter((h) => h.revisado >= new Date(Date.now() - 3 * DIA).toISOString())),
    ultimasOpciones: async (id) => copia(d.opciones.filter((o) => o.busqueda === id)),
    ultimosMejores: async (ids) => copia(ids.map((id) => d.opciones.find((o) => o.busqueda === id && o.es_mejor)).filter(Boolean)),
    avisos: async (id) => copia(d.avisos.filter((a) => a.busqueda === id)),
    avisosRecientes: async () => copia(d.avisos),
    aerolineas: async () => copia(d.aerolineas),
    async guardarAerolinea(a) {
      const i = d.aerolineas.findIndex((x) => x.codigo === a.codigo);
      if (i >= 0) d.aerolineas[i] = { ...d.aerolineas[i], ...a };
      else d.aerolineas.push(a);
      return copia(a);
    },
    async borrarAerolinea(codigo) {
      d.aerolineas = d.aerolineas.filter((a) => a.codigo !== codigo);
    },
    fuentes: async () => copia(d.fuentes),
    async actualizarFuente(fuente, campos) {
      Object.assign(d.fuentes.find((f) => f.fuente === fuente), campos);
    },
    ejecuciones: async () => copia(d.ejecuciones),
    ejecucionesDesde: async () => copia(d.ejecuciones),
    latido: async () => ({ en: new Date(Date.now() - 20000).toISOString(), modo: "continuo", hasta: new Date(Date.now() + 4.2 * 3600000).toISOString() }),
    suscribir(tabla, cb) {
      const s = { tabla, cb };
      suscriptores.add(s);
      return () => suscriptores.delete(s);
    },
  };
}
