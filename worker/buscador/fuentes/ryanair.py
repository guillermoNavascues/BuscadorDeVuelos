"""Ryanair (web oficial): buscador de tarifas más baratas de ryanair.com.

Sus condiciones de uso permiten el uso privado y no comercial; solo prohíben extraer
datos con fines comerciales. Cada búsqueda usa un cliente HTTP nuevo, sin cookies
(navegación privada). Precios por pasajero, sin maletas.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import httpx

from .. import filtros
from ..tiempo import hoy
from ..modelos import FuenteBloqueada, Opcion, ResultadoFuente, Tramo, Trayecto

log = logging.getLogger(__name__)

URL = "https://services-api.ryanair.com/farfnd/v4"
CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
}
TASA_BEBE_POR_VUELO = 25.0  # tarifa fija de Ryanair por bebé en el regazo y vuelo
NOTA = "Precio del buscador de tarifas de Ryanair (se actualiza cada pocas horas): confírmalo en ryanair.com."


def _hora(h: int, fin: bool) -> str:
    return "23:59" if fin and h >= 24 else f"{min(h, 23):02d}:00"


def _tramo(datos: dict) -> Tramo:
    numero = datos["flightNumber"]
    return Tramo(
        aerolinea=numero[:2],
        numero=numero[2:],
        origen=datos["departureAirport"]["iataCode"],
        destino=datos["arrivalAirport"]["iataCode"],
        salida=datetime.fromisoformat(datos["departureDate"]),
        llegada=datetime.fromisoformat(datos["arrivalDate"]),
    )


class Ryanair:
    nombre = "ryanair"

    def __init__(self):
        self.peticiones = 0

    def _get(self, ruta: str, params: dict) -> dict:
        self.peticiones += 1
        # Cliente nuevo en cada petición: sin cookies ni sesión previa
        with httpx.Client(headers=CABECERAS, timeout=30, follow_redirects=False) as http:
            r = http.get(f"{URL}/{ruta}", params=params)
        if r.status_code in (403, 409, 429) or "captcha" in r.text[:2000].lower():
            raise FuenteBloqueada(f"Ryanair ha rechazado la petición (HTTP {r.status_code})")
        if r.status_code == 404:
            return {"fares": []}
        r.raise_for_status()
        return r.json()

    def _consulta(self, b: dict, origen: str, destino: str | None) -> dict | None:
        """Tarifas de Ryanair para tus fechas (o tu periodo de chollo); sin destino, a todos sus destinos."""
        if b["modo"] == "fechas":
            fi = date.fromisoformat(str(b["fecha_ida"]))
            flex = b.get("flex_dias") or 0
            ida_desde, ida_hasta = fi - timedelta(days=flex), fi + timedelta(days=flex)
            if b.get("ida_vuelta"):
                noches_min = noches_max = (date.fromisoformat(str(b["fecha_vuelta"])) - fi).days
        else:
            ida_desde = date.fromisoformat(str(b["chollo_desde"]))
            ida_hasta = date.fromisoformat(str(b["chollo_hasta"]))
            noches_min, noches_max = b.get("noches_min"), b.get("noches_max")
        ida_desde = max(ida_desde, hoy() + timedelta(days=1))
        if ida_hasta < ida_desde:
            return None

        sal_min, sal_max, _, _ = filtros.franja(b, "ida")
        params = {
            "departureAirportIataCode": origen,
            "outboundDepartureDateFrom": ida_desde.isoformat(),
            "outboundDepartureDateTo": ida_hasta.isoformat(),
            "outboundDepartureTimeFrom": _hora(sal_min, False),
            "outboundDepartureTimeTo": _hora(sal_max, True),
            "currency": "EUR",
            "market": "es-es",
        }
        if destino:
            params.update(arrivalAirportIataCode=destino, limit=10)
        if b.get("ida_vuelta"):
            vsal_min, vsal_max, _, _ = filtros.franja(b, "vuelta")
            params.update({
                "inboundDepartureDateFrom": (ida_desde + timedelta(days=noches_min)).isoformat(),
                "inboundDepartureDateTo": (ida_hasta + timedelta(days=noches_max)).isoformat(),
                "inboundDepartureTimeFrom": _hora(vsal_min, False),
                "inboundDepartureTimeTo": _hora(vsal_max, True),
                "durationFrom": noches_min,
                "durationTo": noches_max,
            })
            return self._get("roundTripFares", params)
        return self._get("oneWayFares", params)

    def buscar(self, b: dict, validador: filtros.Validador) -> ResultadoFuente:
        res = ResultadoFuente()
        datos = self._consulta(b, b["origen"], b["destino"])
        if datos is None:
            return res
        res.peticiones = 1
        res.opciones = self._opciones(b, datos)
        return res

    def cualquier_destino(self, b: dict, origen: str) -> list[Opcion]:
        """La tarifa más barata a cada destino de Ryanair desde un aeropuerto (una sola petición)."""
        datos = self._consulta(b, origen, None)
        return self._opciones(b, datos) if datos else []

    def _opciones(self, b: dict, datos: dict) -> list[Opcion]:
        opciones: list[Opcion] = []
        pasajeros = (b.get("adultos") or 1) + (b.get("ninos") or 0)
        bebes = b.get("bebes") or 0
        for tarifa in datos.get("fares", []):
            try:
                ida = Trayecto([_tramo(tarifa["outbound"])])
                vuelta = Trayecto([_tramo(tarifa["inbound"])]) if tarifa.get("inbound") else None
                por_persona = tarifa["outbound"]["price"]["value"] + (
                    tarifa["inbound"]["price"]["value"] if vuelta else 0
                )
            except (KeyError, TypeError, ValueError) as e:
                log.warning("Tarifa de Ryanair con formato inesperado: %s", e)
                continue
            vuelos = 2 if vuelta else 1
            opciones.append(
                Opcion(
                    fuente=self.nombre,
                    ida=ida,
                    vuelta=vuelta,
                    precio_billetes=round(por_persona * pasajeros + bebes * TASA_BEBE_POR_VUELO * vuelos, 2),
                    notas=[NOTA],
                )
            )
        return opciones
