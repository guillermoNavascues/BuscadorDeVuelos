"""Lógica común del robot: consultar las webs en paralelo y evaluar los resultados."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import Counter, defaultdict

from . import precios
from .filtros import Validador
from .fuentes.google_flights import GoogleFlights
from .fuentes.ryanair import Ryanair
from .fuentes.skyscanner import Skyscanner
from .modelos import ErrorExplicado, FuenteBloqueada, Opcion, ResultadoFuente

log = logging.getLogger(__name__)


def crear_fuentes(nombres: list[str], config: dict[str, dict], aerolineas: dict[str, dict]) -> dict:
    permitidas = {c for c, a in aerolineas.items() if a.get("permitida")}
    fuentes = {}
    for nombre in nombres:
        cfg = config[nombre]
        if nombre == "google_flights":
            fuentes[nombre] = GoogleFlights(cfg["pausa_min_s"], cfg["pausa_max_s"], permitidas)
        elif nombre == "ryanair":
            fuentes[nombre] = Ryanair()
        elif nombre == "skyscanner":
            fuentes[nombre] = Skyscanner()
    return fuentes


def consultar(
    fuentes: dict,
    tareas: dict[str, list[dict]],
    validadores: dict[str, Validador],
    config: dict[str, dict],
    limite_s: float,
) -> tuple[dict[str, dict[str, ResultadoFuente]], dict[str, dict]]:
    """Cada web trabaja en su propio hilo, con su propio ritmo: las esperas de una no frenan a otra."""
    resultados: dict[str, dict[str, ResultadoFuente]] = defaultdict(dict)
    estado: dict[str, dict] = {}
    inicio = time.monotonic()

    def trabajar(nombre: str) -> None:
        fuente, cfg = fuentes[nombre], config[nombre]
        est = estado[nombre] = {"bloqueo": None, "errores": [], "busquedas": 0, "peticiones": 0}
        for i, b in enumerate(tareas[nombre]):
            if time.monotonic() - inicio > limite_s:
                est["errores"].append("tiempo de la ronda agotado; el resto, en la siguiente")
                break
            if fuente.peticiones >= cfg["max_peticiones"]:
                break
            if i > 0 and nombre != "google_flights":  # Google ya hace sus pausas por dentro
                time.sleep(random.uniform(cfg["pausa_min_s"], cfg["pausa_max_s"]))
            try:
                r = fuente.buscar(b, validadores[b["id"]])
            except FuenteBloqueada as e:
                log.warning("%s bloqueada: %s", nombre, e)
                est["bloqueo"] = str(e)
                est["bloqueo_en"] = b["id"]  # la búsqueda con la que pasó (para el aviso y para no empezar por ella)
                est["bloqueo_busqueda"] = b.get("nombre") or ""
                break
            except Exception as e:  # un fallo en una búsqueda no detiene las demás
                log.error("Error en %s con la búsqueda %s…: %s", nombre, b["id"][:8], type(e).__name__)
                r = ResultadoFuente(error=(str(e) if isinstance(e, ErrorExplicado) else f"{type(e).__name__}: {e}")[:300])
                est["errores"].append(r.error)
            if r.error and r.error not in est["errores"]:
                est["errores"].append(r.error)
            resultados[b["id"]][nombre] = r
            est["busquedas"] += 1
        est["peticiones"] = fuente.peticiones

    hilos = [threading.Thread(target=trabajar, args=(n,), name=n) for n in fuentes if tareas.get(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return resultados, estado


def categoria_rechazo(motivo: str) -> str:
    m = motivo.lower()
    if "franja" in m:
        return "horario fuera de tus franjas"
    if "lista blanca" in m or "bloqueada" in m:
        return "aerolínea fuera de tu lista blanca"
    if "escala de" in m:
        return "escala demasiado larga"
    if "escalas" in m:
        return "demasiadas escalas"
    if "sale de" in m or "llega a" in m or "cambio de aeropuerto" in m:
        return "otro aeropuerto distinto al elegido"
    return motivo


def evaluar(
    b: dict, por_fuente: dict[str, ResultadoFuente], perfil: dict | None, aerolineas: dict[str, dict]
) -> tuple[list[Opcion], Counter, list[float]]:
    """Filtra, calcula el precio total y ordena de más barata a más cara (sin repetidas)."""
    validador = Validador(b, aerolineas)
    rechazos: Counter = Counter()
    unicas: dict[tuple, Opcion] = {}
    calendario: list[float] = []
    for r in por_fuente.values():
        calendario += [c.precio for c in r.calendario]
        for op in r.opciones:
            motivo = validador.opcion(op)
            if motivo:
                rechazos[categoria_rechazo(motivo)] += 1
                continue
            precios.calcular(op, b, perfil, aerolineas)
            previa = unicas.get(op.clave)
            if previa is None or op.precio_total < previa.precio_total:
                unicas[op.clave] = op
    return sorted(unicas.values(), key=lambda o: o.precio_total), rechazos, calendario
