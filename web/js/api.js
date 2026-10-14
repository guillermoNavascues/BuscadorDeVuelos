// Acceso a los datos: Supabase de verdad o, si no está configurado (o con ?demo), datos de ejemplo.
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "./config.js";
import { crearDemo } from "./demo.js";

export const configurado = Boolean(SUPABASE_URL) && !SUPABASE_URL.includes("TU-PROYECTO");
export const modoDemo = new URLSearchParams(location.search).has("demo");

const ERRORES = [
  [/invalid login credentials/i, "Correo o contraseña incorrectos."],
  [/email not confirmed/i, "Todavía no has confirmado tu correo: revisa tu bandeja de entrada (y el spam)."],
  [/database error saving new user|registro cerrado/i, "Registro cerrado: esta web ya tiene dueño (solo admite una cuenta)."],
  [/user already registered/i, "Ese correo ya tiene cuenta. Entra con tu contraseña."],
  [/password should be at least/i, "La contraseña debe tener al menos 6 caracteres."],
  [/rate limit/i, "Demasiados intentos seguidos. Espera unos minutos."],
  [/cualquier_destino|paises_excluidos|busquedas_cualquier_valido/i, "Para «cualquier destino» falta actualizar la base de datos: en Supabase → SQL Editor pega todo supabase/instalar.sql y pulsa Run."],
  [/fechas_extra|tramos_viaje|busquedas_viaje_valido/i, "Para varias fechas o varios destinos falta actualizar la base de datos: en Supabase → SQL Editor pega todo supabase/instalar.sql y pulsa Run."],
  [/origenes_extra|destinos_extra|busquedas_extras_max/i, "Para usar varios aeropuertos falta actualizar la base de datos: en Supabase → SQL Editor pega todo supabase/instalar.sql y pulsa Run."],
  [/ntfy_pausa|zona_horaria/i, "Para el horario solo Telegram falta actualizar la base de datos: en Supabase → SQL Editor pega todo supabase/instalar.sql y pulsa Run."],
  [/ntfy_tema|alarma_chollos|alarma_prueba/i, "Para la alarma falta actualizar la base de datos: en Supabase → SQL Editor pega todo supabase/instalar.sql y pulsa Run."],
  [/jwt expired|permission denied for (table|relation|sequence)|no autorizado/i, "Tu sesión ha caducado: vuelve a entrar."],
  [/telegram solo se vincula/i, "El chat de Telegram solo se vincula enviando el código al bot."],
  [/aerolineas_web_https/i, "La web oficial tiene que empezar por https://"],
  [/violates check constraint/i, "Algún dato no es válido. Revisa el formulario."],
  [/telegram_prueba/i, "Falta actualizar la base de datos: en Supabase → SQL Editor pega todo supabase/instalar.sql y pulsa Run."],
  [/failed to fetch|network/i, "No hay conexión con la base de datos. Revisa tu internet."],
];

function traducir(error) {
  const texto = error?.message || String(error);
  const encontrado = ERRORES.find(([patron]) => patron.test(texto));
  return new Error(encontrado ? encontrado[1] : texto);
}

function comprobar({ data, error }) {
  if (error) throw traducir(error);
  return data;
}

const haceDias = (dias) => new Date(Date.now() - dias * 86400000).toISOString();
const MAX_FILAS = 1000; // Supabase devuelve como mucho 1000 filas por petición

async function crearReal() {
  // Versión fija: una actualización del CDN no puede cambiar el código que maneja tu sesión sin que lo sepas
  const { createClient } = await import("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.117.3/+esm");
  const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  const usuario = async () => (await sb.auth.getSession()).data.session?.user ?? null;
  const volverAqui = location.origin + location.pathname;

  /** Lee todas las páginas de una consulta (de 1000 en 1000, como mucho `paginas`). */
  async function todas(consulta, paginas = 6) {
    const filas = [];
    for (let i = 0; i < paginas; i++) {
      const lote = comprobar(await consulta().range(i * MAX_FILAS, (i + 1) * MAX_FILAS - 1));
      filas.push(...lote);
      if (lote.length < MAX_FILAS) break;
    }
    return filas;
  }

  return {
    usuario,
    alCambiarSesion: (cb) => sb.auth.onAuthStateChange((_evento, sesion) => cb(sesion?.user ?? null)),
    async entrar(email, password) {
      comprobar(await sb.auth.signInWithPassword({ email, password }));
    },
    async registrar(email, password) {
      return comprobar(await sb.auth.signUp({ email, password, options: { emailRedirectTo: volverAqui } }));
    },
    async recuperar(email) {
      comprobar(await sb.auth.resetPasswordForEmail(email, { redirectTo: volverAqui }));
    },
    async cambiarPassword(password) {
      comprobar(await sb.auth.updateUser({ password }));
    },
    salir: () => sb.auth.signOut(),

    async perfil() {
      const u = await usuario();
      return comprobar(await sb.from("perfiles").select("*").eq("id", u.id).single());
    },
    async guardarPerfil(campos) {
      const u = await usuario();
      return comprobar(await sb.from("perfiles").update(campos).eq("id", u.id).select().single());
    },
    pedirPruebaTelegram() {
      return this.guardarPerfil({ telegram_prueba: true });
    },

    busquedas: async () => comprobar(await sb.from("busquedas").select("*").order("creada", { ascending: false })),
    busqueda: async (id) => comprobar(await sb.from("busquedas").select("*").eq("id", id).single()),
    crearBusqueda: async (datos) => comprobar(await sb.from("busquedas").insert(datos).select().single()),
    actualizarBusqueda: async (id, campos) =>
      comprobar(await sb.from("busquedas").update(campos).eq("id", id).select().single()),
    borrarBusqueda: async (id) => comprobar(await sb.from("busquedas").delete().eq("id", id)),

    /** Mejor precio de cada revisión (para la gráfica), del más antiguo al más reciente. */
    historial: (id, desde = null) =>
      todas(() => {
        let q = sb.from("precios").select("revisado,precio_total,fuente").eq("busqueda", id).eq("es_mejor", true);
        if (desde) q = q.gte("revisado", desde);
        return q.order("revisado", { ascending: true });
      }),
    /** Últimos 3 días de todas las búsquedas (minigráficas del panel). */
    historialTodas: () =>
      todas(() =>
        sb.from("precios").select("busqueda,revisado,precio_total").eq("es_mejor", true).gte("revisado", haceDias(3))
          .order("revisado", { ascending: true }),
      ),
    /** Mejor opción de la última revisión de cada búsqueda: solo fechas y vuelos (para el panel). */
    async ultimosMejores(ids) {
      const filas = await Promise.all(ids.map(async (id) => comprobar(
        await sb.from("precios").select("busqueda,revisado,fecha_ida,fecha_vuelta,ida:detalle->ida,vuelta:detalle->vuelta,siguientes:detalle->siguientes")
          .eq("busqueda", id).eq("es_mejor", true).order("revisado", { ascending: false }).limit(1),
      )));
      return filas.flat();
    },
    async ultimasOpciones(id) {
      const ultima = comprobar(
        await sb.from("precios").select("revisado").eq("busqueda", id).order("revisado", { ascending: false }).limit(1),
      );
      if (!ultima.length) return [];
      return comprobar(
        await sb.from("precios").select("*").eq("busqueda", id).eq("revisado", ultima[0].revisado)
          .order("precio_total", { ascending: true }),
      );
    },
    avisos: async (id) =>
      comprobar(await sb.from("avisos").select("*").eq("busqueda", id).order("enviado", { ascending: false }).limit(50)),
    avisosRecientes: async () =>
      comprobar(await sb.from("avisos").select("*").order("enviado", { ascending: false }).limit(12)),

    aerolineas: async () => comprobar(await sb.from("aerolineas").select("*").order("nombre")),
    guardarAerolinea: async (a) => comprobar(await sb.from("aerolineas").upsert(a).select().single()),
    borrarAerolinea: async (codigo) => comprobar(await sb.from("aerolineas").delete().eq("codigo", codigo)),

    fuentes: async () => comprobar(await sb.from("estado_fuentes").select("*").order("intervalo_min")),
    actualizarFuente: async (fuente, campos) =>
      comprobar(await sb.from("estado_fuentes").update(campos).eq("fuente", fuente).select().single()),
    ejecuciones: async (limite = 40) =>
      comprobar(await sb.from("ejecuciones").select("*").order("inicio", { ascending: false }).limit(limite)),
    ejecucionesDesde: (dias) =>
      todas(() => sb.from("ejecuciones").select("inicio,duracion_s,resumen").gte("inicio", haceDias(dias))),

    /** Señal de vida del robot (null si no hay o si falta actualizar la base de datos). */
    async latido() {
      const { data, error } = await sb.from("ajustes").select("valor").eq("clave", "latido").maybeSingle();
      return error ? null : data?.valor ?? null;
    },

    /**
     * Tiempo real: avisa al instante de inserciones/cambios en una tabla.
     * Devuelve la función para dejar de escuchar.
     */
    suscribir(tabla, alCambiar, filtro = undefined) {
      const canal = sb
        .channel(`rt-${tabla}-${filtro || "todo"}-${Math.random().toString(36).slice(2, 8)}`)
        .on("postgres_changes", { event: "*", schema: "public", table: tabla, ...(filtro ? { filter: filtro } : {}) },
          (cambio) => alCambiar(cambio))
        .subscribe();
      return () => sb.removeChannel(canal);
    },
  };
}

export const api = modoDemo || !configurado ? crearDemo() : await crearReal();
export const esDemo = modoDemo || !configurado;

/**
 * Alarma de prueba enviada directamente a ntfy desde el navegador (llega al instante: no espera al robot).
 * En el modo demo no se envía nada.
 */
export async function enviarAlarmaPrueba(tema) {
  if (esDemo) return;
  const r = await fetch("https://ntfy.sh/", {
    method: "POST",
    body: JSON.stringify({
      topic: tema,
      title: "🔔 Prueba de alarma",
      message: "Así sonará tu móvil cuando haya un chollazo (bajada fuerte, chollo o dentro de tu objetivo).",
      priority: 5,
      tags: ["airplane", "rotating_light"],
      click: `${location.origin}${location.pathname}#/perfil`,
    }),
  });
  if (!r.ok) throw new Error(`ntfy no aceptó la alarma (HTTP ${r.status})`);
}
