"""Pruebas del robot con una base de datos y un Telegram simulados (sin red)."""

from datetime import datetime, timedelta, timezone

import pytest

from buscador import run


@pytest.fixture(autouse=True)
def limites_de_telegram_limpios():
    for limite in (run.LIMITE_DESCONOCIDO, run.LIMITE_RESPUESTAS_DESCONOCIDOS, run.LIMITE_VINCULADO,
                   run.LIMITE_AVISOS_ACCESO):
        limite.marcas.clear()


class BaseDeDatosFalsa:
    def __init__(self, tablas):
        self.tablas = tablas
        self.borrados = []

    def rpc(self, funcion, **argumentos):
        """Imita public.accesos_desde (supabase/esquema.sql, v8) sobre la tabla «auditoria»."""
        if funcion != "accesos_desde" or "auditoria" not in self.tablas:
            raise RuntimeError('Supabase POST /rest/v1/rpc/x: 404 {"code":"PGRST202"}')
        desde = datetime.fromisoformat(argumentos["desde"])
        return [dict(e) for e in sorted(self.tablas["auditoria"], key=lambda e: e["created_at"])
                if datetime.fromisoformat(e["created_at"]) > desde
                and e["accion"] not in ("token_refreshed", "token_revoked")][:200]

    @staticmethod
    def _cumple(fila, filtros):
        for campo, condicion in filtros.items():
            if campo in ("select", "order", "limit"):
                continue
            op, _, valor = condicion.partition(".")
            if op == "eq" and str(fila.get(campo)).lower() != valor.lower():
                return False
        return True

    def leer(self, tabla, **filtros):
        return [dict(f) for f in self.tablas.get(tabla, []) if self._cumple(f, filtros)]

    def insertar(self, tabla, filas, devolver=False):
        filas = filas if isinstance(filas, list) else [filas]
        self.tablas.setdefault(tabla, []).extend(dict(f, id=len(self.tablas.get(tabla, [])) + 1) for f in filas)
        return [self.tablas[tabla][-1]] if devolver else []

    def actualizar(self, tabla, filtros, valores):
        for fila in self.tablas.get(tabla, []):
            if self._cumple(fila, filtros):
                fila.update(valores)

    def guardar(self, tabla, fila):
        filas = self.tablas.setdefault(tabla, [])
        filas[:] = [f for f in filas if f.get("clave") != fila.get("clave")] + [fila]

    def borrar(self, tabla, filtros):
        self.borrados.append((tabla, filtros))


class TelegramFalso:
    def __init__(self, mensajes):
        self.mensajes = mensajes
        self.enviados = []

    def mensajes_nuevos(self, desde, espera=0):
        return [m for m in self.mensajes if desde is None or m["update_id"] > desde]

    def enviar(self, chat, texto):
        self.enviados.append((str(chat), texto))
        return True


def _mensaje(update_id, chat, texto):
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": texto}}


def test_vincular_con_codigo_y_responder_comandos():
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_codigo": "ABCD2345", "telegram_chat_id": None}],
        "busquedas": [{"id": "b1", "usuario": "u1", "nombre": "París", "origen": "SVQ", "destino": "ORY",
                       "activa": True, "precio_actual": 315.0, "mejor_precio": 300.0, "estado": "8 opciones"}],
        "ajustes": [],
    })
    tg = TelegramFalso([
        _mensaje(1, 99, "/start abcd2345"),  # enlace del botón de la web: /start CODIGO
        _mensaje(2, 99, "/estado"),
        _mensaje(3, 99, "hola"),
        _mensaje(4, 55, "/start"),  # otra persona que encuentra el bot
    ])
    perfiles = {p["id"]: p for p in db.leer("perfiles")}
    assert run.atender_telegram(db, tg, perfiles, "https://web") == 1
    perfil = db.leer("perfiles")[0]
    assert perfil["telegram_chat_id"] == "99" and perfil["telegram_codigo"] is None
    textos = [t for chat, t in tg.enviados if chat == "99"]
    assert "Listo" in textos[0]
    assert "París" in textos[1] and "315" in textos[1]  # /estado
    assert "/estado" in textos[2]  # ayuda
    assert any(chat == "55" and "código" in t for chat, t in tg.enviados)
    assert db.leer("ajustes", clave="eq.telegram_offset")[0]["valor"] == 4

    # Los mensajes ya leídos no se vuelven a procesar
    tg.enviados.clear()
    run.atender_telegram(db, tg, {p["id"]: p for p in db.leer("perfiles")}, None)
    assert tg.enviados == []


def test_hilo_de_atencion_contesta_y_da_senal_de_vida():
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_codigo": None, "telegram_chat_id": "99", "telegram_prueba": True}],
        "ajustes": [],
    })
    tg = TelegramFalso([_mensaje(1, 99, "/ayuda")])
    atencion = run.Atencion("https://x.supabase.co", "clave", None, "https://web", None)
    ultimo = atencion.vuelta(db, tg, float("-inf"))
    assert ultimo > float("-inf") and db.leer("ajustes", clave="eq.latido")  # señal de vida escrita
    textos = [t for _, t in tg.enviados]
    assert any("Buscador de Vuelos" in t for t in textos) and any("prueba" in t.lower() for t in textos)
    assert db.leer("perfiles")[0]["telegram_prueba"] is False
    # La siguiente vuelta no vuelve a escribir la señal de vida hasta que pase un minuto
    assert atencion.vuelta(db, TelegramFalso([]), ultimo) == ultimo


def test_alarma_de_prueba_desde_la_web(monkeypatch):
    enviadas = []
    monkeypatch.setattr(run, "alarma", lambda tema, titulo, texto, enlace=None: enviadas.append((tema, titulo)) or True)
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_chat_id": "99", "ntfy_tema": "vuelos-secreto123", "alarma_chollos": True,
                      "alarma_prueba": True}],
        "ajustes": [],
    })
    tg = TelegramFalso([])
    run.atender_telegram(db, tg, {p["id"]: p for p in db.leer("perfiles")}, "https://web")
    assert enviadas == [("vuelos-secreto123", "🔔 Prueba de alarma")]
    assert db.leer("perfiles")[0]["alarma_prueba"] is False and "ntfy" in tg.enviados[0][1]


def test_alarma_urgente_con_botones_de_compra():
    from buscador.avisos import alarma, texto_alarma

    class Respuesta:
        status_code = 200

    class Http:
        def post(self, url, json, timeout):
            self.url, self.datos = url, json
            return Respuesta()

    http = Http()
    comprar = [{"texto": "Comprar ya", "url": "https://www.google.com/travel/flights/booking?tfs=x"}]
    assert alarma("vuelos-abc", "🔥 Chollo encontrado", texto_alarma({"nombre": "Escapada a París"}, 70.0),
                  enlace="https://web/#/busqueda/1", comprar=comprar, http=http)
    assert http.url == "https://ntfy.sh/" and http.datos["topic"] == "vuelos-abc" and http.datos["priority"] == 5
    assert "70,00 €" in http.datos["message"] and http.datos["click"].endswith("/busqueda/1")
    assert http.datos["actions"][0]["label"] == "Comprar ya"
    assert alarma("", "x", "y", http=http) is False  # sin tema no se envía nada
    Respuesta.status_code = 429
    assert alarma("vuelos-abc", "x", "y", http=http) is False


def test_mensaje_de_prueba_desde_la_web():
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_chat_id": "99", "telegram_prueba": True}],
        "ajustes": [],
    })
    tg = TelegramFalso([])
    run.atender_telegram(db, tg, {p["id"]: p for p in db.leer("perfiles")}, None)
    assert tg.enviados and "prueba" in tg.enviados[0][1].lower()
    assert db.leer("perfiles")[0]["telegram_prueba"] is False


def test_migracion_de_ritmo_se_aplica_una_vez():
    db = BaseDeDatosFalsa({
        "estado_fuentes": [{"fuente": "google_flights", "intervalo_min": 140}, {"fuente": "ryanair", "intervalo_min": 380}],
        "ajustes": [],
    })
    run.migrar_datos(db)
    assert {f["fuente"]: f["intervalo_min"] for f in db.leer("estado_fuentes")} == {"google_flights": 2, "ryanair": 10}
    assert db.leer("estado_fuentes", fuente="eq.ryanair")[0]["max_peticiones"] == 1
    db.actualizar("estado_fuentes", {"fuente": "eq.google_flights"}, {"intervalo_min": 77})  # cambio manual
    run.migrar_datos(db)
    assert db.leer("estado_fuentes", fuente="eq.google_flights")[0]["intervalo_min"] == 77  # no se pisa


def test_limpieza_solo_borra_opciones_antiguas_no_ganadoras():
    db = BaseDeDatosFalsa({})
    run.limpiar_historial(db, datetime(2026, 10, 10, tzinfo=timezone.utc))
    precios = dict(db.borrados)["precios"]
    assert precios["es_mejor"] == "eq.false"  # el historial de la gráfica (es_mejor) no se toca
    assert precios["revisado"].startswith("lt.2026-10-08")


def test_ronda_sin_nada_pendiente_no_hace_nada():
    futuro = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    db = BaseDeDatosFalsa({"busquedas": [{"id": "b1", "activa": True, "modo": "fechas", "fecha_ida": "2099-01-01",
                                          "proxima_revision": futuro}]})
    assert run.ronda(db, None, None, forzar=False, limite_s=60) is None
    assert "ejecuciones" not in db.tablas  # no se apunta una ronda vacía


def test_busqueda_nueva_no_espera_al_ritmo_normal_de_la_web():
    ahora = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    hace = lambda minutos: (ahora - timedelta(minutes=minutos)).isoformat()  # noqa: E731
    config = {
        "google_flights": {"activa": True, "intervalo_min": 5, "ultima_ronda": hace(3), "bloqueada_hasta": None},
        "ryanair": {"activa": True, "intervalo_min": 30, "ultima_ronda": hace(1), "bloqueada_hasta": None},
        "skyscanner": {"activa": True, "intervalo_min": 740, "ultima_ronda": hace(10),
                       "bloqueada_hasta": (ahora + timedelta(hours=1)).isoformat()},
    }
    vieja = {"ultima_revision": hace(40), "historial_desde": None}
    nueva = {"ultima_revision": None, "historial_desde": None}
    editada = {"ultima_revision": hace(40), "historial_desde": hace(1)}
    # Solo búsquedas ya revisadas: cada web va a su ritmo (Google se miró hace 3 min y va cada 5)
    assert run.fuentes_listas(config, [vieja], ahora, forzar=False) == []
    # Una nueva o recién editada: Google ya vale (más de 2 min); Ryanair (1 min) y la bloqueada, no
    assert run.fuentes_listas(config, [vieja, nueva], ahora, forzar=False) == ["google_flights"]
    assert run.fuentes_listas(config, [editada], ahora, forzar=False) == ["google_flights"]
    assert not run.es_nueva(vieja) and run.es_nueva(nueva) and run.es_nueva(editada)


def test_horario_solo_telegram_para_la_alarma():
    from buscador.avisos import alarma_en_pausa

    madrid = lambda d, h, m=0: datetime(2026, 10, d, h, m, tzinfo=timezone(timedelta(hours=2)))  # 12/10/2026 = lunes
    base = {"ntfy_pausa": True, "ntfy_pausa_desde": "09:00:00", "ntfy_pausa_hasta": "14:00:00",
            "ntfy_pausa_dias": [1, 2, 3, 4, 5], "zona_horaria": "Europe/Madrid"}
    assert alarma_en_pausa(base, madrid(12, 10)) is True          # lunes 10:00
    assert alarma_en_pausa(base, madrid(12, 14)) is False         # a las 14:00 ya suena
    assert alarma_en_pausa(base, madrid(12, 8, 59)) is False
    assert alarma_en_pausa(base, madrid(11, 10)) is False         # domingo: no está entre los días
    assert alarma_en_pausa({**base, "ntfy_pausa": False}, madrid(12, 10)) is False
    # Las horas son las de su zona, aunque el robot trabaje en UTC
    assert alarma_en_pausa(base, datetime(2026, 10, 12, 7, 30, tzinfo=timezone.utc)) is True  # 9:30 en Madrid
    assert alarma_en_pausa({**base, "zona_horaria": "Atlantic/Canary"},
                           datetime(2026, 10, 12, 7, 30, tzinfo=timezone.utc)) is False      # 8:30 en Canarias
    assert alarma_en_pausa({**base, "zona_horaria": "Marte/Base"}, madrid(12, 10)) is True  # zona rara: España

    # De noche, pasando de medianoche: cuenta el día en que empieza
    noche = {**base, "ntfy_pausa_desde": "23:00", "ntfy_pausa_hasta": "08:00"}
    assert alarma_en_pausa(noche, madrid(16, 23, 30)) is True     # viernes noche
    assert alarma_en_pausa(noche, madrid(17, 7)) is True          # sábado de madrugada (empezó el viernes)
    assert alarma_en_pausa(noche, madrid(18, 7)) is False         # domingo de madrugada (empezó el sábado)
    assert alarma_en_pausa(noche, madrid(13, 7)) is True          # martes de madrugada (empezó el lunes)
    assert alarma_en_pausa(noche, madrid(13, 12)) is False
    assert alarma_en_pausa({**base, "ntfy_pausa_hasta": "09:00"}, madrid(11, 3)) is False  # domingo
    assert alarma_en_pausa({**base, "ntfy_pausa_hasta": "09:00"}, madrid(12, 3)) is True   # lunes: todo el día
    assert alarma_en_pausa({**base, "ntfy_pausa_dias": []}, madrid(12, 10)) is False


def test_en_horario_solo_telegram_avisa_por_telegram_sin_alarma(monkeypatch):
    from collections import Counter

    from test_logica import busqueda, opcion_directa

    from buscador.decision import Decision

    alarmas = []
    monkeypatch.setattr(run, "alarma", lambda *a, **k: alarmas.append(a) or True)
    monkeypatch.setattr(run, "decidir", lambda *a, **k: Decision(True, "chollo", "🔥 ¡Chollo encontrado! −40 %", "x", True))
    perfil = {"id": "u1", "telegram_chat_id": "99", "ntfy_tema": "vuelos-secreto123", "alarma_chollos": True,
              "ntfy_pausa": True, "ntfy_pausa_desde": "00:00", "ntfy_pausa_hasta": "00:00", "ntfy_pausa_dias": [1, 2, 3, 4, 5, 6, 7]}
    for pausa, esperadas in ((True, 0), (False, 1)):
        db, tg = BaseDeDatosFalsa({"busquedas": [busqueda()], "precios": [], "avisos": []}), TelegramFalso([])
        ahora, op = datetime.now(timezone.utc), opcion_directa()
        op.precio_total = 120.0
        run.procesar_busqueda(db, db.leer("busquedas")[0], [op], Counter(), [], ["google"],
                              {**perfil, "ntfy_pausa": pausa}, {}, tg, None, ahora.date(), ahora)
        assert len(tg.enviados) == 1 and ("en pausa" in tg.enviados[0][1]) is pausa
        assert len(alarmas) == esperadas
        alarmas.clear()


def test_el_bot_limita_a_los_desconocidos():
    db = BaseDeDatosFalsa({"perfiles": [{"id": "u1", "telegram_codigo": "ABCD2345", "telegram_chat_id": None}], "ajustes": []})
    # Alguien prueba códigos al azar: tras 5 intentos en una hora se le ignora, aunque luego acierte
    tg = TelegramFalso([_mensaje(i, 555, f"/start ZZZZ{i:04d}") for i in range(1, 8)] + [_mensaje(8, 555, "/start ABCD2345")])
    assert run.atender_telegram(db, tg, {p["id"]: p for p in db.leer("perfiles")}, None) == 0
    assert len(tg.enviados) == 5
    assert db.leer("perfiles")[0]["telegram_chat_id"] is None
    # Pasada la hora puede volver a intentarlo
    limite = run.Limitador(2, 60)
    assert limite.permitir("x", 0) and limite.permitir("x", 1) and not limite.permitir("x", 2)
    assert limite.permitir("x", 61)


def test_enlaces_de_telegram_seguros():
    from buscador.avisos import _href, es_https

    assert es_https("https://www.iberia.com") and not es_https("javascript:alert(1)") and not es_https("http://x.com")
    assert not es_https('https://x.com/"><b>')
    assert _href('https://x.com/?a="b"&c=<d>') == "https://x.com/?a=&quot;b&quot;&amp;c=&lt;d&gt;"


T0 = datetime(2026, 10, 9, 11, 0, tzinfo=timezone.utc)  # 13:00 en Madrid


def _acceso(minutos, accion, ip):
    return {"created_at": (T0 + timedelta(minutes=minutos)).isoformat(), "accion": accion, "ip_address": ip}


def _registro(caplog):
    return " ".join(r.getMessage() for r in caplog.records)


def test_avisos_de_acceso_por_telegram(caplog):
    caplog.set_level("INFO", logger="buscador")
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_chat_id": "99"}],
        "ajustes": [],
        "auditoria": [_acceso(-60 * 24 * 10, "login", "198.51.100.1"), _acceso(-60 * 24 * 40, "login", "192.0.2.200")],
    })
    tg = TelegramFalso([])
    perfiles = {p["id"]: p for p in db.leer("perfiles")}

    # Primera vez: no avisa de lo anterior; las IPs de los últimos 30 días cuentan como conocidas
    assert run.avisar_accesos(db, tg, perfiles, ahora=T0) == 0
    assert len(tg.enviados) == 1 and "activados" in tg.enviados[0][1] and "1 inicio de sesión desde 1 IP " in tg.enviados[0][1]
    assert db.leer("ajustes", clave="eq.accesos_ips")[0]["valor"] == ["198.51.100.1"]
    assert db.leer("ajustes", clave="eq.accesos_desde")[0]["valor"] == T0.isoformat()

    # Entras tú desde tu IP de siempre y alguien desde otra; las renovaciones de sesión y salir no avisan
    tg.enviados.clear()
    db.tablas["auditoria"] += [
        _acceso(1, "token_refreshed", "198.51.100.1"), _acceso(1, "token_revoked", "198.51.100.1"),
        _acceso(2, "login", "198.51.100.1"), _acceso(3, "login", "203.0.113.7"), _acceso(4, "logout", "203.0.113.7"),
    ]
    assert run.avisar_accesos(db, tg, perfiles) == 2
    (chat1, tuyo), (chat2, otro) = tg.enviados
    assert chat1 == chat2 == "99"
    assert "Inicio de sesión" in tuyo and "13:02:00 (hora de Madrid)" in tuyo and "ya habías entrado" in tuyo
    assert "IP 203.0.113.7" in otro and "nueva" in otro and "Cambiar contraseña" in otro
    assert db.leer("ajustes", clave="eq.accesos_desde")[0]["valor"] == _acceso(4, "", "")["created_at"]  # pasa el logout
    assert db.leer("ajustes", clave="eq.accesos_ips")[0]["valor"] == ["203.0.113.7", "198.51.100.1"]

    # Nada nuevo: nada que enviar
    tg.enviados.clear()
    assert run.avisar_accesos(db, tg, perfiles) == 0 and tg.enviados == []

    # El registro de GitHub es público: solo recuentos, ni IPs ni chats
    registro = _registro(caplog)
    assert "2 aviso(s)" in registro and "1 desde IP nueva" in registro
    assert not any(dato in registro for dato in ("198.51.100", "203.0.113", "192.0.2", "99 ", "13:0"))


def test_avisos_de_acceso_agrupados_y_con_limite_por_hora():
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_chat_id": "99"}],
        "ajustes": [{"clave": "accesos_desde", "valor": T0.isoformat()}, {"clave": "accesos_ips", "valor": ["198.51.100.1"]}],
        "auditoria": [_acceso(1 + i * 0.1, "user_recovery_requested", f"192.0.2.{i}") for i in range(11)]
                     + [_acceso(3, "login", "192.0.2.10")],
    })
    tg = TelegramFalso([])
    perfiles = {p["id"]: p for p in db.leer("perfiles")}

    # Muchos seguidos: un solo mensaje con la lista (los 10 últimos) y el resumen
    assert run.avisar_accesos(db, tg, perfiles) == 1
    texto = tg.enviados[0][1]
    assert "12 accesos seguidos" in texto and "(y 2 anteriores)" in texto and "12 desde IP nueva" in texto
    assert texto.count("\n• ") == 10 and "Petición para recuperar la contraseña" in texto
    # Pedir recuperar la contraseña no hace «conocida» la IP; entrar, sí
    assert db.leer("ajustes", clave="eq.accesos_ips")[0]["valor"] == ["192.0.2.10", "198.51.100.1"]

    # Máximo de mensajes por hora: lo que no cabe espera (la marca no avanza) y luego llega agrupado
    marca = lambda: db.leer("ajustes", clave="eq.accesos_desde")[0]["valor"]  # noqa: E731
    for _ in range(4):
        assert run.LIMITE_AVISOS_ACCESO.permitir("accesos")  # con el mensaje anterior, 5 de 6 esta hora
    db.tablas["auditoria"] += [_acceso(10 + i, "login", "198.51.100.1") for i in range(3)]
    tg.enviados.clear()
    assert run.avisar_accesos(db, tg, perfiles) == 1  # el sexto mensaje de la hora: solo el primero de los 3
    assert run.avisar_accesos(db, tg, perfiles) == 0  # ya no caben más esta hora
    assert len(tg.enviados) == 1 and marca() == _acceso(10, "", "")["created_at"]
    db.tablas["auditoria"] += [_acceso(20 + i, "login", "198.51.100.1") for i in range(2)]  # siguen entrando
    run.LIMITE_AVISOS_ACCESO.marcas.clear()  # pasa la hora
    assert run.avisar_accesos(db, tg, perfiles) == 1 and "4 accesos seguidos" in tg.enviados[-1][1]
    assert marca() == _acceso(21, "", "")["created_at"]


def test_avisos_de_acceso_no_se_pierden_si_telegram_falla_o_no_hay_chat():
    db = BaseDeDatosFalsa({
        "perfiles": [{"id": "u1", "telegram_chat_id": None}],
        "ajustes": [{"clave": "accesos_desde", "valor": T0.isoformat()}, {"clave": "accesos_ips", "valor": []}],
        "auditoria": [_acceso(1, "login", "203.0.113.7")],
    })
    tg = TelegramFalso([])
    # Sin chat vinculado: espera (si alguien desvincula Telegram desde la web, al volver a vincularlo te enteras)
    assert run.avisar_accesos(db, tg, {p["id"]: p for p in db.leer("perfiles")}) == 0 and tg.enviados == []
    assert db.leer("ajustes", clave="eq.accesos_desde")[0]["valor"] == T0.isoformat()
    # Telegram no responde: tampoco avanza
    db.actualizar("perfiles", {"id": "eq.u1"}, {"telegram_chat_id": "99"})
    perfiles = {p["id"]: p for p in db.leer("perfiles")}
    tg.enviar = lambda chat, texto: False
    assert run.avisar_accesos(db, tg, perfiles) == 0
    assert db.leer("ajustes", clave="eq.accesos_desde")[0]["valor"] == T0.isoformat()
    # Vuelve Telegram: llega el aviso pendiente
    tg = TelegramFalso([])
    assert run.avisar_accesos(db, tg, perfiles) == 1 and "203.0.113.7" in tg.enviados[0][1]


def test_sin_la_version_8_del_sql_telegram_sigue_atendiendo(caplog):
    caplog.set_level("INFO", logger="buscador")
    db = BaseDeDatosFalsa({"perfiles": [{"id": "u1", "telegram_chat_id": "99"}], "ajustes": []})  # sin accesos_desde
    atencion = run.Atencion("https://x.supabase.co", "clave", None, None, None)
    tg = TelegramFalso([_mensaje(1, 99, "/ayuda")])
    atencion.vuelta(db, tg, float("-inf"))
    atencion.vuelta(db, tg, float("-inf"))
    assert any("/estado" in t for _, t in tg.enviados)  # contesta igual
    avisos = [r.getMessage() for r in caplog.records if "Avisos de acceso" in r.getMessage()]
    assert len(avisos) == 1 and "versión 8" in avisos[0]  # se avisa una vez, no cada minuto
    # Instalada la versión 8, la siguiente vuelta del minuto activa los avisos
    db.tablas["auditoria"] = []
    atencion.vuelta(db, TelegramFalso([]), float("-inf"))
    assert db.leer("ajustes", clave="eq.accesos_desde") and atencion.fallo_accesos is None


def test_mensaje_de_acceso_con_hora_de_madrid_y_html_seguro():
    from buscador.avisos import mensaje_accesos

    texto = mensaje_accesos([{"created_at": "2026-12-01T08:05:09.12345+00:00", "accion": "user_updated_password",
                              "ip_address": "<b>", "nueva": True}])
    assert "Contraseña cambiada" in texto and "09:05:09 (hora de Madrid)" in texto  # en invierno, UTC+1
    assert "&lt;b&gt;" in texto and "<b>nueva</b>" in texto
    assert "evento sin tipo" in mensaje_accesos([{"created_at": "2026-12-01T08:05:09+00:00", "accion": None, "ip_address": ""}])


def test_aviso_por_telegram_al_bloquear_y_al_recuperarse(monkeypatch):
    ahora = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(run, "INICIO_SESION", ahora - timedelta(hours=2))
    monkeypatch.setattr(run, "REGISTRO_PETICIONES", {"google_flights": [
        (ahora - timedelta(minutes=90), 30), (ahora - timedelta(minutes=40), 25), (ahora - timedelta(minutes=5), 12)]})
    tg = TelegramFalso([])
    cfg = {"fuente": "google_flights", "bloqueos_seguidos": 0, "ultima_ok": (ahora - timedelta(minutes=25)).isoformat(),
           "ultima_ronda": (ahora - timedelta(minutes=25)).isoformat()}
    est = {"bloqueo": "Google Flights ha respondido con su página de tráfico inusual https://www.google.com/sorry/x",
           "peticiones": 12, "errores": []}
    cambios = {"bloqueos_seguidos": 1, "bloqueada_hasta": (ahora + timedelta(minutes=60)).isoformat()}
    run.avisar_estado_fuente(tg, ["99"], "Google Flights", cfg, est, cambios, ahora, 4)
    texto = tg.enviados[0][1]
    assert tg.enviados[0][0] == "99" and "ha frenado al robot" in texto
    assert "37 en la última hora" in texto and "67 en esta sesión" in texto and "2 h 00 min" in texto
    assert "máximo 90 consultas por hora" in texto
    assert "hace 25 min" in texto and "descansa 1 h 00 min" in texto and "hasta las 13:00" in texto  # hora de Madrid (UTC+2 en octubre)
    assert "Primer bloqueo" in texto and "sorry" not in texto  # sin direcciones
    run.avisar_estado_fuente(tg, ["99"], "Google Flights", cfg, {**est, "bloqueo_busqueda": "Puente en París"}, cambios, ahora, 4)
    assert "Pasó al buscar: «Puente en París»" in tg.enviados[-1][1]
    tg.enviados.pop()

    # Cuando vuelve a responder, otro mensaje con lo que ha durado la pausa
    tg.enviados.clear()
    run.avisar_estado_fuente(tg, ["99"], "Google Flights", {**cfg, "bloqueos_seguidos": 1, "ultima_ronda": ahora.isoformat()},
                             {"bloqueo": None, "peticiones": 8, "errores": []}, {}, ahora + timedelta(minutes=75), 4)
    assert "vuelve a responder" in tg.enviados[0][1] and "1 h 15 min" in tg.enviados[0][1]

    # Funcionando normal: ningún mensaje; y sin Telegram vinculado, tampoco
    tg.enviados.clear()
    run.avisar_estado_fuente(tg, ["99"], "Google Flights", cfg, {"bloqueo": None, "peticiones": 8, "errores": []}, {}, ahora, 4)
    run.avisar_estado_fuente(tg, [], "Google Flights", cfg, est, cambios, ahora, 4)
    assert tg.enviados == []


def test_busqueda_sin_tiempo_queda_en_cola_con_el_motivo(monkeypatch):
    ahora = datetime.now(timezone.utc)

    def base(google_bloqueada_hasta):
        fuente = {"activa": True, "bloqueos_seguidos": 0, "ultima_ronda": None, "max_peticiones": 60,
                  "pausa_min_s": 6, "pausa_max_s": 16, "intervalo_min": 2}
        return BaseDeDatosFalsa({
            "busquedas": [{"id": "b1", "usuario": "u1", "nombre": "París", "activa": True, "modo": "fechas",
                           "ida_vuelta": True, "fecha_ida": "2027-01-10", "fecha_vuelta": "2027-01-12", "info": {},
                           "proxima_revision": (ahora + timedelta(minutes=57)).isoformat()}],  # con "Forzar" entra igual
            "estado_fuentes": [{**fuente, "fuente": "google_flights", "nombre": "Google Flights",
                                "bloqueada_hasta": google_bloqueada_hasta},
                               {**fuente, "fuente": "ryanair", "nombre": "Ryanair", "bloqueada_hasta": None}],
            "aerolineas": [], "perfiles": [], "ejecuciones": [],
        })

    monkeypatch.setattr(run, "crear_fuentes", lambda nombres, config, aerolineas: {n: None for n in nombres})
    monkeypatch.setattr(run, "consultar", lambda fuentes, tareas, validadores, config, limite_s: (
        {}, {n: {"bloqueo": None, "errores": [], "busquedas": 0, "peticiones": 0} for n in fuentes}))

    # Google frenado: la búsqueda espera y la web dice hasta cuándo
    db = base((ahora + timedelta(minutes=40)).isoformat())
    run.ronda(db, None, None, forzar=True, limite_s=60)
    b = db.leer("busquedas")[0]
    assert b["estado"].startswith("En espera: Google Flights ha frenado al robot; vuelve a probar a las")
    assert b["proxima_revision"] <= datetime.now(timezone.utc).isoformat()  # en cola, no dentro de 57 min

    # Sin bloqueo, simplemente no dio tiempo: en cola para la siguiente vuelta
    db = base(None)
    run.ronda(db, None, None, forzar=True, limite_s=60)
    b = db.leer("busquedas")[0]
    assert b["estado"].startswith("En cola") and b["proxima_revision"] <= datetime.now(timezone.utc).isoformat()


def test_maximo_de_consultas_a_google_por_hora_y_pausa_corta(monkeypatch):
    ahora = datetime.now(timezone.utc)
    fuente = {"activa": True, "bloqueos_seguidos": 0, "ultima_ronda": None, "bloqueada_hasta": None, "intervalo_min": 2,
              "pausa_min_s": 15, "pausa_max_s": 30}

    def base(consultas_ultima_hora):
        return BaseDeDatosFalsa({
            "busquedas": [{"id": "b1", "usuario": "u1", "nombre": "París", "activa": True, "modo": "fechas", "ida_vuelta": True,
                           "fecha_ida": "2027-01-10", "fecha_vuelta": "2027-01-12", "info": {},
                           "proxima_revision": (ahora - timedelta(minutes=5)).isoformat()}],
            "estado_fuentes": [{**fuente, "fuente": "google_flights", "nombre": "Google Flights", "max_peticiones": 60}],
            "aerolineas": [], "perfiles": [],
            "ejecuciones": [{"id": 1, "inicio": (ahora - timedelta(minutes=30)).isoformat(),
                             "resumen": {"fuentes": {"google_flights": {"peticiones": consultas_ultima_hora}}}}],
        })

    usadas = {}

    def consultar(fuentes, tareas, validadores, config, limite_s):
        usadas["fuentes"] = list(fuentes)
        usadas["max"] = {n: config[n]["max_peticiones"] for n in fuentes}
        bloqueo = "Google devuelve páginas sin vuelos una y otra vez: el robot hace una pausa" if usadas.get("bloquear") else None
        return {}, {n: {"bloqueo": bloqueo, "errores": [], "busquedas": 0, "peticiones": config[n]["max_peticiones"]}
                    for n in fuentes}

    monkeypatch.setattr(run, "crear_fuentes", lambda nombres, config, aerolineas: {n: None for n in nombres})
    monkeypatch.setattr(run, "consultar", consultar)

    # Con 88 consultas en la última hora no cabe otra revisión: Google no se consulta y la búsqueda espera en cola
    db = base(88)
    assert run.ronda(db, None, None, forzar=False, limite_s=60) is None
    assert db.leer("busquedas")[0]["estado"].startswith("En cola: el robot reparte las consultas a Google")
    # Con 50, sí, pero sin pasar del máximo (90 - 50 = 40 en esta vuelta)
    db = base(50)
    run.ronda(db, None, None, forzar=False, limite_s=60)
    assert usadas["fuentes"] == ["google_flights"] and usadas["max"]["google_flights"] == 40
    # Si no le da para la búsqueda, queda en cola explicando por qué
    assert db.leer("busquedas")[0]["estado"].startswith("En cola: el robot reparte las consultas a Google")

    # Páginas sin vuelos: la primera pausa es de 20 min (antes, 1 hora)
    usadas["bloquear"] = True
    db = base(0)
    run.ronda(db, None, None, forzar=False, limite_s=60)
    hasta = datetime.fromisoformat(db.leer("estado_fuentes")[0]["bloqueada_hasta"])
    assert timedelta(minutes=19) < hasta - ahora < timedelta(minutes=21)


def test_la_busqueda_con_la_que_falla_google_va_al_final_de_la_cola(monkeypatch):
    ahora = datetime.now(timezone.utc)
    fuente = {"activa": True, "bloqueos_seguidos": 0, "ultima_ronda": None, "bloqueada_hasta": None, "intervalo_min": 2,
              "pausa_min_s": 15, "pausa_max_s": 30, "max_peticiones": 60}
    busquedas = [{"id": i, "usuario": "u1", "nombre": i, "activa": True, "modo": "fechas", "ida_vuelta": True,
                  "fecha_ida": "2027-01-10", "fecha_vuelta": "2027-01-12", "info": {},
                  "proxima_revision": (ahora - timedelta(minutes=m)).isoformat()} for i, m in (("mala", 30), ("otra", 5))]
    db = BaseDeDatosFalsa({"busquedas": busquedas, "aerolineas": [], "perfiles": [], "ejecuciones": [],
                           "estado_fuentes": [{**fuente, "fuente": "google_flights", "nombre": "Google Flights"}]})
    monkeypatch.setattr(run, "crear_fuentes", lambda nombres, config, aerolineas: {n: None for n in nombres})
    monkeypatch.setattr(run, "consultar", lambda fuentes, tareas, validadores, config, limite_s: ({}, {
        "google_flights": {"bloqueo": "Google devuelve páginas sin vuelos una y otra vez", "bloqueo_en": "mala",
                           "bloqueo_busqueda": "mala", "errores": [], "busquedas": 0, "peticiones": 9}}))
    run.ronda(db, None, None, forzar=False, limite_s=60)
    mala, otra = (db.leer("busquedas", id=f"eq.{i}")[0] for i in ("mala", "otra"))
    assert mala["proxima_revision"] > otra["proxima_revision"]  # la de la falla, al final de la cola
    assert mala["estado"].startswith("Google no devolvió vuelos al buscar esta")
    assert otra["estado"].startswith("En espera: Google Flights ha frenado al robot")


# ---------------- autoarreglo y actualización sola ----------------

class GitHubFalso:
    def __init__(self, abierto=False, ultimo="nuevo", archivos=("worker/buscador/run.py",)):
        self.repo, self.abierto, self.ultimo, self.archivos = "yo/robot", abierto, ultimo, list(archivos)
        self.avisos, self.lanzados = [], []

    def hay_aviso_abierto(self):
        return self.abierto

    def abrir_aviso(self, titulo, cuerpo):
        self.avisos.append((titulo, cuerpo))
        return {"number": 7, "html_url": "https://github.com/yo/robot/issues/7"}

    def lanzar_arreglo(self, numero, rama):
        self.lanzados.append((numero, rama))
        return True

    def ultimo_commit(self, rama):
        return self.ultimo

    def archivos_cambiados(self, desde, hasta):
        return self.archivos


def test_autoarreglo_abre_aviso_sin_datos_personales_y_como_mucho_cada_12_horas():
    from buscador import autoarreglo

    b = {"id": "b1", "nombre": "Puente en París", "modo": "fechas", "ida_vuelta": True, "origen": "SVQ", "destino": "ORY",
         "fecha_ida": "2027-01-10", "fecha_vuelta": "2027-01-12", "flex_dias": 2, "fechas_extra": [{"ida": "2027-01-20"}],
         "escalas_max": 1, "ida_salida_min": 6}
    forma = autoarreglo.forma_busqueda(b)
    assert "±2 días" in forma and "1 fecha(s) alternativa(s)" in forma and "con franjas horarias" in forma
    assert not any(dato in forma for dato in ("París", "SVQ", "ORY", "2027"))  # el repositorio es público

    db, gh, telegram = BaseDeDatosFalsa({"ajustes": []}), GitHubFalso(), []
    ahora = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    problemas = [f"Una búsqueda ({forma}) no se ha podido consultar en 3 revisiones seguidas"]
    assert autoarreglo.pedir_arreglo(db, gh, telegram.append, problemas, ahora, 40) is True
    titulo, cuerpo = gh.avisos[0]
    assert titulo.startswith("Autoarreglo:") and "40" in cuerpo and "París" not in cuerpo
    assert gh.lanzados == [(7, "main")] and "issues/7" in telegram[0]
    # A las 6 horas no se vuelve a pedir; a las 13, sí (si no queda otro aviso abierto)
    assert autoarreglo.pedir_arreglo(db, gh, telegram.append, problemas, ahora + timedelta(hours=6), 40) is False
    gh.abierto = True
    assert autoarreglo.pedir_arreglo(db, gh, telegram.append, problemas, ahora + timedelta(hours=13), 40) is False
    gh.abierto = False
    assert autoarreglo.pedir_arreglo(db, gh, telegram.append, problemas, ahora + timedelta(hours=13), 40) is True
    # Fuera de GitHub (en tu PC) no hace nada
    assert autoarreglo.pedir_arreglo(db, None, telegram.append, problemas, ahora + timedelta(days=2), 40) is False


def test_una_busqueda_que_falla_tres_veces_seguidas_pide_el_autoarreglo():
    from collections import Counter

    from test_logica import busqueda

    db = BaseDeDatosFalsa({"busquedas": [busqueda()], "precios": [], "avisos": []})
    problemas = []
    ahora = datetime.now(timezone.utc)
    for _ in range(3):
        b = db.leer("busquedas")[0]
        run.procesar_busqueda(db, b, [], Counter(), [], ["google_flights"], None, {}, None, None, ahora.date(), ahora,
                              ["Google ha devuelto una página sin vuelos"], problemas=problemas)
    assert db.leer("busquedas")[0]["info"]["fallos_seguidos"] == 3
    assert len(problemas) == 1 and "3 revisiones seguidas" in problemas[0] and "prueba" not in problemas[0]


def test_actualizacion_sola_con_una_version_nueva(tmp_path, monkeypatch):
    from buscador import autoarreglo

    assert autoarreglo.hay_version_nueva(GitHubFalso(), "viejo", "main") is True
    assert autoarreglo.hay_version_nueva(GitHubFalso(ultimo="viejo"), "viejo", "main") is False  # ya es la última
    assert autoarreglo.hay_version_nueva(GitHubFalso(archivos=["web/js/app.js"]), "viejo", "main") is False  # solo la web
    assert autoarreglo.hay_version_nueva(None, "viejo", "main") is False
    fichero = tmp_path / "entorno"
    monkeypatch.setenv("GITHUB_ENV", str(fichero))
    autoarreglo.marcar_actualizacion()
    assert fichero.read_text() == "ACTUALIZACION=1" + chr(10)


def test_donde_dice_el_sitio_del_fallo_sin_su_texto():
    try:
        {}["Puente en París"]
    except KeyError as e:
        texto = run._donde(e)
    assert texto.startswith("KeyError en test_robot.py:") and "París" not in texto
