"""Cualquier destino: los destinos más baratos desde tus aeropuertos, con tus mismos filtros.

1. Ryanair da en una sola petición la tarifa más barata a cada uno de sus destinos (una por aeropuerto
   de salida y fecha: las principales, las alternativas o tu periodo de chollo).
2. Se quitan los países que no quieres (por defecto, los de riesgo para viajar: ver la web).
3. Los más baratos se comprueban con Google Flights (todas las aerolíneas) y con tus filtros de siempre:
   escalas, horarios, maletas, lista blanca y descuentos.
4. Queda un top 5 de destinos; desde la web eliges uno y se vigila como una búsqueda normal.
"""

from __future__ import annotations

import logging
import random
import time
from collections import Counter

from . import aeropuertos, viaje
from .filtros import Validador, aeropuertos_busqueda
from .modelos import FuenteBloqueada, Opcion, ResultadoFuente
from .nucleo import evaluar

log = logging.getLogger(__name__)

CUALQUIERA = "XXX"  # código de "destino" que se guarda en la búsqueda (no es ningún aeropuerto)
CANDIDATOS = 6  # cuántos de los más baratos de Ryanair se comprueban con Google
TOP = 5
CONSULTAS_POR_CANDIDATO = 6  # lo que suele gastar en Google comprobar un destino (para no pasar del cupo)
MAX_RYANAIR = 12  # peticiones a Ryanair por revisión como mucho (aeropuertos de salida × fechas)
PAUSA_RYANAIR_S = (6.0, 12.0)  # entre una petición a Ryanair y la siguiente, sin prisas


def es_cualquiera(b: dict) -> bool:
    return bool(b.get("cualquier_destino"))


def para_destino(b: dict, op: Opcion) -> dict:
    """La búsqueda con un destino concreto y las fechas de su tarifa (para comprobarla con tus filtros)."""
    return {
        **b, "destino": op.ida.destino, "cualquier_destino": False, "destinos_extra": [], "fechas_extra": [],
        "tramos_viaje": [], "modo": "fechas", "flex_dias": 0, "fecha_ida": op.ida.fecha.isoformat(),
        "fecha_vuelta": op.vuelta.fecha.isoformat() if op.vuelta else None,
    }


def por_fechas(b: dict) -> list[dict]:
    """La búsqueda con cada una de sus fechas (las principales y las alternativas); con chollo, el periodo entero."""
    pares = viaje.pares_fechas(b)
    if not pares:
        return [b]
    return [{**b, "fecha_ida": fi.isoformat(), "fecha_vuelta": fv.isoformat() if fv else None, "fechas_extra": []}
            for fi, fv in pares]


def candidatos(b: dict, ryanair) -> list[Opcion]:
    """La tarifa más barata de Ryanair a cada destino (sin los países excluidos), de más barata a más cara;
    con varias fechas, la de la fecha más barata para cada destino."""
    excluidos = set(b.get("paises_excluidos") or [])
    origenes, _ = aeropuertos_busqueda(b)
    mejores: dict[str, Opcion] = {}
    peticiones = [(bf, origen) for bf in por_fechas(b) for origen in origenes][:MAX_RYANAIR]
    for i, (bf, origen) in enumerate(peticiones):
        if i:
            time.sleep(random.uniform(*PAUSA_RYANAIR_S))
        for op in ryanair.cualquier_destino(bf, origen):
            destino = op.ida.destino
            if destino in origenes or aeropuertos.pais(destino) in excluidos:
                continue
            if destino not in mejores or op.precio_billetes < mejores[destino].precio_billetes:
                mejores[destino] = op
    return sorted(mejores.values(), key=lambda o: o.precio_billetes)


def revisar(b: dict, google, ryanair, aerolineas: dict, perfil: dict | None,
            cupo_google: int) -> tuple[list[Opcion], Counter, list[str], int, str | None]:
    """Top de destinos con tus filtros. Devuelve (mejor opción de cada destino, de más barata a más cara;
    descartes; errores; consultas a Google gastadas; motivo si Google ha frenado al robot)."""
    rechazos: Counter = Counter()
    errores: list[str] = []
    if ryanair is None:
        return [], rechazos, ["Ryanair no está disponible ahora mismo"], 0, None
    try:
        lista = candidatos(b, ryanair)
    except FuenteBloqueada as e:
        return [], rechazos, [str(e)], 0, None
    if not lista:
        return [], rechazos, [], 0, None
    gastadas, bloqueo, resultado = 0, None, []
    for op in lista[:CANDIDATOS]:
        b2 = para_destino(b, op)
        por_fuente = {"ryanair": ResultadoFuente(opciones=[op])}
        if google is not None and not bloqueo and cupo_google - gastadas >= CONSULTAS_POR_CANDIDATO:
            try:
                r = google.buscar(b2, Validador(b2, aerolineas))
                gastadas += r.peticiones
                por_fuente["google_flights"] = r
            except FuenteBloqueada as e:
                bloqueo = str(e)  # el resto, solo con Ryanair; la ronda marca a Google como frenado
            except Exception as e:  # un destino que falla no estropea los demás
                log.warning("Cualquier destino: Google falló con un destino: %s", type(e).__name__)
        validas, descartes, _ = evaluar(b2, por_fuente, perfil, aerolineas)
        rechazos.update(descartes)
        if validas:
            resultado.append(validas[0])
    resultado.sort(key=lambda o: o.precio_total)
    return resultado[:TOP], rechazos, errores, gastadas, bloqueo


def resumen_top(opciones: list[Opcion]) -> list[dict]:
    """Lo que la web enseña del top (sin tener que leer las opciones guardadas)."""
    top = []
    for op in opciones:
        destino = op.ida.destino
        top.append({
            "destino": destino, "nombre": aeropuertos.nombre(destino), "pais": aeropuertos.pais(destino),
            "precio_total": op.precio_total, "fecha_ida": op.ida.fecha.isoformat(),
            "fecha_vuelta": op.vuelta.fecha.isoformat() if op.vuelta else None,
            "escalas": max(tr.escalas for tr in op.trayectos), "aerolineas": sorted({t.aerolinea for t in op.tramos}),
        })
    return top
