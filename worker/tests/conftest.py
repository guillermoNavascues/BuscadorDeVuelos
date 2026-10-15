import pytest


@pytest.fixture(autouse=True)
def sin_pausas_de_ryanair(monkeypatch):
    """Las pausas entre peticiones a Ryanair son para la web de verdad, no para las pruebas."""
    from buscador import cualquier

    monkeypatch.setattr(cualquier, "PAUSA_RYANAIR_S", (0.0, 0.0))
