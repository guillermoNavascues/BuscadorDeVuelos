"""Reintentos de la base de datos ante cortes de red puntuales (visto en el aviso #4: ReadTimeout)."""

import httpx
import pytest

from buscador import db
from buscador.db import Supabase


def _base(respuestas, monkeypatch):
    """Supabase con red simulada: cada elemento es una excepción o un código HTTP."""
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    llamadas = []

    def manejar(peticion):
        llamadas.append(peticion.method)
        r = respuestas[len(llamadas) - 1]
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r, json=[{"id": 1}])

    base = Supabase("https://x.supabase.co", "sb_secret_abc")
    base.http = httpx.Client(transport=httpx.MockTransport(manejar))
    return base, llamadas


def test_reintenta_un_tiempo_agotado_al_leer(monkeypatch):
    base, llamadas = _base([httpx.ReadTimeout("t"), 200], monkeypatch)
    assert base.leer("busquedas") == [{"id": 1}]
    assert llamadas == ["GET", "GET"]


def test_se_rinde_tras_varios_cortes(monkeypatch):
    base, llamadas = _base([httpx.ReadTimeout("t")] * 5, monkeypatch)
    with pytest.raises(httpx.ReadTimeout):
        base.leer("busquedas")
    assert len(llamadas) == db.REINTENTOS


def test_no_repite_un_insertar_que_pudo_llegar(monkeypatch):
    base, llamadas = _base([httpx.ReadTimeout("t"), 201], monkeypatch)
    with pytest.raises(httpx.ReadTimeout):
        base.insertar("avisos", {"a": 1})
    assert llamadas == ["POST"]


def test_repite_un_insertar_si_no_llego_a_conectar(monkeypatch):
    base, llamadas = _base([httpx.ConnectError("c"), 201], monkeypatch)
    base.insertar("avisos", {"a": 1})
    assert llamadas == ["POST", "POST"]


def test_un_error_http_no_se_reintenta(monkeypatch):
    base, llamadas = _base([500, 200], monkeypatch)
    with pytest.raises(RuntimeError):
        base.leer("busquedas")
    assert len(llamadas) == 1
