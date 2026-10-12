"""Google Flights (fuente principal): compara casi todas las aerolíneas a la vez.

Cada consulta es una petición HTTP independiente, sin cookies ni sesión guardada
(equivalente a navegación privada). El ritmo lo marca estado_fuentes: pausas aleatorias
entre peticiones y como máximo una petición cada `pausa_min` segundos.
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from datetime import date, timedelta

# Como mucho 30 s por página (la librería espera 60 por defecto y reintenta varias veces).
# Tiene que fijarse antes de importar fli, que lo lee al cargarse.
os.environ.setdefault("FLI_TIMEOUT", "30")

from fli.models import (
    Airline,
    Airport,
    DateSearchFilters,
    FlightSearchFilters,
    FlightSegment,
    LayoverRestrictions,
    MaxStops,
    PassengerInfo,
    SeatType,
    SortBy,
    TimeRestrictions,
    TripType,
)
from fli.search import SearchDates, SearchFlights
from fli.search._concurrency import TokenBucketRateLimiter
from fli.search.client import get_client

from .. import filtros, viaje
from ..tiempo import hoy
from ..modelos import ErrorExplicado, FuenteBloqueada, Opcion, PrecioCalendario, ResultadoFuente, Tramo, Trayecto

log = logging.getLogger(__name__)

LOCALE = {"currency": "EUR", "language": "es", "country": "ES"}
ESCALAS = {0: MaxStops.NON_STOP, 1: MaxStops.ONE_STOP_OR_FEWER, 2: MaxStops.TWO_OR_FEWER_STOPS}
MAX_DIAS_FUTURO = 300  # Google no busca más allá de ~305 días
FECHAS_CHOLLO_POR_RONDA = 8  # páginas de calendario por búsqueda chollo y ronda
PROPORCION_AUREA = 0.6180339887498949


def _codigo(aerolinea) -> str:
    return aerolinea.name.removeprefix("_")


def _a_trayecto(resultado) -> Trayecto:
    return Trayecto(
        [
            Tramo(
                aerolinea=_codigo(l.airline),
                numero=str(l.flight_number),
                origen=l.departure_airport.name,
                destino=l.arrival_airport.name,
                salida=l.departure_datetime,
                llegada=l.arrival_datetime,
                operadora=_codigo(l.operating_airline) if l.operating_airline else None,
            )
            for l in resultado.legs
        ]
    )


PATRON_BLOQUEO = r"\b(403|429)\b"  # código HTTP suelto, no dentro de otro número


def _es_bloqueo(error: Exception) -> bool:
    """Error HTTP 403/429 o mensaje de tráfico inusual (sin confundir otros números del texto)."""
    texto = str(error).lower()
    return bool(re.search(PATRON_BLOQUEO, texto)) or any(
        s in texto for s in ("unusual traffic", "too many requests", "forbidden")
    )


# Google a veces responde con una página sin vuelos (la librería ya lo reintenta 3 veces). Solo es un bloqueo
# si pasa en 3 consultas seguidas de al menos 2 búsquedas distintas: si siempre falla la misma, el problema es
# de esa búsqueda (se marca y las demás siguen). Visto el 12/10/2026: una sola búsqueda paraba al robot entero.
SIN_DATOS_SEGUIDOS_BLOQUEO = 3
SIN_DATOS_BUSQUEDAS_DISTINTAS = 2


class SinResultados(ErrorExplicado):
    """Google no ha devuelto su página de resultados (ni vuelos ni error claro)."""


def explicar_sin_datos(respuestas: list[str]) -> str:
    if any(r.startswith("página de consentimiento") for r in respuestas):
        return "Google ha enseñado su aviso de cookies en vez de los vuelos (se reintenta en unos minutos)"
    return "Google ha devuelto una página sin vuelos; suele ser un fallo puntual suyo (se reintenta en unos minutos)"


def describir_respuesta(estado: int, cuerpo: str) -> str:
    """Clasifica una respuesta de Google sin copiar su contenido (puede llevar datos de la búsqueda)."""
    inicio = cuerpo[:5000].lower()
    if estado == 429 or "unusual traffic" in inicio or "/sorry/" in inicio:
        return f"bloqueo (HTTP {estado})"
    if "af_initdatacallback" in cuerpo[:200000].lower() or "ds:1" in cuerpo:
        return f"página de resultados (HTTP {estado})"
    if "consent.google" in inicio or "before you continue" in inicio or "antes de ir a google" in inicio:
        return f"página de consentimiento de cookies (HTTP {estado})"
    if cuerpo.lstrip().startswith(")]}'"):
        if "ErrorResponse" in cuerpo[:2000]:
            return f"error 13 de Google: forma de consulta antigua rechazada (HTTP {estado})"
        return f"datos (HTTP {estado}, {len(cuerpo)} bytes)"
    if "<html" in inicio:
        return f"página sin datos de vuelos (HTTP {estado}, {len(cuerpo)} bytes)"
    return f"respuesta desconocida (HTTP {estado}, {len(cuerpo)} bytes)"


class GoogleFlights:
    nombre = "google_flights"

    def __init__(self, pausa_min_s: float, pausa_max_s: float, codigos_permitidos: set[str]):
        self.pausa = (pausa_min_s, pausa_max_s)
        # Nunca más de una petición cada pausa_min segundos (también en las internas de la librería)
        get_client()._rate_limiter = TokenBucketRateLimiter(calls=1, period=float(pausa_min_s))
        self.incluir = [a for c in sorted(codigos_permitidos) if (a := self._aerolinea(c))]
        self._primera = True
        self.respuestas: list[str] = []  # clasificación de cada respuesta de Google (diagnóstico)
        self._sin_datos: list[str] = []  # búsqueda de cada consulta seguida que vuelve sin datos
        self._busqueda = ""
        self._vigilar_respuestas()

    def _vigilar_respuestas(self) -> None:
        """Anota qué tipo de respuesta da Google: la librería devuelve 0 vuelos sin avisar si no es la normal."""
        cliente = get_client()
        for metodo in ("get", "post"):
            original = getattr(type(cliente), metodo)

            def vigilado(cliente_, *args, _original=original, **kwargs):
                r = _original(cliente_, *args, **kwargs)
                self.respuestas.append(describir_respuesta(r.status_code, r.text))
                return r

            setattr(cliente, metodo, vigilado.__get__(cliente))

    @property
    def peticiones(self) -> int:
        """Peticiones HTTP reales hechas a Google (cada respuesta recibida)."""
        return len(self.respuestas)

    @staticmethod
    def _aerolinea(codigo: str):
        for nombre in (codigo, "_" + codigo):
            if nombre in Airline.__members__:
                return Airline[nombre]
        return None

    def _pausa(self) -> None:
        if not self._primera:
            time.sleep(random.uniform(*self.pausa))
        self._primera = False

    def _llamar(self, funcion, *args, **kwargs):
        self._pausa()
        antes = len(self.respuestas)
        try:
            resultado = funcion(*args, **kwargs, **LOCALE)
        except Exception as e:  # la librería lanza excepciones genéricas
            vistas = self.respuestas[antes:]
            if _es_bloqueo(e) or any(r.startswith("bloqueo") for r in vistas):
                raise FuenteBloqueada(f"Google Flights ha limitado las peticiones: {e}") from e
            if type(e).__name__ == "SearchParseError":  # ninguna página con datos, tras los reintentos
                self._sin_datos.append(self._busqueda)
                if (len(self._sin_datos) >= SIN_DATOS_SEGUIDOS_BLOQUEO
                        and len(set(self._sin_datos)) >= SIN_DATOS_BUSQUEDAS_DISTINTAS):
                    raise FuenteBloqueada("Google devuelve páginas sin vuelos una y otra vez: "
                                          "el robot hace una pausa antes de volver a intentarlo") from e
                raise SinResultados(explicar_sin_datos(vistas)) from e
            raise
        self._sin_datos = []
        return resultado

    # ------------------------------------------------------------------
    # Construcción de filtros
    # ------------------------------------------------------------------
    @staticmethod
    def _aeropuerto(codigo: str):
        if codigo not in Airport.__members__:
            raise ValueError(f"Google Flights no reconoce el aeropuerto {codigo}")
        return Airport[codigo]

    @staticmethod
    def _tiene_franjas(b: dict) -> bool:
        sentidos = ("ida", "vuelta") if b.get("ida_vuelta") else ("ida",)
        return any(filtros.franja(b, s) != (0, 24, 0, 24) for s in sentidos)

    def _segmento(self, b: dict, sentido: str, fecha: date, con_horas: bool = True) -> FlightSegment:
        origenes, destinos = filtros.aeropuertos_busqueda(b)
        o, d = (origenes, destinos) if sentido == "ida" else (destinos, origenes)
        return self._segmento_ruta(o, d, fecha, filtros.franja(b, sentido) if con_horas else (0, 24, 0, 24))

    def _segmento_ruta(self, o: list[str], d: list[str], fecha: date, horas_franja: tuple) -> FlightSegment:
        sal_min, sal_max, lle_min, lle_max = horas_franja
        horas = TimeRestrictions(
            earliest_departure=sal_min or None,
            latest_departure=sal_max if sal_max < 24 else None,
            earliest_arrival=lle_min or None,
            latest_arrival=lle_max if lle_max < 24 else None,
        )
        tiene_horas = any(v is not None for v in horas.model_dump().values())
        return FlightSegment(
            # Google busca desde (y hasta) todos tus aeropuertos a la vez, con una sola petición
            departure_airport=[[self._aeropuerto(c), 0] for c in o],
            arrival_airport=[[self._aeropuerto(c), 0] for c in d],
            travel_date=fecha.isoformat(),
            time_restrictions=horas if tiene_horas else None,
        )

    def _comunes(self, b: dict) -> dict:
        return {
            "passenger_info": PassengerInfo(
                adults=b.get("adultos") or 1, children=b.get("ninos") or 0, infants_on_lap=b.get("bebes") or 0
            ),
            "stops": ESCALAS.get(b.get("escalas_max", 1), MaxStops.ANY),
            "seat_type": SeatType.ECONOMY,
            "layover_restrictions": LayoverRestrictions(max_duration=(b.get("escala_max_horas") or 6) * 60),
            "airlines": self.incluir or None,
        }

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def calendario(self, b: dict, desde: date, hasta: date, noches: int | None) -> list[PrecioCalendario]:
        """Precio más barato (solo billetes) de cada fecha del rango, con una o pocas peticiones."""
        manana = hoy() + timedelta(days=1)
        desde = max(desde, manana)
        hasta = min(hasta, hoy() + timedelta(days=MAX_DIAS_FUTURO))
        if hasta < desde:
            return []
        # Sin franjas horarias: con ellas el calendario de Google devuelve un solo día (como con la
        # escala). Es solo una referencia de precios; los horarios se filtran en las búsquedas de vuelos.
        segmentos = [self._segmento(b, "ida", desde, con_horas=False)]
        if noches:
            segmentos.append(self._segmento(b, "vuelta", desde + timedelta(days=noches), con_horas=False))
        comunes = self._comunes(b)
        # Con límite de duración de escala, el calendario de Google devuelve un solo día (probado
        # el 6/10/2026). El calendario es solo una referencia de precios: la escala se filtra después.
        comunes.pop("layover_restrictions")
        filtros_fechas = DateSearchFilters(
            trip_type=TripType.ROUND_TRIP if noches else TripType.ONE_WAY,
            flight_segments=segmentos,
            from_date=desde.isoformat(),
            to_date=hasta.isoformat(),
            duration=noches,
            **comunes,
        )
        res = self._llamar(SearchDates().search, filtros_fechas) or []
        return [
            PrecioCalendario(r.date[0].date(), r.date[1].date() if len(r.date) > 1 else None, float(r.price))
            for r in res
            if r.price
        ]

    def _solo_ida(self, b: dict, sentido: str, fecha: date, con_horas: bool = True) -> list:
        f = FlightSearchFilters(
            trip_type=TripType.ONE_WAY,
            flight_segments=[self._segmento(b, sentido, fecha, con_horas)],
            sort_by=SortBy.CHEAPEST,
            **self._comunes(b),
        )
        return self._llamar(SearchFlights().search, f) or []

    def _solo_ida_ruta(self, b: dict, origen: str, destino: str, fecha: date, horas_franja: tuple) -> list:
        f = FlightSearchFilters(
            trip_type=TripType.ONE_WAY,
            flight_segments=[self._segmento_ruta([origen], [destino], fecha, horas_franja)],
            sort_by=SortBy.CHEAPEST,
            **self._comunes(b),
        )
        return self._llamar(SearchFlights().search, f) or []

    def varios_destinos(self, b: dict, validador: filtros.Validador) -> list[Opcion]:
        """Viaje con varios destinos (Sevilla → Cracovia → Zúrich → Sevilla): cada vuelo es un billete
        de solo ida y se suman los más baratos que encajan en orden. (La página de resultados de Google
        no sirve búsquedas de varios destinos juntos.)"""
        tramos = viaje.tramos_viaje(b)
        if not tramos or tramos[0][2] < hoy():
            return []
        horas = filtros.franja(b, "ida")
        candidatos: list[list[tuple[float, Trayecto]]] = []
        for i, (origen, destino, fecha) in enumerate(tramos, 1):
            validos: list[tuple[float, Trayecto]] = []
            # Si con tu horario Google no devuelve nada, se repite sin él y lo filtra el robot
            for franja_busqueda in dict.fromkeys([horas, (0, 24, 0, 24)]):
                for r in self._solo_ida_ruta(b, origen, destino, fecha, franja_busqueda):
                    if r.price is None or r.self_transfer:
                        continue
                    tr = _a_trayecto(r)
                    if validador.tramo(tr, origen, destino, i) is None:
                        validos.append((float(r.price), tr))
                if validos:
                    break
            if not validos:
                return []
            candidatos.append(sorted(validos, key=lambda x: x[0]))
        opciones: list[Opcion] = []
        vistas: set = set()
        for inicio in candidatos[0][:3]:  # las 3 primeras idas más baratas, cada una con lo más barato que encaje
            elegidos = [inicio]
            for lista in candidatos[1:]:
                siguiente = next((c for c in lista if c[1].salida > elegidos[-1][1].llegada), None)
                if siguiente is None:
                    break
                elegidos.append(siguiente)
            clave = tuple(id(tr) for _, tr in elegidos)
            if len(elegidos) == len(candidatos) and clave not in vistas:
                vistas.add(clave)
                trayectos = [tr for _, tr in elegidos]
                opciones.append(Opcion(fuente=self.nombre, ida=trayectos[0], vuelta=None, siguientes=trayectos[1:],
                                       precio_billetes=sum(p for p, _ in elegidos), billetes_separados=True))
        return opciones

    def _ida_y_vuelta(self, b: dict, fecha_ida: date, fecha_vuelta: date, con_horas: bool = True, top_n: int = 2) -> list[Opcion]:
        f = FlightSearchFilters(
            trip_type=TripType.ROUND_TRIP,
            flight_segments=[
                self._segmento(b, "ida", fecha_ida, con_horas), self._segmento(b, "vuelta", fecha_vuelta, con_horas)
            ],
            sort_by=SortBy.CHEAPEST,
            **self._comunes(b),
        )
        opciones: list[Opcion] = []
        # top_n=2: se piden las vueltas de las 2 idas más baratas (3 peticiones)
        for combo in self._llamar(SearchFlights().search, f, top_n=top_n) or []:
            ida, vuelta = combo[0], combo[-1]
            if vuelta.price is None or ida.self_transfer or vuelta.self_transfer:
                continue
            tr_ida, tr_vuelta = _a_trayecto(ida), _a_trayecto(vuelta)
            aerolineas_ida = {t.aerolinea for t in tr_ida.tramos}
            aerolineas_vuelta = {t.aerolinea for t in tr_vuelta.tramos}
            opciones.append(
                Opcion(
                    fuente=self.nombre,
                    ida=tr_ida,
                    vuelta=tr_vuelta,
                    precio_billetes=float(vuelta.price),
                    # Si no comparten aerolínea, Google lo vende como dos billetes
                    billetes_separados=not (aerolineas_ida & aerolineas_vuelta),
                )
            )
        return opciones

    def vuelos(self, b: dict, fecha_ida: date, fecha_vuelta: date | None, validador: filtros.Validador) -> list[Opcion]:
        """Opciones concretas para unas fechas: ida y vuelta juntas y, además, dos billetes de solo ida."""
        opciones: list[Opcion] = []
        if fecha_vuelta:
            opciones += self._ida_y_vuelta(b, fecha_ida, fecha_vuelta)

        # Billetes de solo ida (y vuelta por separado): en low cost suele salir más barato
        validos: dict[str, list[tuple[float, object]]] = {}
        for sentido, fecha in (("ida", fecha_ida), ("vuelta", fecha_vuelta)):
            if fecha is None:
                continue
            validos[sentido] = []
            for r in self._solo_ida(b, sentido, fecha):
                if r.price is None or r.self_transfer:
                    continue
                tr = _a_trayecto(r)
                if validador.sentido(tr, sentido) is None:
                    validos[sentido].append((float(r.price), tr))
        idas, vueltas = validos.get("ida", []), validos.get("vuelta")
        if idas and fecha_vuelta is None:
            precio, tr = min(idas, key=lambda x: x[0])
            opciones.append(Opcion(fuente=self.nombre, ida=tr, vuelta=None, precio_billetes=precio))
        elif idas and vueltas:
            # Con varios aeropuertos de salida: lo más barato volviendo al mismo del que sales (para cada uno)
            # y, si sale más barato, volviendo a otro (la web y el aviso lo indican)
            pares = []
            for salida in dict.fromkeys(tr.origen for _, tr in idas):
                ida_aqui = [x for x in idas if x[1].origen == salida]
                vuelta_aqui = [x for x in vueltas if x[1].destino == salida]
                if vuelta_aqui:
                    pares.append((min(ida_aqui, key=lambda x: x[0]), min(vuelta_aqui, key=lambda x: x[0])))
            pares.append((min(idas, key=lambda x: x[0]), min(vueltas, key=lambda x: x[0])))
            vistos = set()
            for (precio_ida, tr_ida), (precio_vuelta, tr_vuelta) in pares:
                if (id(tr_ida), id(tr_vuelta)) in vistos:
                    continue
                vistos.add((id(tr_ida), id(tr_vuelta)))
                opciones.append(Opcion(fuente=self.nombre, ida=tr_ida, vuelta=tr_vuelta,
                                       precio_billetes=precio_ida + precio_vuelta, billetes_separados=True))

        if not opciones and self._tiene_franjas(b):
            # Google filtra por horario y devuelve una lista vacía sin más. Se repite sin franjas y el
            # robot aplica tus horarios: así puede decirte cuántos vuelos hay fuera de ellos (y no se
            # pierde ninguno si Google interpreta los límites de hora de forma más estricta).
            if fecha_vuelta:
                opciones += self._ida_y_vuelta(b, fecha_ida, fecha_vuelta, con_horas=False, top_n=1)
            else:
                for r in self._solo_ida(b, "ida", fecha_ida, con_horas=False):
                    if r.price is not None and not r.self_transfer:
                        opciones.append(Opcion(fuente=self.nombre, ida=_a_trayecto(r), vuelta=None,
                                               precio_billetes=float(r.price)))
        return opciones

    # ------------------------------------------------------------------
    # Punto de entrada por búsqueda
    # ------------------------------------------------------------------
    @staticmethod
    def nueva_sesion_privada() -> None:
        """Descarta la sesión HTTP anterior (y sus cookies): cada búsqueda empieza de cero."""
        get_client()._sessions = threading.local()

    @staticmethod
    def _muestras_chollo(b: dict) -> list[tuple[date, int | None]]:
        """Fechas del periodo del chollo que se miran en esta ronda.

        Desde agosto de 2026 cada fecha del calendario cuesta una página entera de Google (~2 MB),
        así que no se pide el periodo completo: cada ronda mira unas pocas fechas repartidas y la
        siguiente desplaza la selección (info.chollo_turno), hasta cubrirlo todo en pocos días.
        """
        manana = hoy() + timedelta(days=1)
        desde = max(date.fromisoformat(str(b["chollo_desde"])), manana)
        hasta = min(date.fromisoformat(str(b["chollo_hasta"])), hoy() + timedelta(days=MAX_DIAS_FUTURO))
        noches_posibles = [None]
        if b.get("ida_vuelta"):
            n_min, n_max = b["noches_min"], b["noches_max"]
            noches_posibles = sorted({n_min, (n_min + n_max) // 2, n_max})
        # Fechas de salida posibles (con ida y vuelta, que quepa al menos la estancia mínima)
        fechas = [
            desde + timedelta(days=i)
            for i in range((hasta - desde).days + 1)
            if noches_posibles[0] is None or desde + timedelta(days=i + noches_posibles[0]) <= hasta
        ]
        if not fechas:
            return []
        # Secuencia de Weyl (proporción áurea): reparte las fechas por todo el periodo y por todos
        # los días de la semana, y cada ronda continúa donde lo dejó la anterior. Un salto fijo
        # (p. ej. de 7 días) caería siempre en el mismo día de la semana, y si la aerolínea no
        # vuela ese día no se vería nunca ningún precio.
        # Además, cada fecha se mueve como mucho 3 días para caer en un día de la semana distinto
        # de las demás: así, de 8 fechas, 7 son de días distintos aunque la ruta no se vuele a diario.
        turno = int((b.get("info") or {}).get("chollo_turno", 0))
        elegidas: set[int] = set()
        for i in range(FECHAS_CHOLLO_POR_RONDA):
            k = turno * FECHAS_CHOLLO_POR_RONDA + i
            base = int(((k * PROPORCION_AUREA) % 1) * len(fechas))
            dia_semana = k % 7
            for desplazamiento in (0, 1, -1, 2, -2, 3, -3):
                j = base + desplazamiento
                if 0 <= j < len(fechas) and fechas[j].weekday() == dia_semana:
                    base = j
                    break
            elegidas.add(base)
        elegidas = sorted(elegidas)
        muestras = []
        for j, k in enumerate(elegidas):
            fi = fechas[k]
            # La duración de la estancia también va rotando entre la mínima, la media y la máxima
            caben = [n for n in noches_posibles if n is None or fi + timedelta(days=n) <= hasta]
            muestras.append((fi, caben[(turno + j) % len(caben)]))
        return muestras

    def buscar(self, b: dict, validador: filtros.Validador) -> ResultadoFuente:
        self.nueva_sesion_privada()
        self._busqueda = str(b.get("id", ""))
        primera_respuesta = len(self.respuestas)
        res = ResultadoFuente()
        varios = viaje.es_varios_destinos(b)
        pares: list[tuple[date, date | None]] = []
        if varios:
            res.opciones += self.varios_destinos(b, validador)
        elif b["modo"] == "fechas":
            flex = b.get("flex_dias") or 0
            base = viaje.pares_fechas(b)  # las fechas principales y las alternativas
            for fi, fv in base:
                noches = (fv - fi).days if fv else None
                if not flex or noches == 0:
                    pares.append((fi, fv))
                    continue
                # Con margen de días se mira el calendario (una página por día) para elegir las más baratas
                cal: list[PrecioCalendario] = []
                try:
                    cal = self.calendario(b, fi - timedelta(days=flex), fi + timedelta(days=flex), noches)
                except FuenteBloqueada:
                    raise
                except Exception as e:  # sin calendario se buscan las fechas pedidas
                    log.warning("Calendario no disponible: %s", type(e).__name__)
                res.calendario += cal
                mas_baratas = sorted(cal, key=lambda c: c.precio)[: 2 if len(base) == 1 else 1]
                pares += [(c.fecha_ida, c.fecha_vuelta) for c in mas_baratas] or [(fi, fv)]
            pares = list(dict.fromkeys(pares))
        else:
            fallidas = seguidas = 0
            muestras = self._muestras_chollo(b)
            for fi, noches in muestras:
                try:
                    res.calendario += self.calendario(b, fi, fi, noches)
                    seguidas = 0
                except FuenteBloqueada:
                    raise
                except Exception as e:  # una fecha que falla no estropea las demás
                    fallidas += 1
                    seguidas += 1
                    log.warning("Fecha del chollo sin precio: %s", type(e).__name__)
                    if isinstance(e, SinResultados) and seguidas >= 2:
                        break  # dos páginas vacías seguidas: no se gastan más consultas en esta búsqueda
            if muestras and fallidas and not res.calendario:
                res.error = f"No se pudo consultar ninguna fecha del calendario ({fallidas} intentos sin datos)"
            # Lo más barato entre lo visto ahora y lo acumulado en rondas anteriores
            vistos = {(c.fecha_ida, c.fecha_vuelta): c.precio for c in calendario_guardado(b)}
            vistos.update({(c.fecha_ida, c.fecha_vuelta): c.precio for c in res.calendario})
            futuros = [(precio, par) for par, precio in vistos.items() if par[0] > hoy()]
            pares = [min(futuros, key=lambda x: x[0])[1]] if futuros else []

        dia = hoy()
        for fi, fv in pares:
            if fi < dia:
                continue
            res.opciones += self.vuelos(b, fi, fv, validador)
        res.peticiones = len(self.respuestas) - primera_respuesta

        recientes = self.respuestas[primera_respuesta:]
        if any(r.startswith("bloqueo") for r in recientes):
            raise FuenteBloqueada("Google Flights ha respondido con su página de tráfico inusual")
        if not res.opciones and (pares or varios) and not res.error:
            tipos = sorted(set(recientes)) or ["ninguna respuesta"]
            res.error = "Google no devolvió vuelos. Respuestas: " + " | ".join(tipos)
        return res


def calendario_guardado(b: dict) -> list[PrecioCalendario]:
    """Precios de calendario acumulados en rondas anteriores (info.calendario: 'ida|vuelta' -> [precio, visto])."""
    guardado = []
    for clave, (precio, _visto) in ((b.get("info") or {}).get("calendario") or {}).items():
        ida, _, vuelta = clave.partition("|")
        guardado.append(PrecioCalendario(date.fromisoformat(ida), date.fromisoformat(vuelta) if vuelta else None, precio))
    return guardado
