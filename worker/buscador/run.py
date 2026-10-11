"""El robot: revisa las búsquedas, guarda los precios y avisa por Telegram.

Modos:
    python -m buscador.run                 una sola ronda
    python -m buscador.run --continuo 345  sin parar durante 345 minutos (GitHub Actions encadena
                                           una sesión tras otra, así el robot nunca se detiene)

Variables de entorno (secretos de GitHub):
    SUPABASE_URL, SUPABASE_SERVICE_KEY   obligatorias
    TELEGRAM_BOT_TOKEN                   para enviar avisos
    URL_WEB                              dirección de tu web (para enlazar el historial)
    FORZAR=1                             revisa ya todas las búsquedas (no se salta los bloqueos)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from . import enlaces
from .avisos import (
    AYUDA, MENSAJE_PRUEBA, NOTA_PAUSA, TIPOS_ALARMA, Telegram, alarma, alarma_en_pausa, codigo_en_mensaje, eur,
    mensaje_accesos, mensaje_accesos_activados, mensaje_aviso, mensaje_bloqueo, mensaje_estado, mensaje_recuperada,
    texto_alarma,
)
from .db import Supabase
from .decision import decidir, minutos_hasta_siguiente_revision
from .filtros import Validador, franja
from .modelos import Opcion
from .nucleo import consultar, crear_fuentes, evaluar
from .tiempo import ZONA
from .tiempo import hoy as hoy_espana
from .viaje import es_varios_destinos, salidas

log = logging.getLogger("buscador")

LIMITE_RONDA_S = 12 * 60  # tiempo máximo de consultas por ronda
BLOQUEO_MAX = timedelta(hours=48)
# Google frena al robot con las ráfagas (datos del 11/10/2026: 130 consultas en 25 min, 154 y 246 en una hora,
# y 66 + 66 seguidas al cambiar de sesión). Como mucho 90 por hora: lo que no cabe espera en la cola.
GOOGLE_POR_HORA = 90
CUPO_MINIMO = 6  # por debajo de esto no se empieza una revisión de Google (cada una son unas 5-15 consultas)
OPCIONES_GUARDADAS = 5
ESPERA_ENTRE_VUELTAS_S = 60  # en modo continuo: cada minuto se mira Telegram y qué toca revisar
MARGEN_FINAL_S = 15 * 60  # en modo continuo no se empieza una ronda si queda menos que esto
ATENCION_ESPERA_S = 10  # en modo continuo, Telegram y las pruebas de la web se atienden cada ~10 s en paralelo
LATIDO_CADA_S = 60
PRIMERA_REVISION_MIN = 2  # una búsqueda nueva se mira en cuanto la web lleve 2 min sin consultarse
LIMPIEZA_CADA = timedelta(hours=6)
VERSION_DATOS = 6

# Ritmo de cada web en modo continuo (minutos entre rondas). Lo que de verdad marca el ritmo es
# cada búsqueda (cada 20 o 40 min, ver decision.py), el máximo por hora y las pausas entre peticiones.
# Se aplica una sola vez a la base de datos (VERSION_DATOS).
RITMO_FUENTES = {
    "google_flights": {
        # Cada 2 min como mucho: una búsqueda a la que le toca no espera (el total de peticiones lo marca
        # el ritmo de cada búsqueda, cada 20 min, no esto)
        "intervalo_min": 2,
        # 15-30 s entre consultas (antes 6-16): Google frenaba al robot con las ráfagas (130 en 25 min)
        "pausa_min_s": 15,
        "pausa_max_s": 30,
        "descripcion": "Fuente principal: compara casi todas las aerolíneas (Ryanair, Vueling, Iberia, easyJet...). "
        "Cada búsqueda se revisa cada 20 min (40 si el viaje es dentro de más de 2 meses), con 90 consultas "
        "por hora como mucho y 15-30 s entre ellas, para que Google no frene al robot.",
    },
    "ryanair": {
        # Una consulta cada 10 min (antes, 3 seguidas cada 30 con 2 min de pausa): el mismo ritmo para Ryanair,
        # pero la vuelta del robot ya no se queda esperando esas pausas y Google no se retrasa
        "intervalo_min": 10,
        "max_peticiones": 1,
        "descripcion": "Confirma el precio en la propia Ryanair. Una consulta cada 10 min como mucho "
        "(menos de lo que recomiendan).",
    },
}


# ----------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------
# Peticiones hechas a cada web en esta sesión del robot (para el aviso de bloqueo: cuánto aguanta cada una)
INICIO_SESION = datetime.now(timezone.utc)
REGISTRO_PETICIONES: dict[str, list[tuple[datetime, int]]] = {}


def peticiones_desde(fuente: str, desde: datetime) -> int:
    return sum(n for momento, n in REGISTRO_PETICIONES.get(fuente, []) if momento >= desde)


def peticiones_ultima_hora(db: Supabase, fuente: str, ahora: datetime) -> int:
    """Consultas hechas a una web en la última hora, según el registro de vueltas de la base de datos
    (así cuenta también lo de la sesión anterior del robot)."""
    filas = db.leer("ejecuciones", inicio=f"gte.{(ahora - timedelta(hours=1)).isoformat()}", select="resumen")
    total = 0
    for f in filas:
        datos = ((f.get("resumen") or {}).get("fuentes") or {}).get(fuente) or {}
        total += int(datos.get("peticiones") or 0)
    return total


def avisar_estado_fuente(tg: Telegram | None, chats: list[str], nombre_web: str, cfg: dict, est: dict, cambios: dict,
                         ahora: datetime, busquedas: int, ultima_hora: int | None = None) -> None:
    """Telegram cuando una web bloquea al robot y cuando vuelve a responder."""
    if not tg or not chats:
        return
    if est["bloqueo"]:
        hasta = _fecha_hora(cambios["bloqueada_hasta"])
        ultima_ok = _fecha_hora(cfg.get("ultima_ok"))
        texto = mensaje_bloqueo(
            nombre_web, _sin_urls(est["bloqueo"]), cambios["bloqueos_seguidos"], (hasta - ahora).total_seconds() / 60, hasta,
            ultima_hora if ultima_hora is not None else peticiones_desde(cfg["fuente"], ahora - timedelta(hours=1)),
            peticiones_desde(cfg["fuente"], INICIO_SESION),
            (ahora - INICIO_SESION).total_seconds() / 60,
            (ahora - ultima_ok).total_seconds() / 60 if ultima_ok else None, busquedas,
            GOOGLE_POR_HORA if cfg["fuente"] == "google_flights" else None,
        )
    elif cfg.get("bloqueos_seguidos"):
        bloqueo = _fecha_hora(cfg.get("ultima_ronda"))  # la última vuelta en que se consultó fue la del bloqueo
        texto = mensaje_recuperada(nombre_web, (ahora - bloqueo).total_seconds() / 60 if bloqueo else 0, est["peticiones"])
    else:
        return
    for chat in chats:
        tg.enviar(chat, texto)


def _sin_urls(texto: str) -> str:
    """Quita las URLs (pueden llevar rutas, fechas o tokens) antes de escribir en el registro público."""
    return re.sub(r"https?://\S+", "<url>", str(texto))[:200]


def _registrar_fuentes(estado: dict, resultados: dict) -> None:
    """Resumen por web: solo números y tipo de error, nada personal."""
    for nombre, est in estado.items():
        por_fuente = [por[nombre] for por in resultados.values() if nombre in por]
        log.info(
            "%s: %s búsqueda(s), %s petición(es), %s vuelo(s), %s precio(s) de calendario%s",
            nombre, est["busquedas"], est["peticiones"],
            sum(len(r.opciones) for r in por_fuente), sum(len(r.calendario) for r in por_fuente),
            f" · BLOQUEADA: {_sin_urls(est['bloqueo'])}" if est["bloqueo"] else "",
        )
        for error in est["errores"][:3]:
            log.warning("%s: %s", nombre, _sin_urls(error))


def _tiene_franjas(b: dict) -> bool:
    sentidos = ("ida", "vuelta") if b.get("ida_vuelta") else ("ida",)
    return any(franja(b, s) != (0, 24, 0, 24) for s in sentidos)


def _fecha_hora(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


def _caducada(b: dict, hoy: date) -> bool:
    if b["modo"] == "fechas":
        return all(f < hoy for f in salidas(b))  # con varias fechas, cuando ya han pasado todas
    return date.fromisoformat(str(b["chollo_hasta"])) < hoy


def _aplica(fuente: str, b: dict, hoy: date) -> bool:
    info = b.get("info") or {}
    if fuente in ("ryanair", "skyscanner") and es_varios_destinos(b):
        return False  # los viajes con varios destinos solo los busca Google Flights
    if fuente == "skyscanner":
        return b["modo"] == "fechas"
    if fuente == "ryanair":
        sin_ruta = info.get("ryanair_sin_ruta_hasta")
        return not sin_ruta or date.fromisoformat(sin_ruta) <= hoy
    return True


def _ajuste(db: Supabase, clave: str):
    fila = db.leer("ajustes", clave=f"eq.{clave}")
    return fila[0]["valor"] if fila else None


# ----------------------------------------------------------------------------------------
# Mantenimiento
# ----------------------------------------------------------------------------------------
def migrar_datos(db: Supabase) -> None:
    """Pone al día los datos de configuración (sin tocar la estructura de la base de datos)."""
    if int(_ajuste(db, "version_datos") or 1) >= VERSION_DATOS:
        return
    for fuente, valores in RITMO_FUENTES.items():
        db.actualizar("estado_fuentes", {"fuente": f"eq.{fuente}"}, valores)
    db.guardar("ajustes", {"clave": "version_datos", "valor": VERSION_DATOS})
    log.info("Configuración de las webs actualizada al modo continuo (versión %s)", VERSION_DATOS)


def limpiar_historial(db: Supabase, ahora: datetime) -> None:
    """Las opciones no ganadoras solo sirven unos días; el historial de precios (la mejor de cada
    revisión) se conserva entero para la gráfica."""
    db.borrar("precios", {"es_mejor": "eq.false", "revisado": f"lt.{(ahora - timedelta(days=2)).isoformat()}"})
    db.borrar("ejecuciones", {"inicio": f"lt.{(ahora - timedelta(days=14)).isoformat()}"})


def escribir_latido(db: Supabase, modo: str, hasta: datetime | None) -> None:
    """Señal de vida del robot para la web ("en directo")."""
    db.guardar("ajustes", {"clave": "latido", "valor": {
        "en": datetime.now(timezone.utc).isoformat(), "modo": modo, "hasta": hasta.isoformat() if hasta else None,
    }})


# ----------------------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------------------
class Limitador:
    """Cuántas veces se permite algo por clave en una ventana de tiempo (en memoria: el robot vive horas)."""

    def __init__(self, maximo: int, ventana_s: float):
        self.maximo, self.ventana_s = maximo, ventana_s
        self.marcas: dict[str, list[float]] = {}

    def permitir(self, clave: str, ahora: float | None = None) -> bool:
        ahora = time.monotonic() if ahora is None else ahora
        marcas = [t for t in self.marcas.get(clave, []) if ahora - t < self.ventana_s]
        permitido = len(marcas) < self.maximo
        if permitido:
            marcas.append(ahora)
        self.marcas[clave] = marcas
        if len(self.marcas) > 10_000:  # miles de chats distintos no llenan la memoria
            self.marcas = {k: v for k, v in self.marcas.items() if v and ahora - v[-1] < self.ventana_s}
        return permitido


# El bot es público: cualquiera puede escribirle. Un chat que no es el tuyo puede mandar 5 mensajes por hora
# (adivinar un código de vinculación es imposible) y el bot contesta a desconocidos 30 veces por hora como
# mucho, así nadie puede usarlo para saturarlo. Tu chat vinculado: hasta 30 órdenes por minuto.
LIMITE_DESCONOCIDO = Limitador(5, 3600)
LIMITE_RESPUESTAS_DESCONOCIDOS = Limitador(30, 3600)
LIMITE_VINCULADO = Limitador(30, 60)


def atender_telegram(db: Supabase, tg: Telegram, perfiles: dict[str, dict], url_web: str | None, espera: int = 0) -> int:
    """Vincula chats con el código de la web, responde a /estado y /ayuda y envía mensajes de prueba."""
    offset = _ajuste(db, "telegram_offset")
    codigos = {p["telegram_codigo"].upper(): p for p in perfiles.values() if p.get("telegram_codigo")}
    por_chat = {str(p["telegram_chat_id"]): p for p in perfiles.values() if p.get("telegram_chat_id")}
    ultimo, vinculados, ignorados = offset, 0, 0
    for m in tg.mensajes_nuevos(offset, espera):
        ultimo = m["update_id"]
        mensaje = m.get("message") or {}
        chat = (mensaje.get("chat") or {}).get("id")
        texto = (mensaje.get("text") or "").strip()
        if not chat:
            continue
        if not (LIMITE_VINCULADO if str(chat) in por_chat else LIMITE_DESCONOCIDO).permitir(str(chat)):
            ignorados += 1
            continue
        codigo = codigo_en_mensaje(texto)
        if codigo in codigos:
            perfil = codigos.pop(codigo)
            db.actualizar("perfiles", {"id": f"eq.{perfil['id']}"}, {"telegram_chat_id": str(chat), "telegram_codigo": None})
            perfil["telegram_chat_id"] = str(chat)
            por_chat[str(chat)] = perfil
            tg.enviar(chat, "✅ ¡Listo! Este chat queda vinculado a tu Buscador de Vuelos. Aquí te llegarán los avisos.\n\n" + AYUDA)
            vinculados += 1
        elif str(chat) in por_chat:
            orden = texto.split()[0].lower() if texto else ""
            if orden.startswith("/estado"):
                busquedas = db.leer("busquedas", usuario=f"eq.{por_chat[str(chat)]['id']}", order="creada.desc")
                tg.enviar(chat, mensaje_estado(busquedas, url_web))
            elif orden.startswith("/start"):
                tg.enviar(chat, "✅ Este chat ya está vinculado. Aquí te llegarán los avisos.\n\n" + AYUDA)
            else:
                tg.enviar(chat, AYUDA)
        elif texto.startswith("/start") and LIMITE_RESPUESTAS_DESCONOCIDOS.permitir("*"):
            tg.enviar(chat, "Hola 👋 Para vincular este chat envíame el código que aparece en tu web (Perfil → Telegram).")
    if ignorados:
        # Sin el número de chat: el registro de GitHub es público
        log.warning("Telegram: %d mensajes ignorados por exceso (alguien insiste demasiado con el bot)", ignorados)
    if ultimo != offset:
        db.guardar("ajustes", {"clave": "telegram_offset", "valor": ultimo})

    # Mensajes de prueba pedidos desde la web (perfiles.telegram_prueba)
    for p in perfiles.values():
        if p.get("telegram_prueba") and p.get("telegram_chat_id"):
            tg.enviar(p["telegram_chat_id"], MENSAJE_PRUEBA)
            db.actualizar("perfiles", {"id": f"eq.{p['id']}"}, {"telegram_prueba": False})
            p["telegram_prueba"] = False
        if p.get("alarma_prueba"):
            ok = alarma(p.get("ntfy_tema") or "", "🔔 Prueba de alarma",
                        "Así sonará tu móvil cuando haya un chollazo. Si no ha sonado fuerte, revisa los pasos de tu Perfil.",
                        enlace=url_web)
            db.actualizar("perfiles", {"id": f"eq.{p['id']}"}, {"alarma_prueba": False})
            p["alarma_prueba"] = False
            if p.get("telegram_chat_id"):
                tg.enviar(p["telegram_chat_id"], "🔔 Alarma de prueba enviada a la app ntfy." if ok else
                          "🔔 No se pudo enviar la alarma de prueba (ntfy no respondió). Se reintentará si la pides otra vez.")
    return vinculados


# ----------------------------------------------------------------------------------------
# Avisos de acceso a la cuenta de la web
# ----------------------------------------------------------------------------------------
ACCESOS_IGNORADOS = {"token_refreshed", "token_revoked", "logout"}  # renovar la sesión o salir no es entrar
ACCESOS_AGRUPAR_DESDE = 4  # 4 o más seguidos llegan en un solo mensaje
IPS_RECORDADAS = 20
# Como mucho 6 mensajes por hora: lo que no cabe (o no se pudo enviar) espera y llega agrupado después
LIMITE_AVISOS_ACCESO = Limitador(6, 3600)


def _recordar_ips(conocidas: list[str], eventos: list[dict]) -> list[str]:
    """IPs desde las que se ha entrado, la más reciente primero. Solo cuentan los inicios de sesión: pedir
    recuperar la contraseña desde una IP no la convierte en «conocida» para cuando entre desde ella."""
    for e in eventos:
        if e.get("accion") == "login" and e.get("ip_address"):
            conocidas = [e["ip_address"]] + [ip for ip in conocidas if ip != e["ip_address"]]
    return conocidas[:IPS_RECORDADAS]


def avisar_accesos(db: Supabase, tg: Telegram, perfiles: dict[str, dict], ahora: datetime | None = None) -> int:
    """Avisa por Telegram de cada acceso a la cuenta de la web (hora, IP, tipo y si la IP es nueva).
    Devuelve los mensajes enviados. Lo que no se envía (límite por hora, Telegram caído o chat sin vincular)
    no se pierde: la marca no avanza y llega en la siguiente vuelta que se pueda."""
    ahora = ahora or datetime.now(timezone.utc)
    chat = next((p["telegram_chat_id"] for p in perfiles.values() if p.get("telegram_chat_id")), None)
    desde = _ajuste(db, "accesos_desde")
    if desde is None:
        # Primera vez: lo anterior no se avisa, y las IPs de los últimos 30 días cuentan como conocidas
        previos = db.rpc("accesos_desde", desde=(ahora - timedelta(days=30)).isoformat())
        ips = _recordar_ips([], previos)
        db.guardar("ajustes", {"clave": "accesos_ips", "valor": ips})
        db.guardar("ajustes", {"clave": "accesos_desde", "valor": ahora.isoformat()})
        if chat:
            tg.enviar(chat, mensaje_accesos_activados(sum(e.get("accion") == "login" for e in previos), len(ips)))
        log.info("Avisos de acceso activados")
        return 0
    if not chat:
        return 0
    eventos = db.rpc("accesos_desde", desde=desde)
    if not eventos:
        return 0

    conocidas = list(_ajuste(db, "accesos_ips") or [])
    vistas = conocidas
    for e in eventos:
        e["nueva"] = bool(e.get("ip_address")) and e["ip_address"] not in vistas
        vistas = _recordar_ips(vistas, [e])
    relevantes = [i for i, e in enumerate(eventos) if e.get("accion") not in ACCESOS_IGNORADOS]
    grupos = [relevantes] if len(relevantes) >= ACCESOS_AGRUPAR_DESDE else [[i] for i in relevantes]

    # Cada mensaje cubre sus eventos y los ignorados que vengan detrás (para que la marca también los pase)
    hecho = -1 if grupos else len(eventos) - 1
    enviados = 0
    for n, grupo in enumerate(grupos):
        if not LIMITE_AVISOS_ACCESO.permitir("accesos") or not tg.enviar(chat, mensaje_accesos([eventos[i] for i in grupo])):
            break
        hecho = grupos[n + 1][0] - 1 if n + 1 < len(grupos) else len(eventos) - 1
        enviados += 1
    if hecho >= 0:
        db.guardar("ajustes", {"clave": "accesos_ips", "valor": _recordar_ips(conocidas, eventos[: hecho + 1])})
        db.guardar("ajustes", {"clave": "accesos_desde", "valor": eventos[hecho]["created_at"]})
    if enviados:
        # Solo recuentos: el registro de GitHub es público (nada de IPs, horas exactas ni chats)
        avisados = [eventos[i] for i in relevantes if i <= hecho]
        log.info("Accesos a la cuenta: %d aviso(s) por Telegram (%d acceso(s), %d desde IP nueva)%s",
                 enviados, len(avisados), sum(e["nueva"] for e in avisados),
                 f"; {len(relevantes) - len(avisados)} pendiente(s) para más tarde" if len(avisados) < len(relevantes) else "")
    return enviados


class Atencion(threading.Thread):
    """En modo continuo, en paralelo a las búsquedas: contesta a Telegram en cuanto le escribes, atiende las
    pruebas pedidas desde la web en unos segundos, mantiene al día la señal de vida (aunque una búsqueda
    tarde varios minutos) y cada minuto te avisa si alguien ha entrado en tu cuenta de la web.
    Usa sus propias conexiones: no comparte nada con el hilo de las búsquedas."""

    def __init__(self, url: str, clave: str, token: str | None, url_web: str | None, hasta: datetime | None):
        super().__init__(name="atencion", daemon=True)
        self.url, self.clave, self.token, self.url_web, self.hasta = url, clave, token, url_web, hasta
        self.parar = threading.Event()
        self.fallo_accesos: str | None = None

    def accesos(self, db: Supabase, tg: Telegram, perfiles: dict[str, dict]) -> None:
        """Los avisos de acceso nunca frenan a Telegram (p. ej. si aún no está instalada la versión 8 del SQL)."""
        try:
            avisar_accesos(db, tg, perfiles)
            self.fallo_accesos = None
        except Exception as e:
            if self.fallo_accesos != type(e).__name__:  # se escribe una vez, no cada minuto
                pista = " · falta ejecutar supabase/instalar.sql (versión 8)" if "PGRST202" in str(e) else ""
                log.warning("Avisos de acceso: no se pudieron revisar: %s: %s%s", type(e).__name__, _sin_urls(e), pista)
            self.fallo_accesos = type(e).__name__

    def vuelta(self, db: Supabase, tg: Telegram | None, ultimo_latido: float) -> float:
        cada_minuto = time.monotonic() - ultimo_latido >= LATIDO_CADA_S
        if cada_minuto:
            escribir_latido(db, "continuo", self.hasta)
            ultimo_latido = time.monotonic()
        if tg:
            perfiles = {p["id"]: p for p in db.leer("perfiles")}
            if cada_minuto:
                self.accesos(db, tg, perfiles)
            if atender_telegram(db, tg, perfiles, self.url_web, espera=ATENCION_ESPERA_S):
                log.info("Telegram: chat vinculado")
        else:
            self.parar.wait(ATENCION_ESPERA_S)
        return ultimo_latido

    def run(self) -> None:
        db = Supabase(self.url, self.clave)
        tg = Telegram(self.token) if self.token else None
        ultimo_latido = float("-inf")
        while not self.parar.is_set():
            try:
                ultimo_latido = self.vuelta(db, tg, ultimo_latido)
            except Exception as e:  # un fallo de red no para la atención: se reintenta enseguida
                log.error("Fallo atendiendo Telegram: %s: %s", type(e).__name__, _sin_urls(e))
                self.parar.wait(ATENCION_ESPERA_S)


# ----------------------------------------------------------------------------------------
# Una búsqueda
# ----------------------------------------------------------------------------------------
def acumular_calendario(info: dict, nuevos: list, hoy: date, dias_validez: int = 10) -> None:
    """Guarda en info.calendario los precios vistos (chollo) y pasa el turno de fechas a la siguiente ronda."""
    acumulado = dict(info.get("calendario") or {})
    for c in nuevos:
        acumulado[f"{c.fecha_ida.isoformat()}|{c.fecha_vuelta.isoformat() if c.fecha_vuelta else ''}"] = [
            round(c.precio, 2), hoy.isoformat()
        ]
    limite = (hoy - timedelta(days=dias_validez)).isoformat()
    info["calendario"] = {
        clave: valor for clave, valor in acumulado.items() if clave[:10] > hoy.isoformat() and valor[1] >= limite
    }
    info["chollo_turno"] = int(info.get("chollo_turno", 0)) + 1


def opciones_a_guardar(validas: list[Opcion], n: int = OPCIONES_GUARDADAS) -> list[Opcion]:
    """Las n más baratas; si la más barata vuelve a otro aeropuerto, se guarda también la mejor que vuelve
    al mismo del que sales (para que puedas compararlas)."""
    elegidas = validas[:n]
    mismo = next((o for o in validas if not o.vuelta_a_otro_aeropuerto), None)
    if mismo is not None and mismo not in elegidas:
        elegidas = elegidas[: n - 1] + [mismo]
    return elegidas


def _fila_precio(b: dict, op: Opcion, es_mejor: bool, aerolineas: dict) -> dict:
    detalle = op.a_dict()
    detalle["enlaces"] = enlaces.compra(b, op, aerolineas)
    detalle["google_flights"] = enlaces.google_flights(b, op)
    detalle["comprar"] = enlaces.comprar_ya(b, op)
    return {
        "busqueda": b["id"],
        "usuario": b["usuario"],
        "fuente": op.fuente,
        "fecha_ida": op.ida.fecha.isoformat(),
        "fecha_vuelta": (op.vuelta or (op.siguientes[-1] if op.siguientes else None)).fecha.isoformat()
        if op.vuelta or op.siguientes else None,
        "precio_billetes": round(op.precio_billetes, 2),
        "precio_maletas": op.precio_maletas,
        "descuento": op.descuento,
        "precio_total": op.precio_total,
        "maletas_estimadas": op.maletas_estimadas,
        "es_mejor": es_mejor,
        "detalle": detalle,
    }


def procesar_busqueda(
    db: Supabase,
    b: dict,
    validas: list[Opcion],
    rechazos: Counter,
    calendario: list[float],
    fuentes_usadas: list[str],
    perfil: dict | None,
    aerolineas: dict,
    tg: Telegram | None,
    url_web: str | None,
    hoy: date,
    ahora: datetime,
    errores: list[str] | None = None,
) -> bool:
    """Guarda el historial, decide si avisar y actualiza la búsqueda. Devuelve True si avisó."""
    if not validas and not rechazos and errores:
        # Ninguna web pudo responder: no es que no haya vuelos. Se reintenta pronto.
        db.actualizar("busquedas", {"id": f"eq.{b['id']}"}, {
            "ultima_revision": ahora.isoformat(),
            "proxima_revision": (ahora + timedelta(minutes=20)).isoformat(),
            "estado": "No se pudo consultar en esta ronda: " + _sin_urls(errores[0])[:150],
        })
        return False

    filtros_historial = {"busqueda": f"eq.{b['id']}", "es_mejor": "eq.true", "select": "precio_total,revisado",
                         "order": "revisado.asc", "limit": 5000}
    if b.get("historial_desde"):  # tras editar el viaje, el historial anterior no se compara
        filtros_historial["revisado"] = f"gte.{b['historial_desde']}"
    puntos = db.leer("precios", **filtros_historial)
    historial = [float(p["precio_total"]) for p in puntos]
    horas = (ahora - _fecha_hora(puntos[0]["revisado"])).total_seconds() / 3600 if puntos else 0.0

    if validas:
        db.insertar("precios", [_fila_precio(b, op, i == 0, aerolineas) for i, op in enumerate(opciones_a_guardar(validas))])

    mejor = validas[0] if validas else None
    decision = decidir(b, mejor, historial, calendario, hoy, horas_historial=horas)

    info = dict(b.get("info") or {})
    info["opciones_validas"] = len(validas)
    info["rechazos"] = dict(rechazos.most_common(4))
    info["fuentes"] = fuentes_usadas
    if "habitual" in decision.contexto:
        info["habitual"] = decision.contexto["habitual"]
    if mejor and historial:
        info["variacion"] = round(mejor.precio_total - historial[-1], 2)  # respecto a la revisión anterior
    cambios = {
        "ultima_revision": ahora.isoformat(),
        "proxima_revision": (ahora + timedelta(minutes=minutos_hasta_siguiente_revision(b, hoy))).isoformat(),
        "precio_actual": mejor.precio_total if mejor else None,
        "info": info,
    }
    if mejor:
        previo = b.get("mejor_precio")
        cambios["mejor_precio"] = min(float(previo), mejor.precio_total) if previo is not None else mejor.precio_total
        cambios["estado"] = f"{len(validas)} opciones válidas · la mejor: {eur(mejor.precio_total)}"
    elif rechazos:
        motivo, veces = rechazos.most_common(1)[0]
        cambios["estado"] = f"Ningún vuelo cumple tus filtros (motivo principal: {motivo}, {veces} vuelos)"
    else:
        cambios["estado"] = "No se han encontrado vuelos para esta ruta y fechas"

    avisado = False
    if decision.avisar and mejor:
        texto = mensaje_aviso(
            b, mejor, decision, enlaces.compra(b, mejor, aerolineas), enlaces.google_flights(b, mejor), aerolineas,
            f"{url_web.rstrip('/')}/#/busqueda/{b['id']}" if url_web else None,
            comprar=enlaces.comprar_ya(b, mejor),
            mismo_aeropuerto=next((o for o in validas if not o.vuelta_a_otro_aeropuerto), None),
        )
        perfil = perfil or {}
        con_alarma = decision.tipo in TIPOS_ALARMA and perfil.get("alarma_chollos") and perfil.get("ntfy_tema")
        # En su horario «solo Telegram» el móvil no suena: el aviso llega solo por Telegram (y se lo decimos)
        if con_alarma and alarma_en_pausa(perfil, ahora):
            con_alarma = False
            texto += "\n\n" + NOTA_PAUSA
        chat = perfil.get("telegram_chat_id")
        entregado = bool(tg and chat and tg.enviar(chat, texto))
        if con_alarma:
            alarma(perfil["ntfy_tema"], decision.titulo, texto_alarma(b, mejor.precio_total, decision.motivo),
                   enlace=f"{url_web.rstrip('/')}/#/busqueda/{b['id']}" if url_web else None,
                   comprar=enlaces.comprar_ya(b, mejor))
        db.insertar("avisos", {
            "busqueda": b["id"], "usuario": b["usuario"], "tipo": decision.tipo, "motivo": decision.motivo,
            "precio_total": mejor.precio_total, "mensaje": texto, "entregado": entregado,
        })
        if decision.fija_precio:
            cambios["ultimo_aviso_precio"] = mejor.precio_total
            cambios["ultimo_aviso_en"] = ahora.isoformat()
        if decision.tipo in ("final", "sin_presupuesto", "proximo"):
            cambios["aviso_final_enviado"] = True
        avisado = True
        log.info("Aviso '%s' enviado (búsqueda %s…)", decision.tipo, b["id"][:8])

    db.actualizar("busquedas", {"id": f"eq.{b['id']}"}, cambios)
    return avisado


# ----------------------------------------------------------------------------------------
# Una ronda
# ----------------------------------------------------------------------------------------
def es_nueva(b: dict) -> bool:
    """Búsqueda recién creada (o recién editada) que todavía no tiene precio."""
    ultima = b.get("ultima_revision")
    desde = b.get("historial_desde")
    return not ultima or bool(desde and _fecha_hora(desde) > _fecha_hora(ultima))


def fuentes_listas(config: dict, pendientes: list[dict], ahora: datetime, forzar: bool) -> list[str]:
    """Webs que se pueden consultar ya. Una búsqueda nueva no espera al ritmo normal de cada web
    (para ver su primer precio cuanto antes), pero sí un mínimo entre consultas; los bloqueos se respetan siempre."""
    hay_nuevas = any(es_nueva(b) for b in pendientes)
    listas = []
    for nombre, cfg in config.items():
        bloqueada = _fecha_hora(cfg.get("bloqueada_hasta"))
        ultima = _fecha_hora(cfg.get("ultima_ronda"))
        if not cfg["activa"] or (bloqueada and bloqueada > ahora):
            continue
        intervalo = min(cfg["intervalo_min"], PRIMERA_REVISION_MIN) if hay_nuevas else cfg["intervalo_min"]
        if not forzar and ultima and ahora - ultima < timedelta(minutes=intervalo):
            continue
        listas.append(nombre)
    return listas


def ronda(db: Supabase, tg: Telegram | None, url_web: str | None, forzar: bool, limite_s: float) -> dict | None:
    """Revisa las búsquedas a las que les toca. Devuelve el resumen, o None si no había nada que hacer."""
    ahora = datetime.now(timezone.utc)
    hoy = hoy_espana()
    pendientes = []
    for b in db.leer("busquedas", activa="eq.true"):
        if _caducada(b, hoy):
            db.actualizar("busquedas", {"id": f"eq.{b['id']}"}, {"activa": False, "estado": "Caducada: las fechas ya han pasado"})
            continue
        if forzar or _fecha_hora(b["proxima_revision"]) <= ahora:
            pendientes.append(b)
    if not pendientes:
        return None
    # Primero las que más llevan esperando: con el máximo de consultas por hora ninguna se queda atrás
    pendientes.sort(key=lambda b: str(b.get("proxima_revision") or ""))

    config = {f["fuente"]: f for f in db.leer("estado_fuentes")}
    listas = fuentes_listas(config, pendientes, ahora, forzar)
    # Máximo de consultas a Google por hora (lo que no cabe espera en la cola, en vez de que Google frene al robot)
    google_hora = peticiones_ultima_hora(db, "google_flights", ahora) if "google_flights" in listas else 0
    cupo_google = GOOGLE_POR_HORA - google_hora
    google_sin_cupo = "google_flights" in listas and cupo_google < CUPO_MINIMO
    texto_cola = (f"En cola: el robot reparte las consultas a Google ({GOOGLE_POR_HORA} por hora como mucho) "
                  "para que no lo frene; se revisa en cuanto haya hueco")
    if google_sin_cupo:
        listas.remove("google_flights")
    elif "google_flights" in listas:
        config["google_flights"] = {**config["google_flights"],
                                    "max_peticiones": min(config["google_flights"]["max_peticiones"], cupo_google)}
    if not listas:
        for b in pendientes if google_sin_cupo else []:
            if b.get("estado") != texto_cola:  # solo si cambia (esto se mira cada minuto)
                db.actualizar("busquedas", {"id": f"eq.{b['id']}"}, {"estado": texto_cola})
        return None

    t0 = time.monotonic()
    ejecucion = db.insertar("ejecuciones", {"inicio": ahora.isoformat()}, devolver=True)[0]
    resumen: dict = {"forzada": forzar, "avisos": 0, "revisadas": 0, "errores": [],
                     "pendientes": len(pendientes), "fuentes_en_ronda": listas}
    try:
        aerolineas = {a["codigo"]: a for a in db.leer("aerolineas")}
        perfiles = {p["id"]: p for p in db.leer("perfiles")}
        fuentes = crear_fuentes(listas, config, aerolineas)
        tareas = {n: [b for b in pendientes if _aplica(n, b, hoy)] for n in fuentes}
        # Ryanair tiene un máximo de peticiones por ronda: primero las que hace más tiempo que no mira
        if "ryanair" in tareas:
            tareas["ryanair"].sort(key=lambda b: (b.get("info") or {}).get("ryanair_ultima", ""))
        validadores = {b["id"]: Validador(b, aerolineas) for b in pendientes}
        resultados, estado = consultar(fuentes, tareas, validadores, config, limite_s)
        _registrar_fuentes(estado, resultados)
        resumen["fuentes"] = estado
        for nombre, est in estado.items():
            REGISTRO_PETICIONES.setdefault(nombre, []).append((ahora, est["peticiones"]))
        chats = [str(p["telegram_chat_id"]) for p in perfiles.values() if p.get("telegram_chat_id")]

        for nombre, est in estado.items():
            cfg = config[nombre]
            cambios = {"ultima_ronda": ahora.isoformat()}
            if est["bloqueo"]:
                seguidos = cfg["bloqueos_seguidos"] + 1
                # Páginas sin vuelos: 20 min de descanso (luego el máximo por hora ya frena); un bloqueo claro
                # (tráfico inusual, 429...): 30 min. El doble con cada bloqueo seguido (máximo 48 h).
                base = 20 if "páginas sin vuelos" in est["bloqueo"] else max(cfg["intervalo_min"], 30)
                espera = min(timedelta(minutes=base * 2 ** (seguidos - 1)), BLOQUEO_MAX)
                cambios.update(bloqueos_seguidos=seguidos, bloqueada_hasta=(ahora + espera).isoformat(), ultimo_error=est["bloqueo"])
            else:
                cambios.update(bloqueos_seguidos=0, bloqueada_hasta=None, ultima_ok=ahora.isoformat(),
                               ultimo_error=est["errores"][-1] if est["errores"] else None)
            db.actualizar("estado_fuentes", {"fuente": f"eq.{nombre}"}, cambios)
            config[nombre] = {**cfg, **cambios}
            if est["bloqueo"] or cfg.get("bloqueos_seguidos"):  # se bloquea, o vuelve a responder tras un bloqueo
                try:
                    avisar_estado_fuente(tg, chats, cfg.get("nombre") or nombre, {**cfg, "fuente": nombre}, est, cambios,
                                         ahora, len(db.leer("busquedas", activa="eq.true", select="id")),
                                         google_hora + est["peticiones"] if nombre == "google_flights" else None)
                except Exception as e:  # el aviso nunca debe parar la ronda
                    log.warning("No se pudo avisar del estado de %s: %s", nombre, type(e).__name__)

        # Si Google ha frenado al robot, las búsquedas esperan a que vuelva (y la web dice hasta cuándo)
        google = config.get("google_flights") or {}
        google_hasta = _fecha_hora(google.get("bloqueada_hasta")) if google.get("activa") else None
        google_hasta = google_hasta if google_hasta and google_hasta > ahora else None
        for b in pendientes:
            por_fuente = resultados.get(b["id"], {})
            if not por_fuente:
                # Queda en cola para la siguiente vuelta (no se queda con una hora de revisión vieja)
                if google_hasta:
                    texto = f"En espera: Google Flights ha frenado al robot; vuelve a probar a las {google_hasta.astimezone(ZONA):%H:%M}"
                elif google_sin_cupo or ("google_flights" in estado and estado["google_flights"]["peticiones"] >= cupo_google):
                    texto = texto_cola
                else:
                    texto = "En cola: no dio tiempo en esta vuelta; se revisa en la siguiente, en unos minutos"
                db.actualizar("busquedas", {"id": f"eq.{b['id']}"}, {"estado": texto, "proxima_revision": ahora.isoformat()})
                continue
            info = dict(b.get("info") or {})
            if "ryanair" in por_fuente:
                info["ryanair_ultima"] = ahora.isoformat()
                r = por_fuente["ryanair"]
                # Sin tarifas en una consulta real y sin franjas horarias: Ryanair no vuela esa ruta
                # (con franjas, o fechas sin vuelo ese día, la respuesta también sale vacía)
                if r.peticiones and not r.opciones and not r.error and not _tiene_franjas(b):
                    info["ryanair_sin_ruta_hasta"] = (hoy + timedelta(days=3)).isoformat()
            if b["modo"] == "chollo" and "google_flights" in por_fuente:
                acumular_calendario(info, por_fuente["google_flights"].calendario, hoy)
            b["info"] = info
            try:
                validas, rechazos, calendario = evaluar(b, por_fuente, perfiles.get(b["usuario"]), aerolineas)
                if b["modo"] == "chollo":
                    # Lo "normal" de la ruta se calcula con todo lo visto en los últimos días
                    calendario = [precio for precio, _visto in (info.get("calendario") or {}).values()]
                log.info("Búsqueda %s…: %s opción(es) válida(s); descartadas: %s",
                         b["id"][:8], len(validas), dict(rechazos) or "ninguna")
                errores = [r.error for r in por_fuente.values() if r.error and not r.opciones]
                if procesar_busqueda(db, b, validas, rechazos, calendario, list(por_fuente), perfiles.get(b["usuario"]),
                                     aerolineas, tg, url_web, hoy, ahora, errores):
                    resumen["avisos"] += 1
                resumen["revisadas"] += 1
            except Exception as e:
                log.error("Error procesando la búsqueda %s…: %s", b["id"][:8], type(e).__name__)
                resumen["errores"].append(f"{b.get('nombre')}: {type(e).__name__}: {e}"[:300])
    except Exception as e:
        log.error("Fallo en la ronda: %s", type(e).__name__)
        resumen["errores"].append(f"Fallo en la ronda: {type(e).__name__}: {e}"[:500])
    finally:
        duracion = int(time.monotonic() - t0)
        db.actualizar("ejecuciones", {"id": f"eq.{ejecucion['id']}"},
                      {"fin": datetime.now(timezone.utc).isoformat(), "duracion_s": duracion, "resumen": resumen})
        # Solo números en el registro: si el repositorio es público, cualquiera puede leerlo.
        log.info("Ronda terminada en %s s: %s revisadas, %s avisos, %s incidencias",
                 duracion, resumen["revisadas"], resumen["avisos"], len(resumen["errores"]))
    return resumen


# ----------------------------------------------------------------------------------------
# Programa
# ----------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Robot del Buscador de Vuelos")
    parser.add_argument("--continuo", type=float, metavar="MINUTOS", help="funcionar sin parar durante estos minutos")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx registra cada URL pedida (rutas, fechas...) y fli escribe fechas de viaje en sus avisos:
    # no deben aparecer en registros públicos (los fallos ya se resumen sin datos personales)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("fli").setLevel(logging.ERROR)

    url, clave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    hay = lambda nombre: "sí" if os.environ.get(nombre) else "NO"  # nunca se escribe el valor
    log.info("Configuración: SUPABASE_URL=%s · SUPABASE_SERVICE_KEY=%s · TELEGRAM_BOT_TOKEN=%s · URL_WEB=%s",
             hay("SUPABASE_URL"), hay("SUPABASE_SERVICE_KEY"), hay("TELEGRAM_BOT_TOKEN"), hay("URL_WEB"))
    if not url or not clave:
        log.warning("Faltan SUPABASE_URL y/o SUPABASE_SERVICE_KEY (secretos del repositorio en GitHub). Nada que hacer.")
        return 0
    url_web = os.environ.get("URL_WEB") or None
    forzar = os.environ.get("FORZAR", "").lower() in ("1", "true", "si", "sí")

    db = Supabase(url, clave)
    inicio = time.monotonic()
    fin = inicio + args.continuo * 60 if args.continuo else None
    hasta = datetime.now(timezone.utc) + timedelta(minutes=args.continuo) if args.continuo else None

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg = Telegram(token) if token else None
    if tg and not tg.token_valido():
        log.warning("Telegram: el token no es válido, revisa el secreto TELEGRAM_BOT_TOKEN")
        tg = None
    log.info("Telegram: %s", "token válido" if tg else "sin token válido, no se pueden enviar avisos")

    try:
        migrar_datos(db)
    except Exception as e:
        log.warning("No se pudo actualizar la configuración: %s", type(e).__name__)

    # En modo continuo, Telegram y la señal de vida van en paralelo (contesta en segundos)
    atencion = Atencion(url, clave, token if tg else None, url_web, hasta) if fin else None
    if atencion:
        atencion.start()

    ultima_limpieza = None
    codigo_salida = 0
    while True:
        ahora = datetime.now(timezone.utc)
        try:
            if ultima_limpieza is None or ahora - ultima_limpieza > LIMPIEZA_CADA:
                limpiar_historial(db, ahora)
                ultima_limpieza = ahora
            if not atencion:
                escribir_latido(db, "ronda", hasta)
            if tg and not atencion:
                perfiles = {p["id"]: p for p in db.leer("perfiles")}
                if atender_telegram(db, tg, perfiles, url_web):
                    log.info("Telegram: chat vinculado")
            restante = fin - time.monotonic() if fin else None
            if restante is None:
                ronda(db, tg, url_web, forzar, LIMITE_RONDA_S)
            elif restante > MARGEN_FINAL_S:
                ronda(db, tg, url_web, forzar, min(LIMITE_RONDA_S, restante - MARGEN_FINAL_S / 2))
            forzar = False  # solo la primera vuelta revisa todo
        except Exception as e:
            # Un fallo puntual (red, Supabase...) no detiene el robot continuo: se reintenta en la siguiente vuelta
            log.error("Fallo en esta vuelta: %s: %s", type(e).__name__, _sin_urls(e))
            if not fin:
                codigo_salida = 1
        if not fin or time.monotonic() + ESPERA_ENTRE_VUELTAS_S >= fin:
            break
        time.sleep(ESPERA_ENTRE_VUELTAS_S)

    if atencion:
        atencion.parar.set()
        atencion.join(timeout=ATENCION_ESPERA_S + 20)
    log.info("Robot detenido tras %s min", round((time.monotonic() - inicio) / 60))
    return codigo_salida


if __name__ == "__main__":
    sys.exit(main())
