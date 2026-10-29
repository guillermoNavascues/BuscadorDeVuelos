from datetime import date, datetime, timedelta

from buscador import precios
from buscador.decision import decidir
from buscador.filtros import Validador
from buscador.modelos import Opcion, Tramo, Trayecto

AEROLINEAS = {
    "FR": {"nombre": "Ryanair", "permitida": True, "cabina_max": 40, "facturada_nacional_max": 59.99,
           "facturada_europa_max": 59.99, "facturada_largo_max": 59.99, "cobra_por": "tramo"},
    "IB": {"nombre": "Iberia", "permitida": True, "cabina_max": 0, "facturada_nacional_max": 57,
           "facturada_europa_max": 95, "facturada_largo_max": 135, "cobra_por": "trayecto"},
    "XX": {"nombre": "Bloqueada", "permitida": False, "cabina_max": 0, "facturada_nacional_max": 0,
           "facturada_europa_max": 0, "facturada_largo_max": 0, "cobra_por": "tramo"},
}


def tramo(aero, o, d, salida, horas=2, operadora=None):
    return Tramo(aero, "100", o, d, salida, salida + timedelta(hours=horas), operadora)


def busqueda(**cambios):
    b = {
        "id": "x", "usuario": "u", "nombre": "prueba", "modo": "fechas", "ida_vuelta": True,
        "origen": "SVQ", "destino": "ORY", "fecha_ida": "2026-11-15", "fecha_vuelta": "2026-11-19",
        "adultos": 2, "ninos": 0, "bebes": 0, "maletas_cabina": 0, "maletas_20kg": 1,
        "escalas_max": 1, "escala_max_horas": 6, "modo_precio": "mas_barato", "presupuesto": None,
        "aplicar_descuentos": True, "info": {},
    }
    b.update(cambios)
    return b


IDA = datetime(2026, 11, 15, 7, 0)
VUELTA = datetime(2026, 11, 19, 18, 0)


def opcion_directa(aero_ida="FR", aero_vuelta="FR", precio=200.0):
    return Opcion("prueba", Trayecto([tramo(aero_ida, "SVQ", "ORY", IDA)]),
                  Trayecto([tramo(aero_vuelta, "ORY", "SVQ", VUELTA)]), precio)


# ---------------- precios ----------------

def test_maletas_por_tramo_y_por_trayecto():
    b = busqueda(maletas_20kg=2)
    op = Opcion("p", Trayecto([tramo("FR", "SVQ", "MAD", IDA), tramo("FR", "MAD", "ORY", IDA + timedelta(hours=3))]),
                Trayecto([tramo("IB", "ORY", "MAD", VUELTA), tramo("IB", "MAD", "SVQ", VUELTA + timedelta(hours=3))]), 300)
    precios.calcular(op, b, None, AEROLINEAS)
    # Ryanair cobra por vuelo: 2 vuelos x 2 maletas x 59,99. Iberia una vez por trayecto: 2 x 95
    assert op.precio_maletas == round(2 * 2 * 59.99 + 2 * 95, 2)
    assert op.precio_total == round(300 + op.precio_maletas, 2)
    assert op.maletas_estimadas


def test_familia_numerosa_solo_en_vuelos_nacionales():
    perfil = {"familia_numerosa": "general", "residente": "ninguno"}
    b_nac = busqueda(destino="BCN", maletas_20kg=0)
    op = Opcion("p", Trayecto([tramo("IB", "SVQ", "BCN", IDA)]), Trayecto([tramo("IB", "BCN", "SVQ", VUELTA)]), 200)
    precios.calcular(op, b_nac, perfil, AEROLINEAS)
    # 5 % sobre (200 - 20 € x 2 pasajeros x 2 vuelos) = 5 % de 120
    assert op.descuento == 6.0
    assert op.precio_total == 194.0

    op_int = opcion_directa(precio=200)
    precios.calcular(op_int, busqueda(maletas_20kg=0), perfil, AEROLINEAS)
    assert op_int.descuento == 0


def test_residente_canarias():
    perfil = {"familia_numerosa": "especial", "residente": "canarias"}
    b = busqueda(destino="TFN", maletas_20kg=0, adultos=1)
    op = Opcion("p", Trayecto([tramo("IB", "SVQ", "TFN", IDA)]), Trayecto([tramo("IB", "TFN", "SVQ", VUELTA)]), 140)
    precios.calcular(op, b, perfil, AEROLINEAS)
    assert op.descuento == round((140 - 40) * 0.85, 2)


# ---------------- filtros ----------------

def test_aeropuerto_exacto_y_vuelta_al_mismo_aeropuerto():
    v = Validador(busqueda(), AEROLINEAS)
    assert v.opcion(opcion_directa()) is None
    mal = Opcion("p", Trayecto([tramo("FR", "SVQ", "BVA", IDA)]), Trayecto([tramo("FR", "BVA", "SVQ", VUELTA)]), 50)
    assert "llega a BVA" in v.opcion(mal)
    vuelta_a_otro = Opcion("p", Trayecto([tramo("FR", "SVQ", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "AGP", VUELTA)]), 50)
    assert "llega a AGP" in v.opcion(vuelta_a_otro)


def test_franjas_horarias_y_llegada_al_dia_siguiente():
    v = Validador(busqueda(ida_salida_min=8, ida_llegada_max=22), AEROLINEAS)
    assert "sale a las 07:00" in v.opcion(opcion_directa())
    nocturno = Opcion("p", Trayecto([tramo("FR", "SVQ", "ORY", datetime(2026, 11, 15, 21, 30), horas=3)]),
                      Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 50)
    v2 = Validador(busqueda(ida_llegada_max=23), AEROLINEAS)
    assert "día siguiente" in v2.opcion(nocturno)


def test_lista_blanca_incluye_operadora():
    v = Validador(busqueda(), AEROLINEAS)
    op = Opcion("p", Trayecto([tramo("IB", "SVQ", "ORY", IDA, operadora="XX")]), Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 50)
    assert "bloqueada" in v.opcion(op)
    op2 = Opcion("p", Trayecto([tramo("IB", "SVQ", "ORY", IDA, operadora="ZZ")]), Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 50)
    assert "lista blanca" in v.opcion(op2)


def test_escala_demasiado_larga():
    v = Validador(busqueda(), AEROLINEAS)
    op = Opcion("p", Trayecto([tramo("IB", "SVQ", "MAD", IDA), tramo("IB", "MAD", "ORY", IDA + timedelta(hours=10))]),
                Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 50)
    assert "escala de" in v.opcion(op)


# ---------------- decisión ----------------

def _con_total(total, billetes=None):
    op = opcion_directa(precio=billetes if billetes is not None else total)
    op.precio_total = total
    return op


def test_presupuesto():
    b = busqueda(modo_precio="presupuesto", presupuesto=200)
    hoy = date(2026, 9, 1)
    assert decidir(b, _con_total(250), [], [], hoy).avisar is False  # más allá del margen (200 + 20 % = 240)
    assert decidir(b, _con_total(210), [], [], hoy).tipo == "cerca_objetivo"
    d = decidir(b, _con_total(199.99), [], [], hoy)
    assert d.avisar and d.tipo == "presupuesto"


def test_rebaja_tras_aviso():
    b = busqueda(modo_precio="presupuesto", presupuesto=200, ultimo_aviso_precio=180)
    hoy = date(2026, 9, 1)
    assert decidir(b, _con_total(175), [], [], hoy).avisar is False  # baja menos de 5 % y de 10 €
    assert decidir(b, _con_total(170), [], [], hoy).tipo == "bajada"


def test_viaje_proximo_avisa_ya():
    b = busqueda()
    d = decidir(b, _con_total(300), [], [], date(2026, 11, 5))
    assert d.avisar and d.tipo == "proximo"


def test_ventana_optima_minimo_visto():
    b = busqueda()
    hoy = date(2026, 10, 1)  # 45 días antes: dentro de la ventana para Europa
    assert decidir(b, _con_total(250), [260, 255], [], hoy, horas_historial=12).tipo == "buen_momento"
    # Con solo 1 hora observada todavía no se fía del mínimo
    assert decidir(b, _con_total(250), [260, 255], [], hoy, horas_historial=1).avisar is False
    assert decidir(b, _con_total(270), [260, 255], [], hoy).avisar is False


def test_pronto_solo_chollos():
    b = busqueda()
    hoy = date(2026, 7, 1)  # 137 días antes: demasiado pronto para Europa
    assert decidir(b, _con_total(250), [260, 255], [], hoy).avisar is False
    hist = [300, 310, 305, 300, 295, 300]
    assert decidir(b, _con_total(230), hist, [], hoy, horas_historial=30).tipo == "chollo"


def test_chollo_por_calendario():
    b = busqueda(modo="chollo", chollo_desde="2026-11-01", chollo_hasta="2027-01-31")
    calendario = [100, 110, 120, 130, 140, 150, 160, 170]
    assert decidir(b, _con_total(140, billetes=95), [], calendario, date(2026, 10, 1)).tipo == "chollo"
    assert decidir(b, _con_total(160, billetes=125), [], calendario, date(2026, 10, 1)).avisar is False


# ---------------- conexión con Supabase ----------------

def test_cabeceras_segun_tipo_de_clave():
    from buscador.db import Supabase

    nueva = Supabase("https://x.supabase.co", "sb_secret_abc")
    assert nueva.http.headers["apikey"] == "sb_secret_abc"
    assert "authorization" not in nueva.http.headers  # las claves sb_ no son JWT
    antigua = Supabase("https://x.supabase.co", "eyJhbGciOi.antigua")
    assert antigua.http.headers["authorization"] == "Bearer eyJhbGciOi.antigua"


def test_url_con_o_sin_rest_v1():
    from buscador.db import Supabase

    for url in ("https://x.supabase.co", "https://x.supabase.co/", "https://x.supabase.co/rest/v1/"):
        assert Supabase(url, "sb_secret_abc").base == "https://x.supabase.co/rest/v1"


def test_clasificar_respuestas_de_google():
    from buscador.fuentes.google_flights import describir_respuesta

    pagina = "<html><script>AF_initDataCallback({key: 'ds:1', data: []})</script></html>"
    assert describir_respuesta(200, pagina).startswith("página de resultados")
    error13 = ')]}\'\n[["wrb.fr",null,null,null,null,[13,null,[["type.googleapis.com/travel.frontend.flights.ErrorResponse"]]]]]'
    assert describir_respuesta(200, error13).startswith("error 13")
    assert describir_respuesta(429, "<html>").startswith("bloqueo")
    assert describir_respuesta(200, "<html>Our systems have detected unusual traffic").startswith("bloqueo")
    assert describir_respuesta(200, '<html><a href="https://consent.google.com/x">').startswith("página de consentimiento")
    assert describir_respuesta(200, "<html><body>hola</body></html>").startswith("página sin datos")


def test_muestras_y_calendario_acumulado_del_chollo():
    from buscador.fuentes.google_flights import FECHAS_CHOLLO_POR_RONDA, GoogleFlights, calendario_guardado
    from buscador.modelos import PrecioCalendario
    from buscador.run import acumular_calendario

    hoy = date.today()
    b = busqueda(modo="chollo", ida_vuelta=True, chollo_desde=(hoy + timedelta(days=5)).isoformat(),
                 chollo_hasta=(hoy + timedelta(days=95)).isoformat(), noches_min=2, noches_max=4, info={})
    vistas = set()
    for turno in range(40):
        b["info"]["chollo_turno"] = turno
        muestras = GoogleFlights._muestras_chollo(b)
        assert 0 < len(muestras) <= FECHAS_CHOLLO_POR_RONDA
        for fi, noches in muestras:
            assert fi + timedelta(days=noches) <= hoy + timedelta(days=95)
        # En cada ronda, fechas de días de la semana distintos (no siempre el mismo)
        assert len({fi.weekday() for fi, _ in muestras}) >= 4
        vistas |= set(muestras)
    assert len({fi for fi, _ in vistas}) > 80  # en 40 rondas se ha mirado casi cada día del periodo

    solo_ida = busqueda(modo="chollo", ida_vuelta=False, chollo_desde=(hoy + timedelta(days=20)).isoformat(),
                        chollo_hasta=(hoy + timedelta(days=80)).isoformat(), info={})
    for turno in range(10):
        solo_ida["info"]["chollo_turno"] = turno
        assert len({fi.weekday() for fi, _ in GoogleFlights._muestras_chollo(solo_ida)}) >= 4

    info = {"calendario": {"2000-01-01|2000-01-03": [10, "2000-01-01"]}}  # pasada: se descarta
    acumular_calendario(info, [PrecioCalendario(hoy + timedelta(days=9), hoy + timedelta(days=12), 80.0)], hoy)
    assert list(info["calendario"]) == [f"{hoy + timedelta(days=9)}|{hoy + timedelta(days=12)}"]
    assert info["chollo_turno"] == 1
    assert calendario_guardado({"info": info})[0].precio == 80.0


# ---------------- versión 3: varios aeropuertos, bajada fuerte, comprar ya ----------------

def test_varios_aeropuertos_de_salida_y_una_sola_llegada():
    b = busqueda(origenes_extra=["XRY"], destinos_extra=["CDG"])  # la llegada extra (versiones antiguas) se ignora
    v = Validador(b, AEROLINEAS)
    jerez_y_vuelta_a_jerez = Opcion("p", Trayecto([tramo("FR", "XRY", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "XRY", VUELTA)]), 90)
    jerez_y_vuelta_a_sevilla = Opcion("p", Trayecto([tramo("FR", "XRY", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 80)
    a_cdg = Opcion("p", Trayecto([tramo("FR", "XRY", "CDG", IDA)]), Trayecto([tramo("FR", "CDG", "XRY", VUELTA)]), 70)
    desde_madrid = Opcion("p", Trayecto([tramo("FR", "MAD", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 60)
    assert v.opcion(jerez_y_vuelta_a_jerez) is None and not jerez_y_vuelta_a_jerez.vuelta_a_otro_aeropuerto
    assert v.opcion(jerez_y_vuelta_a_sevilla) is None and jerez_y_vuelta_a_sevilla.vuelta_a_otro_aeropuerto
    assert "CDG" in v.opcion(a_cdg)  # solo vale la llegada elegida
    assert "MAD" in v.opcion(desde_madrid) and "SVQ / XRY" in v.opcion(desde_madrid)
    assert Validador(busqueda(), AEROLINEAS).opcion(jerez_y_vuelta_a_jerez) is not None  # sin extras, solo el exacto


def test_se_guarda_siempre_la_que_vuelve_al_mismo_aeropuerto():
    from buscador.run import opciones_a_guardar
    otro = [Opcion("p", Trayecto([tramo("FR", "XRY", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 80 + i)
            for i in range(6)]
    mismo = Opcion("p", Trayecto([tramo("FR", "XRY", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "XRY", VUELTA)]), 99)
    elegidas = opciones_a_guardar(otro + [mismo], n=5)
    assert len(elegidas) == 5 and elegidas[0] is otro[0] and elegidas[-1] is mismo


def test_aviso_indica_que_vuelves_a_otro_aeropuerto():
    from buscador.avisos import mensaje_aviso
    from buscador.decision import Decision
    b = busqueda(origenes_extra=["XRY"])
    barato = Opcion("p", Trayecto([tramo("FR", "XRY", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "SVQ", VUELTA)]), 80)
    barato.precio_total = 80
    mismo = Opcion("p", Trayecto([tramo("FR", "XRY", "ORY", IDA)]), Trayecto([tramo("FR", "ORY", "XRY", VUELTA)]), 95)
    mismo.precio_total = 95
    texto = mensaje_aviso(b, barato, Decision(True, "chollo", "t", "m"), [], "https://g", AEROLINEAS, None,
                          mismo_aeropuerto=mismo)
    assert "vuelves a" in texto and "SVQ" in texto and "95,00 €" in texto and "+15,00 €" in texto


def test_ruta_con_varios_aeropuertos_en_los_mensajes():
    from buscador.avisos import ruta_txt
    texto = ruta_txt(busqueda(origenes_extra=["XRY", "SVQ"], destinos_extra=["CDG"]))  # el repetido no se duplica
    assert texto.count("SVQ") == 1 and "XRY" in texto and " o " in texto and "ORY" in texto and "CDG" not in texto


def test_bajada_fuerte_avisa_aunque_no_llegue_al_objetivo():
    b = busqueda(modo_precio="presupuesto", presupuesto=30)
    d = decidir(b, _con_total(70), [171, 172, 171], [], date(2026, 9, 1))
    assert d.avisar and d.tipo == "bajada_fuerte" and d.fija_precio is False and "171" in d.motivo
    # Un vaivén normal no es una bajada fuerte
    assert decidir(b, _con_total(165), [171, 172, 171], [], date(2026, 9, 1)).avisar is False
    # Si llega al objetivo, manda el aviso de objetivo (más importante)
    assert decidir(b, _con_total(29), [171], [], date(2026, 9, 1)).tipo == "presupuesto"


def test_chollo_nunca_mas_caro_que_el_minimo_visto():
    b = busqueda(modo="chollo", chollo_desde="2026-10-09", chollo_hasta="2026-10-28")
    calendario = [150, 200, 260, 300, 340, 380, 420, 460]  # fechas caras del periodo: mediana alta
    # 182 € es "barato" frente a la mediana del periodo, pero ya se vio 171 €: no es un chollo
    assert decidir(b, _con_total(182, billetes=182), [171, 175], calendario, date(2026, 10, 8)).avisar is False
    assert decidir(b, _con_total(165, billetes=165), [171, 175], calendario, date(2026, 10, 8)).tipo == "chollo"


def test_chollo_dice_el_porcentaje_exacto():
    b = busqueda(modo="chollo", chollo_desde="2026-10-09", chollo_hasta="2026-10-28")
    calendario = [150, 180, 195, 201, 201, 220, 260, 300, 340]  # mediana 201 €
    d = decidir(b, _con_total(122, billetes=122), [], calendario, date(2026, 10, 8))
    assert d.tipo == "chollo" and "39 % más baratos" in d.motivo and "201,00 €" in d.motivo and "−39 %" in d.titulo


def test_cerca_del_objetivo_y_despues_dentro():
    b = busqueda(modo_precio="presupuesto", presupuesto=30)
    hoy = date(2026, 9, 1)
    cerca = decidir(b, _con_total(35), [60], [], hoy)  # objetivo 30: avisa hasta 36 € (+20 %)
    assert cerca.tipo == "cerca_objetivo" and cerca.fija_precio and "17 %" in cerca.motivo
    assert decidir(b, _con_total(37), [39], [], hoy).avisar is False  # 37 € pasa de 36 € (+20 %) y no es bajada fuerte
    assert decidir(b, _con_total(35), [34], [], hoy).avisar is False  # ya se vio más barato
    # Ya avisado a 45 €: al bajar de 30 llega el aviso de "dentro de tu presupuesto", aunque baje poco
    ya = busqueda(modo_precio="presupuesto", presupuesto=30, ultimo_aviso_precio=31)
    assert decidir(ya, _con_total(29.5), [31], [], hoy).tipo == "presupuesto"
    assert decidir(ya, _con_total(30.5), [31], [], hoy).avisar is False


def test_chollo_cercano_se_revisa_cada_20_minutos():
    from buscador.decision import minutos_hasta_siguiente_revision
    hoy = date(2026, 10, 8)
    cerca = busqueda(modo="chollo", chollo_desde="2026-10-09", chollo_hasta="2026-10-28")
    lejos = busqueda(modo="chollo", chollo_desde="2027-02-01", chollo_hasta="2027-03-01")
    assert minutos_hasta_siguiente_revision(cerca, hoy) == 20
    assert minutos_hasta_siguiente_revision(lejos, hoy) == 40  # a más de 2 meses, cada 40 min
    # Con fechas concretas: hasta 2 meses vista, cada 20; después, cada 40
    assert minutos_hasta_siguiente_revision(busqueda(fecha_ida="2026-12-07", fecha_vuelta="2026-12-10"), hoy) == 20
    assert minutos_hasta_siguiente_revision(busqueda(fecha_ida="2026-12-08", fecha_vuelta="2026-12-10"), hoy) == 40


def test_enlaces_comprar_ya_en_google_flights():
    from buscador.enlaces import comprar_ya
    juntos = comprar_ya(busqueda(), opcion_directa())
    assert len(juntos) == 1 and juntos[0]["url"].startswith("https://www.google.com/travel/flights/booking?tfs=")
    separados = opcion_directa()
    separados.billetes_separados = True
    assert [e["texto"] for e in comprar_ya(busqueda(), separados)] == ["Comprar la ida", "Comprar la vuelta"]


def test_enlace_google_abre_en_los_mas_bajos():
    from buscador.enlaces import google_flights
    url = google_flights(busqueda(), opcion_directa())
    assert url.startswith("https://www.google.com/travel/flights/search?tfs=") and "tfu=EgoIABAAGAAgAigB" in url


def test_google_sin_pagina_de_resultados():
    import pytest
    from fli.search import SearchParseError

    from buscador.fuentes.google_flights import GoogleFlights, SinResultados
    from buscador.modelos import FuenteBloqueada

    g = GoogleFlights.__new__(GoogleFlights)  # sin red ni cliente real
    g.pausa, g._primera, g.respuestas, g._sin_datos, g._busqueda = (0, 0), True, [], [], "b1"

    def sin_datos(**_):
        g.respuestas.append("página sin datos de vuelos (HTTP 200, 900 bytes)")
        raise SearchParseError("Search page carried no ds:1 payload")

    # Una vez: mensaje claro en español (sin el nombre técnico del error)
    with pytest.raises(SinResultados, match="página sin vuelos"):
        g._llamar(sin_datos)
    # Si falla siempre la misma búsqueda, es cosa de esa búsqueda: no se para el robot
    for _ in range(3):
        with pytest.raises(SinResultados):
            g._llamar(sin_datos)
    # Si falla también otra búsqueda seguida, sí: es Google, y el robot espera
    g._busqueda = "b2"
    with pytest.raises(FuenteBloqueada):
        g._llamar(sin_datos)
    # Una respuesta buena pone la cuenta a cero
    assert g._llamar(lambda **_: [1]) == [1] and g._sin_datos == []

    def trafico_inusual(**_):
        g.respuestas.append("bloqueo (HTTP 200)")
        raise SearchParseError("Search page carried no ds:1 payload")

    with pytest.raises(FuenteBloqueada):  # la página de "tráfico inusual" es un bloqueo a la primera
        g._llamar(trafico_inusual)

    def cookies(**_):
        g.respuestas.append("página de consentimiento de cookies (HTTP 200)")
        raise SearchParseError("x")

    g._sin_datos = []
    with pytest.raises(SinResultados, match="cookies"):
        g._llamar(cookies)


# ---------------- varias fechas y varios destinos ----------------

def test_varias_fechas_en_una_busqueda():
    from buscador import viaje

    b = busqueda(fechas_extra=[{"ida": "2026-11-20", "vuelta": "2026-11-23"}, {"ida": "2026-11-15", "vuelta": "2026-11-19"},
                               {"ida": "2026-11-27", "vuelta": "2026-11-25"}])
    # Sin repetir la principal ni aceptar una vuelta anterior a la ida
    assert viaje.pares_fechas(b) == [(date(2026, 11, 15), date(2026, 11, 19)), (date(2026, 11, 20), date(2026, 11, 23))]
    assert viaje.primera_salida(b, date(2026, 11, 16)) == date(2026, 11, 20)
    solo = busqueda(ida_vuelta=False, fecha_vuelta=None, fechas_extra=[{"ida": "2026-11-18"}])
    assert viaje.pares_fechas(solo) == [(date(2026, 11, 15), None), (date(2026, 11, 18), None)]


def test_lo_que_ya_ha_llegado_se_quita_y_la_busqueda_se_borra():
    from buscador.viaje import caducidad

    d = lambda dia: date(2026, 11, dia)  # noqa: E731
    b = busqueda(fechas_extra=[{"ida": "2026-11-20", "vuelta": "2026-11-23"}])  # 15-19 y 20-23
    assert caducidad(b, d(14)) == (False, {})
    # El día en que empieza el viaje, esas fechas se quitan: las siguientes pasan a ser las principales
    assert caducidad(b, d(15)) == (False, {"fecha_ida": "2026-11-20", "fecha_vuelta": "2026-11-23", "fechas_extra": []})
    assert caducidad(b, d(20)) == (True, {})  # no queda ninguna: se borra
    # La principal sigue y una alternativa ya pasó (solo ida)
    solo = busqueda(ida_vuelta=False, fecha_vuelta=None, fecha_ida="2026-11-20",
                    fechas_extra=[{"ida": "2026-11-12"}, {"ida": "2026-11-25"}])
    assert caducidad(solo, d(13)) == (False, {"fecha_ida": "2026-11-20", "fecha_vuelta": None,
                                              "fechas_extra": [{"ida": "2026-11-25"}]})
    # Con ±1 día de margen se podría salir el 16: hasta entonces no caduca
    assert caducidad(busqueda(flex_dias=1), d(15)) == (False, {})
    assert caducidad(busqueda(flex_dias=1), d(16)) == (True, {})
    # Chollo: el periodo empieza siempre mañana y se borra cuando ya no cabe la estancia mínima
    chollo = busqueda(modo="chollo", fecha_ida=None, fecha_vuelta=None, chollo_desde="2026-11-01",
                      chollo_hasta="2026-11-30", noches_min=3, noches_max=5)
    assert caducidad(chollo, d(10)) == (False, {"chollo_desde": "2026-11-11"})
    assert caducidad({**chollo, "chollo_desde": "2026-11-11"}, d(10)) == (False, {})
    assert caducidad(chollo, d(26)) == (False, {"chollo_desde": "2026-11-27"})
    assert caducidad(chollo, d(27)) == (True, {})  # salir el 28 con 3 noches ya no cabe antes del 30
    # Varios destinos: cuando sale el primer vuelo
    varios = busqueda(ida_vuelta=False, fecha_vuelta=None, fecha_ida="2026-11-13", tramos_viaje=[
        {"origen": "SVQ", "destino": "KRK", "fecha": "2026-11-13"}, {"origen": "KRK", "destino": "SVQ", "fecha": "2026-11-16"}])
    assert caducidad(varios, d(12)) == (False, {}) and caducidad(varios, d(13)) == (True, {})
    assert caducidad(busqueda(fecha_ida=None), d(20)) == (False, {})  # incompleta: no se toca


def test_viaje_con_varios_destinos(monkeypatch):
    from types import SimpleNamespace

    from buscador import enlaces, viaje
    from buscador.avisos import mensaje_aviso
    from buscador.decision import Decision
    from buscador.fuentes import google_flights as gf

    b = busqueda(ida_vuelta=False, fecha_vuelta=None, origen="SVQ", destino="KRK", fecha_ida="2026-11-13", tramos_viaje=[
        {"origen": "SVQ", "destino": "KRK", "fecha": "2026-11-13"},
        {"origen": "KRK", "destino": "ZRH", "fecha": "2026-11-16"},
        {"origen": "ZRH", "destino": "SVQ", "fecha": "2026-11-19"},
    ])
    assert viaje.es_varios_destinos(b) and viaje.ruta_viaje(b) == ["SVQ", "KRK", "ZRH", "SVQ"]
    vuelos = {
        ("SVQ", "KRK"): [(120, "FR", datetime(2026, 11, 13, 7)), (90, "FR", datetime(2026, 11, 13, 20))],
        ("KRK", "ZRH"): [(40, "XX", datetime(2026, 11, 16, 8)), (70, "FR", datetime(2026, 11, 16, 9))],  # XX: bloqueada
        ("ZRH", "SVQ"): [(100, "IB", datetime(2026, 11, 19, 10)), (80, "FR", datetime(2026, 11, 19, 6))],
    }
    g = gf.GoogleFlights.__new__(gf.GoogleFlights)  # sin red
    g._solo_ida_ruta = lambda b_, o, d, fecha, horas: [
        SimpleNamespace(price=p, self_transfer=False, tr=Trayecto([tramo(a, o, d, s)])) for p, a, s in vuelos[(o, d)]]
    monkeypatch.setattr(gf, "_a_trayecto", lambda r: r.tr)
    monkeypatch.setattr(gf, "hoy", lambda: date(2026, 10, 1))
    validador = Validador(b, AEROLINEAS)

    opciones = g.varios_destinos(b, validador)
    assert [o.precio_billetes for o in opciones] == [240, 270]  # 90 + 70 + 80, y la otra ida
    mejor = opciones[0]
    assert [t.origen for t in mejor.trayectos] == ["SVQ", "KRK", "ZRH"] and mejor.billetes_separados
    assert validador.opcion(mejor) is None and len(mejor.a_dict()["siguientes"]) == 2

    precios.calcular(mejor, b, None, AEROLINEAS)  # 1 maleta facturada en cada vuelo de Ryanair
    assert mejor.precio_maletas == round(3 * 59.99, 2) and mejor.desglose_maletas[0].startswith("Vuelo 1")
    assert [e["texto"] for e in enlaces.comprar_ya(b, mejor)] == ["Comprar el vuelo 1", "Comprar el vuelo 2", "Comprar el vuelo 3"]
    assert enlaces.compra(b, mejor, AEROLINEAS)[0]["aerolinea"] == "Ryanair"
    texto = mensaje_aviso(b, mejor, Decision(True, "chollo", "🔥 Chollo", "motivo"), enlaces.compra(b, mejor, AEROLINEAS),
                          enlaces.google_flights(b, mejor), AEROLINEAS, None, comprar=enlaces.comprar_ya(b, mejor))
    assert "Vuelo 3" in texto and "varios destinos" in texto and "Cracovia" in texto and "más baratos" not in texto

    # Un vuelo que sale antes de que llegue el anterior no vale
    al_reves = Opcion("google_flights", Trayecto([tramo("FR", "SVQ", "KRK", datetime(2026, 11, 16, 20))]), None, 100,
                      siguientes=[Trayecto([tramo("FR", "KRK", "ZRH", datetime(2026, 11, 16, 9))]),
                                  Trayecto([tramo("FR", "ZRH", "SVQ", datetime(2026, 11, 19, 6))])])
    assert "antes" in validador.opcion(al_reves)
    # Y si falta un vuelo del viaje, tampoco
    assert validador.opcion(Opcion("x", mejor.ida, None, 1)) == "faltan vuelos del viaje"


def test_sin_vuelos_con_tus_filtros_no_es_un_fallo(monkeypatch):
    from buscador.fuentes import google_flights as gf

    def preparar(respuesta):
        g = gf.GoogleFlights.__new__(gf.GoogleFlights)  # sin red
        g.respuestas, g._sin_datos, g._busqueda = [], [], ""
        g.nueva_sesion_privada = lambda: None

        def vuelos(b, fi, fv, validador):
            g.respuestas.append(respuesta)
            return []
        g.vuelos = vuelos
        return g

    b = busqueda(escalas_max=0)
    # Google respondió con su página de resultados normal: no hay vuelos que cumplan los filtros
    assert preparar("página de resultados (HTTP 200)").buscar(b, Validador(b, AEROLINEAS)).error is None
    # Otra cosa (aviso de cookies, página sin datos...): eso sí es un fallo
    res = preparar("página de consentimiento de cookies (HTTP 200)").buscar(b, Validador(b, AEROLINEAS))
    assert res.error and "cookies" in res.error


def test_ida_y_vuelta_sin_datos_sigue_con_solo_ida(monkeypatch):
    from types import SimpleNamespace

    import pytest

    from buscador.fuentes import google_flights as gf

    b = busqueda()
    g = gf.GoogleFlights.__new__(gf.GoogleFlights)  # sin red
    monkeypatch.setattr(gf, "_a_trayecto", lambda r: r.tr)

    def sin_datos(*_, **__):
        raise gf.SinResultados("sin vuelos")
    g._ida_y_vuelta = sin_datos
    g._solo_ida = lambda b_, sentido, fecha, con_horas=True: [SimpleNamespace(
        price=50, self_transfer=False,
        tr=Trayecto([tramo("FR", "SVQ", "ORY", IDA) if sentido == "ida" else tramo("FR", "ORY", "SVQ", VUELTA)]))]
    opciones = g.vuelos(b, date(2026, 11, 15), date(2026, 11, 19), Validador(b, AEROLINEAS))
    assert [o.precio_billetes for o in opciones] == [100] and opciones[0].billetes_separados

    # Si los de solo ida tampoco dan datos, el error sale (no se disimula un fallo de Google)
    g._solo_ida = sin_datos
    with pytest.raises(gf.SinResultados):
        g.vuelos(b, date(2026, 11, 15), date(2026, 11, 19), Validador(b, AEROLINEAS))


# ---------------- cualquier destino ----------------

def _ida_vuelta(aero, o, d, precio, dia=13, fuente="ryanair"):
    return Opcion(fuente, Trayecto([tramo(aero, o, d, datetime(2026, 11, dia, 8))]),
                  Trayecto([tramo(aero, d, o, datetime(2026, 11, dia + 3, 18))]), precio)


class RyanairFalsa:
    def __init__(self, tarifas):
        self.tarifas, self.pedidas = tarifas, []

    def cualquier_destino(self, b, origen):
        self.pedidas.append(origen)
        return [op for op in self.tarifas if op.ida.origen == origen]


def busqueda_cualquiera(**cambios):
    return busqueda(**{"destino": "XXX", "cualquier_destino": True, "origen": "SVQ", "origenes_extra": ["XRY"],
                       "paises_excluidos": ["RU", "UA"], "maletas_20kg": 0, **cambios})


def test_cualquier_destino_candidatos_sin_paises_excluidos():
    from buscador import cualquier

    b = busqueda_cualquiera()
    ryanair = RyanairFalsa([
        _ida_vuelta("FR", "SVQ", "PMI", 60), _ida_vuelta("FR", "XRY", "PMI", 45),  # el mismo destino desde Jerez, más barato
        _ida_vuelta("FR", "SVQ", "RAK", 40), _ida_vuelta("FR", "SVQ", "SVO", 10),  # Moscú: país excluido
        _ida_vuelta("FR", "SVQ", "XRY", 5),  # uno de tus aeropuertos de salida: no es un destino
    ])
    lista = cualquier.candidatos(b, ryanair)
    assert ryanair.pedidas == ["SVQ", "XRY"]  # una petición por aeropuerto de salida
    assert [(o.ida.origen, o.ida.destino, o.precio_billetes) for o in lista] == [("SVQ", "RAK", 40), ("XRY", "PMI", 45)]


def test_cualquier_destino_con_varias_fechas():
    from buscador import cualquier
    from buscador.modelos import ResultadoFuente

    class RyanairPorFechas(RyanairFalsa):
        def cualquier_destino(self, b, origen):
            self.pedidas.append((origen, b["fecha_ida"], b["fecha_vuelta"]))
            dia = int(b["fecha_ida"][-2:])
            return [op for op in self.tarifas if op.ida.origen == origen and op.ida.salida.day == dia]

    b = busqueda_cualquiera(fecha_ida="2026-11-13", fecha_vuelta="2026-11-16",
                            fechas_extra=[{"ida": "2026-11-20", "vuelta": "2026-11-23"}])
    ryanair = RyanairPorFechas([
        _ida_vuelta("FR", "SVQ", "PMI", 60, dia=13), _ida_vuelta("FR", "SVQ", "PMI", 35, dia=20),  # Palma, mejor el 20
        _ida_vuelta("FR", "XRY", "RAK", 40, dia=13), _ida_vuelta("FR", "XRY", "RAK", 90, dia=20),  # Marrakech, el 13
    ])
    lista = cualquier.candidatos(b, ryanair)
    # Una petición por aeropuerto de salida y fecha
    assert ryanair.pedidas == [("SVQ", "2026-11-13", "2026-11-16"), ("XRY", "2026-11-13", "2026-11-16"),
                               ("SVQ", "2026-11-20", "2026-11-23"), ("XRY", "2026-11-20", "2026-11-23")]
    assert [(o.ida.destino, o.ida.salida.day, o.precio_billetes) for o in lista] == [("PMI", 20, 35), ("RAK", 13, 40)]

    # Google comprueba cada destino en la fecha de su tarifa más barata
    class GoogleFalso:
        fechas = []

        def buscar(self, b2, validador):
            self.fechas.append((b2["destino"], b2["fecha_ida"], b2["fechas_extra"]))
            return ResultadoFuente(opciones=[], peticiones=5)

    google = GoogleFalso()
    top, _, _, _, _ = cualquier.revisar(b, google, ryanair, AEROLINEAS, None, cupo_google=90)
    assert google.fechas == [("PMI", "2026-11-20", []), ("RAK", "2026-11-13", [])]
    assert [(t["destino"], t["fecha_ida"]) for t in cualquier.resumen_top(top)] == [("PMI", "2026-11-20"), ("RAK", "2026-11-13")]

    # Con muchas salidas y fechas, como mucho 12 peticiones a Ryanair
    ryanair.pedidas.clear()
    extra = [{"ida": f"2026-11-{d}", "vuelta": f"2026-11-{d + 2}"} for d in (14, 15, 16, 17, 18)]
    cualquier.candidatos(busqueda_cualquiera(origenes_extra=["XRY", "AGP", "ODB"], fechas_extra=extra), ryanair)
    assert len(ryanair.pedidas) == cualquier.MAX_RYANAIR


def test_cualquier_destino_top_con_tus_filtros_y_google():
    from buscador import cualquier
    from buscador.modelos import ResultadoFuente

    b = busqueda_cualquiera()
    ryanair = RyanairFalsa([_ida_vuelta("FR", "SVQ", d, p) for d, p in
                            (("PMI", 30), ("RAK", 31), ("BGY", 45), ("BVA", 50), ("OPO", 55), ("MAD", 60), ("LIS", 70))])

    class GoogleFalso:
        def __init__(self):
            self.destinos = []

        def buscar(self, b2, validador):
            self.destinos.append(b2["destino"])
            assert b2["cualquier_destino"] is False and b2["modo"] == "fechas" and b2["fecha_ida"] == "2026-11-13"
            # Google encuentra Lisboa más barato con Iberia... pero Lisboa no está entre los 6 candidatos
            opciones = [_ida_vuelta("IB", "SVQ", "BGY", 20, fuente="google_flights")] if b2["destino"] == "BGY" else []
            return ResultadoFuente(opciones=opciones, peticiones=5)

    google = GoogleFalso()
    top, rechazos, errores, gastadas, bloqueo = cualquier.revisar(b, google, ryanair, AEROLINEAS, None, cupo_google=90)
    assert google.destinos == ["PMI", "RAK", "BGY", "BVA", "OPO", "MAD"]  # los 6 más baratos de Ryanair
    assert gastadas == 30 and bloqueo is None and not errores
    assert [o.ida.destino for o in top] == ["BGY", "PMI", "RAK", "BVA", "OPO"]  # Bérgamo, más barato con Google
    assert top[0].fuente == "google_flights" and len(top) == cualquier.TOP
    resumen = cualquier.resumen_top(top)
    assert resumen[0]["destino"] == "BGY" and resumen[0]["pais"] == "IT" and resumen[0]["fecha_ida"] == "2026-11-13"

    # Sin cupo de Google: solo con Ryanair (y sin gastar consultas)
    google.destinos.clear()
    top, _, _, gastadas, _ = cualquier.revisar(b, google, ryanair, AEROLINEAS, None, cupo_google=5)
    assert google.destinos == [] and gastadas == 0 and [o.ida.destino for o in top][:2] == ["PMI", "RAK"]


def test_cualquier_destino_se_revisa_cada_2_horas():
    from buscador.decision import minutos_hasta_siguiente_revision

    assert minutos_hasta_siguiente_revision(busqueda_cualquiera(), date(2026, 10, 14)) == 120
