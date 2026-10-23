"""Forma del viaje de una búsqueda: unas fechas (más otras alternativas) o un viaje con varios destinos."""

from __future__ import annotations

from datetime import date, timedelta

MAX_FECHAS_EXTRA = 5  # fechas alternativas de un mismo viaje (además de las principales)
MAX_TRAMOS = 5  # vuelos de un viaje con varios destinos


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def tramos_viaje(b: dict) -> list[tuple[str, str, date]]:
    """Vuelos de un viaje con varios destinos (Sevilla → Cracovia → Zúrich → Sevilla), en orden."""
    tramos = []
    for t in (b.get("tramos_viaje") or [])[:MAX_TRAMOS]:
        f = _fecha(t.get("fecha"))
        if f and t.get("origen") and t.get("destino"):
            tramos.append((str(t["origen"]).upper(), str(t["destino"]).upper(), f))
    return tramos if len(tramos) >= 2 else []


def es_varios_destinos(b: dict) -> bool:
    return b.get("modo") == "fechas" and bool(tramos_viaje(b))


def pares_fechas(b: dict) -> list[tuple[date, date | None]]:
    """Fechas de ida (y de vuelta) que se vigilan: las principales y las alternativas, sin repetir."""
    if b.get("modo") != "fechas" or es_varios_destinos(b):
        return []
    ida_vuelta = bool(b.get("ida_vuelta"))
    candidatas = [{"ida": b.get("fecha_ida"), "vuelta": b.get("fecha_vuelta")}]
    candidatas += (b.get("fechas_extra") or [])[:MAX_FECHAS_EXTRA]
    pares: list[tuple[date, date | None]] = []
    for p in candidatas:
        fi = _fecha(p.get("ida"))
        fv = _fecha(p.get("vuelta")) if ida_vuelta else None
        if fi and (not ida_vuelta or (fv and fv >= fi)) and (fi, fv) not in pares:
            pares.append((fi, fv))
    return pares


def salidas(b: dict) -> list[date]:
    """Todas las fechas en que podrías empezar el viaje."""
    if es_varios_destinos(b):
        return [tramos_viaje(b)[0][2]]
    if b.get("modo") == "fechas":
        return [fi for fi, _ in pares_fechas(b)] or [f for f in [_fecha(b.get("fecha_ida"))] if f]
    return [f for f in [_fecha(b.get("chollo_desde"))] if f]


def primera_salida(b: dict, hoy: date) -> date:
    """La salida más cercana que aún no ha pasado (o la última, si ya pasaron todas)."""
    fechas = sorted(salidas(b))
    futuras = [f for f in fechas if f >= hoy]
    return futuras[0] if futuras else fechas[-1]


def _par(fi: date, fv: date | None) -> dict:
    return {"ida": fi.isoformat(), **({"vuelta": fv.isoformat()} if fv else {})}


def caducidad(b: dict, hoy: date) -> tuple[bool, dict]:
    """Lo que ya ha pasado de una búsqueda: (borrarla, cambios para quitar lo pasado).

    Unas fechas caducan el día en que empieza el viaje (con margen de días, el último en que se podría
    salir): se quitan y, si no queda ninguna, se borra la búsqueda. Un viaje con varios destinos, cuando
    sale el primer vuelo. Un chollo, cuando ya no cabe ninguna salida (con la estancia mínima), y mientras
    tanto el periodo empieza siempre mañana.
    """
    if es_varios_destinos(b):
        return tramos_viaje(b)[0][2] <= hoy, {}
    if b.get("modo") == "fechas":
        pares = pares_fechas(b)
        if not pares:
            return False, {}  # fechas sin completar: no se toca
        margen = timedelta(days=b.get("flex_dias") or 0)
        vivos = [(fi, fv) for fi, fv in pares if fi + margen > hoy]
        if not vivos:
            return True, {}
        if len(vivos) == len(pares):
            return False, {}
        principal = pares[0] if pares[0] in vivos else min(vivos)
        return False, {
            "fecha_ida": principal[0].isoformat(),
            "fecha_vuelta": principal[1].isoformat() if principal[1] else None,
            "fechas_extra": [_par(fi, fv) for fi, fv in vivos if (fi, fv) != principal],
        }
    desde, hasta = _fecha(b.get("chollo_desde")), _fecha(b.get("chollo_hasta"))
    if not desde or not hasta:
        return False, {}
    estancia = (b.get("noches_min") or 0) if b.get("ida_vuelta") else 0
    if hasta - timedelta(days=estancia) <= hoy:
        return True, {}
    return False, ({"chollo_desde": (hoy + timedelta(days=1)).isoformat()} if desde <= hoy else {})


def ruta_viaje(b: dict) -> list[str]:
    """Aeropuertos por los que pasa un viaje con varios destinos: SVQ, KRK, ZRH, SVQ."""
    tramos = tramos_viaje(b)
    return [tramos[0][0]] + [d for _, d, _ in tramos] if tramos else []
