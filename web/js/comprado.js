// «Ya he comprado los vuelos»: con los billetes en la mano la búsqueda ya no sirve, así que se borra
// (con su historial), después de confirmarlo. Está en la tarjeta del panel, en la página de la búsqueda
// y como botón debajo de cada aviso de Telegram.
import { api } from "./api.js";
import { icono } from "./iconos.js";
import { aviso, confirmar, esc } from "./util.js";

export const botonComprado = (b, pequeno = false) =>
  `<button type="button" class="${pequeno ? "pequeno " : ""}exito" data-comprado="${esc(b.id)}">${icono("check")}Ya he comprado los vuelos</button>`;

/** Pide confirmación y borra la búsqueda. Devuelve true si se borró. */
export async function yaHeComprado(b) {
  const ok = await confirmar({
    titulo: "¿Ya tienes los billetes?",
    texto: `Se borrará "${b.nombre}" con todo su historial de precios y dejarás de recibir sus avisos. No se puede deshacer.`,
    aceptar: "Sí, borrar la búsqueda",
  });
  if (!ok) return false;
  try {
    await api.borrarBusqueda(b.id);
    aviso("¡Buen viaje! Búsqueda borrada");
    return true;
  } catch (e) {
    aviso(e.message, "error");
    return false;
  }
}
