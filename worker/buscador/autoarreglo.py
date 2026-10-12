"""Arreglo automático y actualización sola del robot (solo funciona dentro de GitHub Actions).

- Si el robot ve un fallo que se repite, abre un aviso (issue) en el repositorio con los datos técnicos y lanza
  el flujo "Autoarreglo del robot": Claude investiga, prepara el arreglo y abre una propuesta de cambio
  (pull request) que apruebas tú. Como mucho uno cada 12 h y nunca con otro abierto (gasta de tu plan de Claude).
- Cada 10 min mira si hay una versión nueva del robot en GitHub (p. ej. un arreglo que acabas de aprobar):
  si la hay, termina la sesión y la siguiente arranca ya con ella. Así no hace falta reiniciarlo a mano.

El repositorio es público: los avisos llevan solo datos técnicos (ni rutas, ni fechas, ni precios, ni nombres).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import httpx

from .viaje import es_varios_destinos, tramos_viaje

log = logging.getLogger(__name__)

API = "https://api.github.com"
ETIQUETA = "autoarreglo"
FLUJO = "autoarreglo.yml"
CADA = timedelta(hours=12)
# Lo que hace falta para que una versión nueva reinicie el robot (los cambios de la web no lo necesitan)
RUTAS_ROBOT = ("worker/", ".github/workflows/robot.yml")


class GitHub:
    """Lo justo de la API de GitHub, con el token de la propia ejecución (GITHUB_TOKEN)."""

    def __init__(self, repo: str, token: str, http=None):
        self.repo = repo
        self.http = http or httpx.Client(timeout=20, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    @classmethod
    def desde_entorno(cls) -> GitHub | None:
        repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
        return cls(repo, token) if repo and token else None

    def hay_aviso_abierto(self) -> bool:
        r = self.http.get(f"{API}/repos/{self.repo}/issues", params={"labels": ETIQUETA, "state": "open", "per_page": 1})
        return r.status_code == 200 and bool(r.json())

    def abrir_aviso(self, titulo: str, cuerpo: str) -> dict | None:
        r = self.http.post(f"{API}/repos/{self.repo}/issues", json={"title": titulo, "body": cuerpo, "labels": [ETIQUETA]})
        return r.json() if r.status_code == 201 else None

    def lanzar_arreglo(self, numero: int, rama: str) -> bool:
        r = self.http.post(f"{API}/repos/{self.repo}/actions/workflows/{FLUJO}/dispatches",
                           json={"ref": rama, "inputs": {"aviso": str(numero)}})
        return r.status_code == 204

    def ultimo_commit(self, rama: str) -> str | None:
        r = self.http.get(f"{API}/repos/{self.repo}/commits/{rama}")
        return r.json().get("sha") if r.status_code == 200 else None

    def archivos_cambiados(self, desde: str, hasta: str) -> list[str]:
        r = self.http.get(f"{API}/repos/{self.repo}/compare/{desde}...{hasta}")
        return [f["filename"] for f in r.json().get("files", [])] if r.status_code == 200 else []


# ----------------------------------------------------------------------------------------
# Qué se cuenta en el aviso (sin datos personales: el repositorio es público)
# ----------------------------------------------------------------------------------------
def forma_busqueda(b: dict) -> str:
    """Cómo es una búsqueda, sin decir cuál es: "fechas concretas, ida y vuelta, ±2 días, 1 fecha alternativa"."""
    partes = ["chollo (cualquier fecha de un periodo)" if b.get("modo") == "chollo" else "fechas concretas"]
    if es_varios_destinos(b):
        partes.append(f"varios destinos ({len(tramos_viaje(b))} vuelos)")
    else:
        partes.append("ida y vuelta" if b.get("ida_vuelta") else "solo ida")
    if b.get("flex_dias"):
        partes.append(f"±{b['flex_dias']} días")
    if b.get("fechas_extra"):
        partes.append(f"{len(b['fechas_extra'])} fecha(s) alternativa(s)")
    if b.get("origenes_extra"):
        partes.append(f"{len(b['origenes_extra']) + 1} aeropuertos de salida")
    franjas = any(b.get(f"{s}_{c}_{x}") not in (None, 0 if x == "min" else 24)
                  for s in ("ida", "vuelta") for c in ("salida", "llegada") for x in ("min", "max"))
    partes += [f"máx. {b.get('escalas_max', 1)} escala(s)", "con franjas horarias" if franjas else "sin franjas horarias"]
    return ", ".join(partes)


def cuerpo_aviso(problemas: list[str], version: str | None, sesion: str | None, google_hora: int) -> str:
    lineas = ["## Qué ha pasado", "", *[f"- {p}" for p in problemas], "", "## Datos técnicos", ""]
    if version:
        lineas.append(f"- Versión del robot: `{version[:12]}`")
    lineas.append(f"- Consultas a Google en la última hora: {google_hora}")
    if sesion:
        lineas.append(f"- Registro de la sesión del robot: {sesion}")
    lineas += ["", "_Este aviso lo abre el robot solo y lanza el flujo «Autoarreglo del robot». Sin datos personales:",
               "ni rutas, ni fechas, ni precios, ni nombres de búsquedas._"]
    return "\n".join(lineas)


def pedir_arreglo(db, gh: GitHub | None, enviar_telegram, problemas: list[str], ahora: datetime, google_hora: int) -> bool:
    """Abre el aviso y lanza el arreglo, si no se ha hecho en las últimas 12 h y no hay otro abierto."""
    if not gh or not problemas:
        return False
    fila = db.leer("ajustes", clave="eq.autoarreglo_ultimo")
    ultimo = fila[0]["valor"] if fila else None
    if ultimo and ahora - datetime.fromisoformat(ultimo) < CADA:
        return False
    try:
        if gh.hay_aviso_abierto():
            return False
        servidor, run = os.environ.get("GITHUB_SERVER_URL", "https://github.com"), os.environ.get("GITHUB_RUN_ID")
        sesion = f"{servidor}/{gh.repo}/actions/runs/{run}" if run else None
        aviso = gh.abrir_aviso(f"Autoarreglo: {problemas[0][:90]}",
                               cuerpo_aviso(problemas, os.environ.get("GITHUB_SHA"), sesion, google_hora))
        if not aviso:
            log.warning("Autoarreglo: no se pudo abrir el aviso en GitHub")
            return False
        db.guardar("ajustes", {"clave": "autoarreglo_ultimo", "valor": ahora.isoformat()})
        lanzado = gh.lanzar_arreglo(aviso["number"], os.environ.get("GITHUB_REF_NAME") or "main")
        log.info("Autoarreglo: aviso #%s abierto%s", aviso["number"], " y arreglo lanzado" if lanzado else "")
        enviar_telegram(
            "🛠️ <b>He visto un fallo que se repite</b> y he pedido a Claude que lo revise:\n"
            + "\n".join(f"• {p}" for p in problemas)
            + f"\n\nAviso en GitHub: {aviso['html_url']}\nSi encuentra un arreglo, te dejará una propuesta en GitHub para que "
            "la apruebes; al aprobarla, el robot se actualiza solo en unos minutos.")
        return True
    except httpx.HTTPError as e:
        log.warning("Autoarreglo: GitHub no responde (%s)", type(e).__name__)
        return False


# ----------------------------------------------------------------------------------------
# Actualización sola
# ----------------------------------------------------------------------------------------
def hay_version_nueva(gh: GitHub | None, version: str | None, rama: str | None) -> bool:
    """¿Hay en GitHub una versión del robot más nueva que la que está funcionando?"""
    if not gh or not version or not rama:
        return False
    try:
        ultima = gh.ultimo_commit(rama)
        if not ultima or ultima == version:
            return False
        return any(a.startswith(RUTAS_ROBOT) for a in gh.archivos_cambiados(version, ultima))
    except httpx.HTTPError:
        return False


def marcar_actualizacion() -> None:
    """Le dice al flujo de GitHub que lance ya la siguiente sesión (aunque esta haya durado poco)."""
    fichero = os.environ.get("GITHUB_ENV")
    if fichero:
        with open(fichero, "a", encoding="utf-8") as f:
            f.write("ACTUALIZACION=1\n")
