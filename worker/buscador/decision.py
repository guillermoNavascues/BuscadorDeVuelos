"""¿Es el momento de avisar para comprar?

Basado en la investigación (docs/INVESTIGACION.md):
- Ventana más barata: nacional ~3-9 semanas antes, Europa ~4-10, larga distancia ~7-19.
- En las 3 últimas semanas el precio casi siempre sube (Ryanair: +50-75 % en los últimos días).
- Nadie conoce el mínimo futuro: se avisa cuando el precio es el más bajo visto o está en la
  zona baja de lo habitual para fechas cercanas, y siempre antes de entrar en las 3 últimas semanas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median

from . import aeropuertos
from .modelos import Opcion
from .viaje import primera_salida

# Días antes de la salida en los que suele estar lo más barato (inicio, fin)
VENTANA_OPTIMA = {"nacional": (21, 60), "europa": (28, 70), "largo": (50, 135)}
DIAS_VIAJE_PROXIMO = 21  # menos de 3 semanas: avisar ya con lo mejor que haya
DIAS_AVISO_FINAL = 24  # último aviso antes de entrar en las 3 últimas semanas
BAJADA_MINIMA_PCT = 0.05  # volver a avisar si baja al menos un 5 %...
BAJADA_MINIMA_EUR = 10.0  # ...o al menos 10 €
# Con revisiones cada pocos minutos, un "mínimo" de la última hora no dice nada:
# para darlo por bueno hace falta haber observado el precio durante un tiempo.
HORAS_PARA_MINIMO = 6
HORAS_PARA_CHOLLO_ANTICIPADO = 24
# Bajada fuerte: avisar aunque no sea "el momento" ni llegue a tu objetivo (p. ej. de 171 € a 70 €)
BAJADA_FUERTE_PCT = 0.15
BAJADA_FUERTE_EUR = 15.0
# Modo presupuesto: avisar también si se queda cerca del objetivo: hasta un 20 % más caro.
# P. ej. con 30 € de objetivo, hasta 36 €; con 60 €, hasta 72 €; con 600 €, hasta 720 €.
CERCA_OBJETIVO_PCT = 0.20


@dataclass
class Decision:
    avisar: bool
    tipo: str = ""
    titulo: str = ""
    motivo: str = ""
    # True si el aviso cuenta como "precio avisado" (para no repetir salvo bajadas)
    fija_precio: bool = True
    contexto: dict = field(default_factory=dict)


def _percentil(valores: list[float], p: float) -> float:
    datos = sorted(valores)
    if not datos:
        raise ValueError("sin datos")
    k = (len(datos) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(datos) - 1)
    return datos[f] + (datos[c] - datos[f]) * (k - f)


def _eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _no_supera_minimo(total: float, historial: list[float]) -> bool:
    """Un "chollo" nunca puede ser más caro que lo más barato ya visto en esta búsqueda."""
    return not historial or total <= min(historial) + 0.005


def margen_objetivo(presupuesto: float) -> float:
    return presupuesto * CERCA_OBJETIVO_PCT


def _pct_menos(precio: float, referencia: float) -> int:
    """Cuánto más barato (en %) es `precio` que `referencia`."""
    return round((1 - precio / referencia) * 100) if referencia else 0


def _bajada_fuerte(total: float, historial: list[float], contexto: dict) -> Decision | None:
    """Precio claramente por debajo de todo lo visto hasta ahora en esta búsqueda."""
    if not historial:
        return None
    minimo = min(historial)
    if total <= minimo * (1 - BAJADA_FUERTE_PCT) and minimo - total >= BAJADA_FUERTE_EUR:
        pct = round((minimo - total) / minimo * 100)
        return Decision(
            True, "bajada_fuerte", "📉 ¡Bajada fuerte de precio!",
            f"Ahora {_eur(total)}: {_eur(minimo - total)} menos (−{pct} %) que lo más barato visto hasta ahora "
            f"({_eur(minimo)}). Si te encaja, puede ser buen momento para comprar.",
            # No cuenta como "precio avisado": tus avisos normales (objetivo, buen momento...) siguen igual
            fija_precio=False, contexto=contexto,
        )
    return None


def decidir(
    busqueda: dict,
    mejor: Opcion | None,
    historial: list[float],
    calendario: list[float],
    hoy: date,
    horas_historial: float = 0.0,
) -> Decision:
    """historial: mejores totales de revisiones anteriores (antiguo → reciente).
    calendario: precios de billetes (sin maletas) de fechas cercanas o del rango del chollo.
    horas_historial: cuántas horas abarca el historial (de la primera revisión a la última)."""
    contexto: dict = {}
    if historial:
        contexto["minimo_visto"] = min(historial)
    if len(calendario) >= 5:
        contexto["habitual"] = (round(_percentil(calendario, 25)), round(_percentil(calendario, 75)))

    modo_fechas = busqueda["modo"] == "fechas"
    dias = None
    if modo_fechas:
        dias = (primera_salida(busqueda, hoy) - hoy).days  # con varias fechas, la más cercana
        contexto["dias"] = dias

    if mejor is None:
        # Ningún vuelo cumple los filtros (aeropuertos, horarios, escalas, aerolíneas)
        return Decision(False, contexto=contexto)

    total = mejor.precio_total
    ultimo = busqueda.get("ultimo_aviso_precio")
    ultimo = float(ultimo) if ultimo is not None else None

    # --- Ya se avisó antes: solo se vuelve a avisar si baja de verdad ---
    if ultimo is not None:
        if busqueda.get("modo_precio") == "presupuesto" and busqueda.get("presupuesto") is not None:
            presupuesto = float(busqueda["presupuesto"])
            if total <= presupuesto < ultimo:
                return Decision(
                    True, "presupuesto", "✅ ¡Ya está dentro de tu presupuesto!",
                    f"Total {_eur(total)} para todos, sin pasar de tu máximo de {_eur(presupuesto)} "
                    f"(el último aviso fue de {_eur(ultimo)}).",
                    contexto=contexto,
                )
        if total <= ultimo * (1 - BAJADA_MINIMA_PCT) or ultimo - total >= BAJADA_MINIMA_EUR:
            return Decision(
                True, "bajada", "📉 ¡Ha bajado todavía más!",
                f"El precio ha bajado de {_eur(ultimo)} a {_eur(total)} desde el último aviso.",
                contexto=contexto,
            )
        return Decision(False, contexto=contexto)

    # --- Modo presupuesto: avisar en cuanto algo no supere el máximo ---
    if busqueda.get("modo_precio") == "presupuesto":
        presupuesto = float(busqueda["presupuesto"])
        if total <= presupuesto:
            return Decision(
                True, "presupuesto", "✅ ¡Dentro de tu presupuesto!",
                f"Total {_eur(total)} para todos, sin pasar de tu máximo de {_eur(presupuesto)}.",
                contexto=contexto,
            )
        if total <= presupuesto + margen_objetivo(presupuesto) and _no_supera_minimo(total, historial):
            return Decision(
                True, "cerca_objetivo", "🎯 ¡Muy cerca de tu objetivo!",
                f"Total {_eur(total)}: solo {_eur(total - presupuesto)} (un {round((total / presupuesto - 1) * 100)} %) "
                f"por encima de tu objetivo de {_eur(presupuesto)}. "
                "Si te vale, puede ser buen momento; sigo vigilando y te aviso si baja de tu objetivo.",
                contexto=contexto,
            )
        if modo_fechas and dias is not None and dias <= DIAS_AVISO_FINAL and not busqueda.get("aviso_final_enviado"):
            return Decision(
                True, "sin_presupuesto", "⚠️ Aún no hay nada dentro de tu presupuesto",
                f"Faltan {dias} días y a partir de ahora el precio suele subir. Lo más barato que "
                f"cumple tus filtros cuesta {_eur(total)} (tu máximo: {_eur(presupuesto)}). "
                "Sigo vigilando por si baja.",
                fija_precio=False, contexto=contexto,
            )
        return _bajada_fuerte(total, historial, contexto) or Decision(False, contexto=contexto)

    # --- Modo chollo (cualquier fecha) y "lo más barato posible" ---
    if not modo_fechas:
        if len(calendario) >= 5:
            mediana = median(calendario)
            umbral = min(_percentil(calendario, 20), mediana * 0.80)
            if mejor.precio_billetes <= umbral and _no_supera_minimo(total, historial):
                return Decision(
                    True, "chollo", f"🔥 ¡Chollo encontrado! −{_pct_menos(mejor.precio_billetes, mediana)} %",
                    f"Billetes a {_eur(mejor.precio_billetes)}: un {_pct_menos(mejor.precio_billetes, mediana)} % más baratos "
                    f"que el precio normal de esta ruta en tus fechas ({_eur(mediana)}).",
                    contexto=contexto,
                )
        if (len(historial) >= 4 and horas_historial >= HORAS_PARA_MINIMO and total <= median(historial) * 0.80
                and _no_supera_minimo(total, historial)):
            return Decision(
                True, "chollo", f"🔥 ¡Chollo encontrado! −{_pct_menos(total, median(historial))} %",
                f"{_eur(total)}: un {_pct_menos(total, median(historial))} % más barato que lo normal en lo que he visto "
                f"hasta ahora en esta ruta ({_eur(median(historial))}).",
                contexto=contexto,
            )
        return _bajada_fuerte(total, historial, contexto) or Decision(False, contexto=contexto)

    # --- Modo fechas y "lo más barato posible" ---
    if dias <= DIAS_VIAJE_PROXIMO:
        return Decision(
            True, "proximo", "⏰ Viaje próximo: mejor opción ahora",
            f"Sales en {dias} días. A partir de ahora el precio casi siempre sube, así que esta es "
            "la mejor opción que hay. Te avisaré si baja.",
            contexto=contexto,
        )
    if dias <= DIAS_AVISO_FINAL:
        return Decision(
            True, "final", "⏳ Último aviso recomendado",
            f"Faltan {dias} días: en las próximas 3 semanas el precio suele subir. Es buen momento para comprar.",
            contexto=contexto,
        )

    zona = aeropuertos.tipo_ruta(busqueda["origen"], busqueda["destino"])
    _, fin_ventana = VENTANA_OPTIMA[zona]
    referencia_baja = _percentil(calendario, 25) if len(calendario) >= 5 else None
    minimo = min(historial) if historial else None

    if dias <= fin_ventana:
        if len(historial) >= 2 and horas_historial >= HORAS_PARA_MINIMO and total <= minimo:
            return Decision(
                True, "buen_momento", "✅ Buen momento para comprar",
                f"Es el precio más bajo de las últimas {round(horas_historial)} h de vigilancia y estás en la ventana en la que "
                f"los vuelos suelen estar más baratos ({dias} días antes).",
                contexto=contexto,
            )
        if referencia_baja is not None and mejor.precio_billetes <= referencia_baja:
            return Decision(
                True, "buen_momento", "✅ Buen momento para comprar",
                f"Está en la zona baja de lo habitual para fechas cercanas y estás en la ventana "
                f"más barata ({dias} días antes).",
                contexto=contexto,
            )
        return _bajada_fuerte(total, historial, contexto) or Decision(False, contexto=contexto)

    # Todavía es pronto: solo se avisa si es algo excepcional
    if (len(historial) >= 6 and horas_historial >= HORAS_PARA_CHOLLO_ANTICIPADO and total <= median(historial) * 0.80
            and _no_supera_minimo(total, historial)):
        return Decision(
            True, "chollo", f"🔥 Chollo anticipado −{_pct_menos(total, median(historial))} %",
            f"Aún es pronto ({dias} días), pero {_eur(total)} es un {_pct_menos(total, median(historial))} % más barato "
            f"que lo normal en lo que he visto ({_eur(median(historial))}).",
            contexto=contexto,
        )
    if len(calendario) >= 10 and mejor.precio_billetes <= median(calendario) * 0.75 and _no_supera_minimo(total, historial):
        return Decision(
            True, "chollo", f"🔥 Chollo anticipado −{_pct_menos(mejor.precio_billetes, median(calendario))} %",
            f"Aún es pronto ({dias} días), pero los billetes ({_eur(mejor.precio_billetes)}) son un "
            f"{_pct_menos(mejor.precio_billetes, median(calendario))} % más baratos que lo normal en fechas cercanas "
            f"({_eur(median(calendario))}).",
            contexto=contexto,
        )
    return _bajada_fuerte(total, historial, contexto) or Decision(False, contexto=contexto)


# Cada cuántos minutos se revisa una búsqueda (el robot funciona sin parar).
# Las aerolíneas cambian precios varias veces al día: revisar más a menudo no aporta más
# información y solo haría que Google bloquease al robot.
# Cada 20 min si el viaje sale en menos de 2 meses y cada 40 si falta más. Además, el robot no pasa de
# un número de consultas a Google por hora (run.py): si hay muchas búsquedas, esperan un poco en cola.
# Así se reparte primero en los viajes cercanos, que es donde los precios se mueven más.
DIAS_VIAJE_CERCANO = 60
REVISION_CERCA_MIN = 20
REVISION_LEJOS_MIN = 40


def minutos_hasta_siguiente_revision(busqueda: dict, hoy: date) -> int:
    """Cada 20 min hasta 2 meses vista; cada 40 si falta más (en un chollo cuenta el inicio del periodo)."""
    dias = (primera_salida(busqueda, hoy) - hoy).days
    return REVISION_CERCA_MIN if dias <= DIAS_VIAJE_CERCANO else REVISION_LEJOS_MIN
