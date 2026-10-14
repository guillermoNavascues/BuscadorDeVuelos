"""Acceso mínimo a Supabase (API REST de PostgREST) con la clave de servicio del robot."""

from __future__ import annotations

import time

import httpx

REINTENTOS = 3
ESPERA_S = 2.0  # se duplica en cada reintento


class Supabase:
    def __init__(self, url: str, clave_servicio: str):
        # Acepta la URL del proyecto con o sin "/rest/v1" al final
        base = url.strip().rstrip("/")
        if base.endswith("/rest/v1"):
            base = base[: -len("/rest/v1")]
        self.base = base + "/rest/v1"
        cabeceras = {"apikey": clave_servicio, "Content-Type": "application/json"}
        # Las claves nuevas (sb_secret_...) no son JWT y solo van en "apikey";
        # la antigua service_role (JWT) también debe ir como Bearer.
        if not clave_servicio.startswith("sb_"):
            cabeceras["Authorization"] = f"Bearer {clave_servicio}"
        self.http = httpx.Client(headers=cabeceras, timeout=30)

    def _revisar(self, r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {r.request.method} {r.request.url.path}: {r.status_code} {r.text[:300]}")
        return r

    def _pedir(self, metodo: str, url: str, repetible: bool = True, **kwargs) -> httpx.Response:
        """Reintenta los cortes de red puntuales (tiempo agotado, conexión caída). Si la petición no es
        repetible sin riesgo (insertar), solo se repite cuando ni siquiera llegó a conectar."""
        for intento in range(REINTENTOS):
            try:
                return self._revisar(self.http.request(metodo, url, **kwargs))
            except httpx.TransportError as e:
                if intento == REINTENTOS - 1 or not (repetible or isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout))):
                    raise
                time.sleep(ESPERA_S * 2 ** intento)

    def leer(self, tabla: str, **params) -> list[dict]:
        params.setdefault("select", "*")
        return self._pedir("GET", f"{self.base}/{tabla}", params=params).json()

    def insertar(self, tabla: str, filas: dict | list[dict], devolver: bool = False) -> list[dict]:
        cabeceras = {"Prefer": "return=representation" if devolver else "return=minimal"}
        r = self._pedir("POST", f"{self.base}/{tabla}", repetible=False, json=filas, headers=cabeceras)
        return r.json() if devolver else []

    def actualizar(self, tabla: str, filtros: dict, valores: dict) -> None:
        self._pedir("PATCH", f"{self.base}/{tabla}", params=filtros, json=valores)

    def guardar(self, tabla: str, filas: dict | list[dict]) -> None:
        """Inserta o actualiza por clave primaria."""
        cabeceras = {"Prefer": "resolution=merge-duplicates,return=minimal"}
        self._pedir("POST", f"{self.base}/{tabla}", json=filas, headers=cabeceras)

    def rpc(self, funcion: str, **argumentos) -> list[dict]:
        """Llama a una función de la base de datos (p. ej. accesos_desde, que solo permite la clave secreta)."""
        return self._pedir("POST", f"{self.base}/rpc/{funcion}", repetible=False, json=argumentos).json()

    def borrar(self, tabla: str, filtros: dict) -> None:
        """Borra las filas que cumplen los filtros (nunca sin filtros)."""
        if not filtros:
            raise ValueError("borrar() necesita al menos un filtro")
        self._pedir("DELETE", f"{self.base}/{tabla}", params=filtros)
