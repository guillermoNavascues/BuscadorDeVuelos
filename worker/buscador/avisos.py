"""Avisos por Telegram (bot propio) y vinculación del chat con la web."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from . import aeropuertos
from .decision import Decision
from .filtros import aeropuertos_busqueda
from .modelos import Opcion, Trayecto
from .tiempo import ZONA
from .viaje import ruta_viaje

log = logging.getLogger(__name__)

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha(d) -> str:
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def _e(texto) -> str:
    return html.escape(str(texto), quote=False)


def es_https(url) -> bool:
    """Solo se enlaza a direcciones https:// (la web oficial de una aerolínea la puedes editar tú)."""
    return bool(re.fullmatch(r"https://[^\s\"'<>]+", str(url or "")))


def _href(url) -> str:
    """Dirección dentro de href="...": con las comillas escapadas, para que no pueda romper el mensaje."""
    return html.escape(str(url), quote=True)


def _linea_trayecto(etiqueta: str, tr: Trayecto, aerolineas: dict[str, dict]) -> str:
    vuelos = ", ".join(
        f"{aerolineas.get(t.aerolinea, {}).get('nombre', t.aerolinea)} {t.aerolinea}{t.numero}"
        + (
            f" (operado por {aerolineas.get(t.operadora, {}).get('nombre', t.operadora)})"
            if t.operadora and t.operadora != t.aerolinea
            else ""
        )
        for t in tr.tramos
    )
    if tr.escalas == 0:
        escalas = "directo"
    else:
        sitios = ", ".join(
            f"{t.destino} {m // 60} h {m % 60:02d} min" for t, m in zip(tr.tramos, tr.esperas_min)
        )
        escalas = f"{tr.escalas} escala{'s' if tr.escalas > 1 else ''} ({sitios})"
    dia_sig = " (+1 día)" if tr.llegada.date() > tr.salida.date() else ""
    return (
        f"🛫 <b>{etiqueta}</b> {_fecha(tr.salida)} · {tr.salida:%H:%M} {tr.origen} → "
        f"{tr.llegada:%H:%M}{dia_sig} {tr.destino}\n      {_e(vuelos)} · {escalas}"
    )


def ruta_txt(b: dict) -> str:
    """"Jerez (XRY) o Sevilla (SVQ) → París Charles de Gaulle (CDG)"; con varios destinos, todo el recorrido."""
    if b.get("cualquier_destino"):
        return " o ".join(map(aeropuertos.nombre, aeropuertos_busqueda(b)[0])) + " → cualquier destino"
    recorrido = ruta_viaje(b) if b.get("modo") == "fechas" else []
    if recorrido:
        return " → ".join(map(aeropuertos.nombre, recorrido))
    origenes, destinos = aeropuertos_busqueda(b)
    return " o ".join(map(aeropuertos.nombre, origenes)) + " → " + " o ".join(map(aeropuertos.nombre, destinos))


def pasajeros_txt(b: dict) -> str:
    partes = [f"{b['adultos']} adulto{'s' if b['adultos'] != 1 else ''}"]
    if b.get("ninos"):
        partes.append(f"{b['ninos']} niño{'s' if b['ninos'] != 1 else ''}")
    if b.get("bebes"):
        partes.append(f"{b['bebes']} bebé{'s' if b['bebes'] != 1 else ''}")
    maletas = []
    if b.get("maletas_cabina"):
        maletas.append(f"{b['maletas_cabina']} maleta{'s' if b['maletas_cabina'] != 1 else ''} de cabina")
    if b.get("maletas_20kg"):
        maletas.append(f"{b['maletas_20kg']} facturada{'s' if b['maletas_20kg'] != 1 else ''} de 20 kg")
    return ", ".join(partes) + (" · " + ", ".join(maletas) if maletas else " · sin maletas extra")


def mensaje_aviso(
    b: dict,
    op: Opcion,
    decision: Decision,
    enlaces_compra: list[dict],
    enlace_google: str,
    aerolineas: dict[str, dict],
    url_web: str | None,
    comprar: list[dict] | None = None,
    mismo_aeropuerto: Opcion | None = None,
    top: list[Opcion] | None = None,
) -> str:
    ruta = ruta_txt(b)
    lineas = [
        f"<b>{_e(decision.titulo)}</b>",
        f"<b>{_e(b['nombre'])}</b>",
        _e(ruta) + (" · varios destinos" if op.siguientes else " · ida y vuelta" if op.vuelta else " · solo ida"),
        "",
    ]
    if b.get("cualquier_destino"):
        lineas[-1:-1] = [f"🌍 Ahora el más barato: <b>{_e(aeropuertos.nombre(op.ida.destino))}</b>"]
    if op.siguientes:
        lineas += [_linea_trayecto(f"Vuelo {i}", tr, aerolineas) for i, tr in enumerate([op.ida] + op.siguientes, 1)]
    else:
        lineas.append(_linea_trayecto("Ida", op.ida, aerolineas))
    if op.vuelta:
        lineas.append(_linea_trayecto("Vuelta", op.vuelta, aerolineas))
    lineas += ["", f"👥 {_e(pasajeros_txt(b))}", "", f"💶 <b>TOTAL: {eur(op.precio_total)}</b> (todos los pasajeros)"]
    lineas.append(f"   Billetes: {eur(op.precio_billetes)}")
    if op.precio_maletas:
        lineas.append(f"   Maletas: {eur(op.precio_maletas)} (máximo estimado: puede salir más barato)")
    if op.descuento:
        lineas.append(f"   Descuento: −{eur(op.descuento)} ({_e(op.descuento_detalle)})")
    ctx = decision.contexto
    extra = []
    if "minimo_visto" in ctx:
        extra.append(f"mínimo visto {eur(ctx['minimo_visto'])}")
    if "habitual" in ctx:
        extra.append(f"billetes habituales {ctx['habitual'][0]}-{ctx['habitual'][1]} €")
    if extra:
        lineas.append("📊 " + " · ".join(extra))
    lineas += ["", f"ℹ️ {_e(decision.motivo)}"]
    if op.vuelta_a_otro_aeropuerto:
        aviso = (f"🔁 <b>Ojo: vuelves a {_e(aeropuertos.nombre(op.vuelta.destino))}</b>, no a "
                 f"{_e(aeropuertos.nombre(op.ida.origen))}, de donde sales: así sale más barato.")
        if mismo_aeropuerto is not None and mismo_aeropuerto is not op:
            aviso += (f" Volviendo a {_e(aeropuertos.nombre(mismo_aeropuerto.ida.origen))} costaría "
                      f"{eur(mismo_aeropuerto.precio_total)} (+{eur(mismo_aeropuerto.precio_total - op.precio_total)}).")
        lineas.append(aviso)
    if op.siguientes:
        lineas.append("⚠️ Cada vuelo es un billete aparte: tienes que comprarlos todos.")
    elif op.billetes_separados:
        lineas.append("⚠️ Ida y vuelta son billetes separados: tienes que comprar los dos.")
    for nota in op.notas:
        lineas.append(f"ℹ️ {_e(nota)}")
    if top and len(top) > 1:
        lineas += ["", "🏆 <b>Los destinos más baratos ahora</b> (elige uno en la web y lo vigilo):"]
        for i, o in enumerate(top, 1):
            fechas = _fecha(o.ida.fecha) + (f" → {_fecha(o.vuelta.fecha)}" if o.vuelta else "")
            lineas.append(f"{i}. {_e(aeropuertos.nombre(o.ida.destino))} · <b>{eur(o.precio_total)}</b> · {fechas}")
    if comprar:
        lineas += ["", "🛒 <b>Comprar ya (Google Flights, con estos vuelos elegidos):</b>"]
        for e in comprar:
            lineas.append(f'👉 <a href="{_href(e["url"])}">{_e(e["texto"])}</a>')
    lineas += ["", "🏢 <b>O en la web oficial:</b>"]
    for e in (x for x in enlaces_compra if es_https(x["url"])):
        lineas.append(f'• <a href="{_href(e["url"])}">{_e(e["aerolinea"])}</a>')
    if not op.siguientes:  # con varios destinos, Google solo enseña los vuelos de uno en uno
        lineas.append(f'🔎 <a href="{_href(enlace_google)}">Ver los más baratos en Google Flights</a>')
    if url_web:
        lineas.append(f'📈 <a href="{_href(url_web)}">Historial en tu web</a>')
    lineas.append("Revisa el precio final en la web antes de pagar: puede cambiar en cualquier momento.")
    return unir_sin_pasarse(lineas)


# Alarma en el móvil para los chollazos con ntfy (app gratuita y de código abierto: https://ntfy.sh).
# El robot publica en un "tema" secreto que solo conocen tu web y tu móvil (el nombre hace de contraseña).
# Con prioridad máxima, en Android se le puede poner sonido de alarma y que se salte el "No molestar".
NTFY_URL = "https://ntfy.sh/"
TIPOS_ALARMA = {
    "bajada_fuerte": "📉 Bajada fuerte de precio",
    "chollo": "🔥 Chollo encontrado",
    "presupuesto": "✅ Dentro de tu objetivo",
}


def alarma(tema: str, titulo: str, texto: str, enlace: str | None = None,
           comprar: list[dict] | None = None, http=None) -> bool:
    """Notificación urgente en el móvil. Devuelve True si ntfy la aceptó."""
    if not tema:
        return False
    datos = {"topic": tema, "title": titulo[:200], "message": texto[:1000], "priority": 5,
             "tags": ["airplane", "rotating_light"]}
    if enlace:
        datos["click"] = enlace
    botones = [{"action": "view", "label": e["texto"], "url": e["url"], "clear": True} for e in (comprar or [])[:2]]
    if botones:
        datos["actions"] = botones
    try:
        r = (http or httpx).post(NTFY_URL, json=datos, timeout=20)
    except httpx.HTTPError as e:
        log.warning("ntfy no responde: %s", type(e).__name__)
        return False
    if r.status_code != 200:
        log.warning("ntfy no aceptó la alarma (HTTP %s)", r.status_code)  # sin el tema: el registro es público
    return r.status_code == 200


def texto_alarma(b: dict, total: float, motivo: str = "") -> str:
    return f"{b['nombre']}: {eur(total)} en total. {motivo} Toca para verlo o pulsa Comprar ya.".replace("  ", " ")


NOTA_PAUSA = "🔕 <i>La alarma del móvil está en pausa por tu horario «solo Telegram»: este aviso solo te llega aquí.</i>"


def _hora(valor, defecto: time) -> time:
    """"08:30" o "08:30:00" (así devuelve Supabase las columnas time) → time(8, 30)."""
    try:
        h, m = str(valor).split(":")[:2]
        return time(int(h), int(m))
    except (TypeError, ValueError):
        return defecto


def alarma_en_pausa(perfil: dict, ahora: datetime | None = None) -> bool:
    """¿Es una de las horas en las que el usuario quiere los avisos solo por Telegram (sin alarma en el móvil)?

    Las horas son las de su zona horaria (la de su navegador; España si no hay). Si el horario pasa de
    medianoche (de 23:00 a 08:00), cuenta el día en que empieza. Si "desde" y "hasta" coinciden, todo el día.
    """
    if not perfil.get("ntfy_pausa"):
        return False
    try:
        zona = ZoneInfo(perfil.get("zona_horaria") or "Europe/Madrid")
    except (ZoneInfoNotFoundError, ValueError):
        zona = ZONA
    local = (ahora or datetime.now(timezone.utc)).astimezone(zona)
    desde = _hora(perfil.get("ntfy_pausa_desde"), time(9))
    hasta = _hora(perfil.get("ntfy_pausa_hasta"), time(14))
    dias = perfil.get("ntfy_pausa_dias")
    dias = set(range(1, 8)) if dias is None else set(dias)
    t, dia = local.time(), local.isoweekday()
    if desde == hasta:
        return dia in dias
    if desde < hasta:
        return desde <= t < hasta and dia in dias
    if t >= desde:
        return dia in dias
    return t < hasta and (dia - 2) % 7 + 1 in dias  # de madrugada: la pausa empezó el día anterior


def _duracion(minutos: float) -> str:
    m = max(0, round(minutos))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def mensaje_bloqueo(web: str, motivo: str, seguidos: int, espera_min: float, hasta: datetime, ultima_hora: int,
                    en_sesion: int, sesion_min: float, desde_ok_min: float | None, busquedas: int,
                    maximo_hora: int | None = None, busqueda: str = "") -> str:
    """Una web ha bloqueado al robot: cuánto llevaba y cuánto descansa (para entender sus límites)."""
    lineas = [
        f"🚧 <b>{_e(web)} ha frenado al robot</b>",
        f"Qué ha pasado: {_e(motivo)}",
        *([f"Pasó al buscar: «{_e(busqueda)}»"] if busqueda else []),
        f"Peticiones hechas: <b>{ultima_hora} en la última hora</b> · {en_sesion} en esta sesión del robot "
        f"(lleva {_duracion(sesion_min)} en marcha)",
    ]
    if desde_ok_min is not None:
        lineas.append(f"Última vez que respondió bien: hace {_duracion(desde_ok_min)}")
    lineas += [
        f"Búsquedas activas: {busquedas}" + (f" · máximo {maximo_hora} consultas por hora" if maximo_hora else ""),
        f"{'Primer bloqueo' if seguidos == 1 else f'Bloqueo nº {seguidos} seguido'}: el robot descansa "
        f"{_duracion(espera_min)} (hasta las {hasta.astimezone(ZONA):%H:%M}) y vuelve a probar solo.",
        "Te escribo otra vez cuando vuelva a responder.",
    ]
    return "\n".join(lineas)


def mensaje_recuperada(web: str, pausa_min: float, peticiones: int) -> str:
    return (f"✅ <b>{_e(web)} vuelve a responder</b> tras {_duracion(pausa_min)} de pausa "
            f"({peticiones} peticiones en esta vuelta, sin problemas). El robot sigue con normalidad.")


LIMITE_TELEGRAM = 4000  # Telegram admite 4096 caracteres por mensaje


def unir_sin_pasarse(lineas: list[str], limite: int = LIMITE_TELEGRAM) -> str:
    """Une líneas completas sin pasar del límite (cortar a mitad rompería el HTML del mensaje)."""
    texto = ""
    for linea in lineas:
        siguiente = f"{texto}\n{linea}" if texto else linea
        if len(siguiente) > limite - 2:
            return texto + "\n…"
        texto = siguiente
    return texto


AYUDA = (
    "✈️ <b>Buscador de Vuelos</b>\n"
    "Te aviso por aquí cuando una de tus búsquedas llega a buen precio.\n\n"
    "/estado · cómo van tus búsquedas ahora mismo\n"
    "/ayuda · este mensaje\n\n"
    "Las búsquedas se crean y se editan en tu web."
)

MENSAJE_PRUEBA = (
    "🧪 <b>Mensaje de prueba</b>\n"
    "Si lees esto, los avisos de tu Buscador de Vuelos te llegarán aquí. ✅\n"
    "Escribe /estado para ver cómo van tus búsquedas."
)


def mensaje_estado(busquedas: list[dict], url_web: str | None) -> str:
    """Resumen de las búsquedas activas para el comando /estado."""
    activas = [b for b in busquedas if b.get("activa")]
    if not activas:
        return "No tienes ninguna búsqueda activa. Créala en tu web" + (f": {_e(url_web)}" if url_web else ".")
    lineas = [f"📋 <b>Tus búsquedas</b> ({len(activas)})", ""]
    for b in activas:
        ruta = ruta_txt(b)
        if b.get("precio_actual") is not None:
            precio = f"💶 <b>{eur(float(b['precio_actual']))}</b>"
            if b.get("mejor_precio") is not None:
                precio += f" · mínimo visto {eur(float(b['mejor_precio']))}"
        else:
            precio = "💶 sin precio todavía"
        lineas += [f"<b>{_e(b['nombre'])}</b>", _e(ruta), precio, f"ℹ️ {_e(b.get('estado') or 'Pendiente')}", ""]
    if url_web:
        lineas.append(f'📈 <a href="{_href(url_web)}">Abrir tu web</a>')
    return unir_sin_pasarse(lineas)


class Telegram:
    def __init__(self, token: str):
        self.url = f"https://api.telegram.org/bot{token}"
        self.http = httpx.Client(timeout=20)

    def enviar(self, chat_id: str, texto: str) -> bool:
        try:
            r = self.http.post(
                f"{self.url}/sendMessage",
                json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True},
            )
            if r.status_code != 200:
                log.warning("Telegram respondió %s: %s", r.status_code, r.text[:200])
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.warning("No se pudo enviar el aviso por Telegram: %s", type(e).__name__)
            return False

    def token_valido(self) -> bool:
        """Comprueba el token con getMe (sin escribir nada en el registro que lo revele)."""
        try:
            r = self.http.get(f"{self.url}/getMe")
        except httpx.HTTPError as e:
            log.warning("Telegram no responde: %s", type(e).__name__)
            return False
        if r.status_code != 200:
            log.warning("Telegram rechaza el token (HTTP %s)", r.status_code)
        return r.status_code == 200

    def mensajes_nuevos(self, desde_update: int | None, espera: int = 0) -> list[dict]:
        """Mensajes nuevos. Con `espera`, Telegram mantiene la petición abierta hasta esos segundos y
        contesta en cuanto llega un mensaje (así el bot responde al momento)."""
        params = {"timeout": espera, "allowed_updates": '["message"]'}
        if desde_update is not None:
            params["offset"] = desde_update + 1
        try:
            r = self.http.get(f"{self.url}/getUpdates", params=params, timeout=espera + 15)
        except httpx.HTTPError as e:
            log.warning("No se pudieron leer los mensajes de Telegram: %s", type(e).__name__)
            return []
        if r.status_code != 200:
            # 409 = el bot tiene un webhook configurado y no admite getUpdates
            log.warning("No se pudieron leer los mensajes de Telegram (HTTP %s): %s", r.status_code, r.text[:150])
            return []
        return r.json().get("result", [])


def codigo_en_mensaje(texto: str) -> str | None:
    """Acepta '/start CODIGO' o simplemente 'CODIGO'."""
    partes = (texto or "").strip().split()
    if not partes:
        return None
    candidato = partes[-1].upper()
    return candidato if 4 <= len(candidato) <= 12 and candidato.isalnum() else None


# Avisos de acceso a la cuenta de la web (lo que Supabase apunta en auth.audit_log_entries)
ACCIONES_ACCESO = {
    "login": "Inicio de sesión",
    "user_signedup": "Cuenta nueva registrada",
    "user_repeated_signup": "Intento de registro con tu correo",
    "user_recovery_requested": "Petición para recuperar la contraseña",
    "user_updated_password": "Contraseña cambiada",
    "user_modified": "Datos de la cuenta cambiados",
    "user_deleted": "Cuenta borrada",
    "user_confirmation_requested": "Petición de confirmación del correo",
    "user_reauthenticate_requested": "Petición de reautenticación",
    "invite_accepted": "Invitación aceptada",
}
NO_HAS_SIDO_TU = "¿No has sido tú? Cambia ya la contraseña (Perfil → Cambiar contraseña): eso cierra todas las demás sesiones."


def _momento(valor: str) -> datetime:
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(ZONA)


def _accion(evento: dict) -> str:
    accion = evento.get("accion") or "evento sin tipo"
    return _e(ACCIONES_ACCESO.get(accion, accion))


def _ip(evento: dict) -> str:
    ip = evento.get("ip_address")
    return (f"IP {_e(ip)}" + (" 🆕" if evento.get("nueva") else "")) if ip else "IP desconocida"


def mensaje_accesos(eventos: list[dict], en_lista: int = 10) -> str:
    """Aviso de acceso. Cada evento: created_at, ip_address, accion y nueva (IP que no estaba entre tus últimos
    inicios de sesión). Uno solo va con todo detalle; varios seguidos, en una lista."""
    if len(eventos) == 1:
        e = eventos[0]
        m = _momento(e["created_at"])
        if not e.get("ip_address"):
            ip = "🌐 IP desconocida"
        elif e.get("nueva"):
            ip = f"🌐 IP {_e(e['ip_address'])} · 🆕 <b>nueva</b>: no estaba entre tus últimos inicios de sesión"
        else:
            ip = f"🌐 IP {_e(e['ip_address'])} · ya habías entrado desde ella"
        return "\n".join([
            f"🔐 <b>{_accion(e)}</b> en tu cuenta de la web",
            f"🕒 {_fecha(m)} · {m:%H:%M:%S} (hora de Madrid)", ip, "", NO_HAS_SIDO_TU,
        ])
    primero, ultimo = _momento(eventos[0]["created_at"]), _momento(eventos[-1]["created_at"])
    nuevas = sum(1 for e in eventos if e.get("nueva"))
    lineas = [
        f"🔐 <b>{len(eventos)} accesos seguidos a tu cuenta de la web</b>",
        f"🕒 De {_fecha(primero)} {primero:%H:%M} a {_fecha(ultimo)} {ultimo:%H:%M} (hora de Madrid)"
        + (f" · {nuevas} desde IP nueva 🆕" if nuevas else ""),
        "",
    ]
    if len(eventos) > en_lista:
        lineas.append(f"(y {len(eventos) - en_lista} anteriores)")
    for e in eventos[-en_lista:]:
        m = _momento(e["created_at"])
        lineas.append(f"• {_fecha(m)} {m:%H:%M} · {_accion(e)} · {_ip(e)}")
    if nuevas:
        lineas += ["", "🆕 = IP nueva: no estaba entre tus últimos inicios de sesión"]
    lineas += ["", NO_HAS_SIDO_TU]
    return unir_sin_pasarse(lineas)


def mensaje_accesos_activados(inicios: int, ips: int) -> str:
    return (
        "🔐 <b>Avisos de acceso activados</b>\n"
        "Desde ahora te escribo aquí cada vez que alguien entre en tu cuenta de la web: la hora, la IP "
        "y si la IP es nueva.\n"
        f"En los últimos 30 días hubo {inicios} inicio{'s' if inicios != 1 else ''} de sesión "
        f"desde {ips} IP{'s' if ips != 1 else ''} distinta{'s' if ips != 1 else ''}."
    )
