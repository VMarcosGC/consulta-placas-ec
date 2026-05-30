"""Proxy residencial para Playwright (egreso con IP residencial, p. ej. de Ecuador).

Las fuentes municipales/judiciales (AMT, EPMTSD, FGE) bloquean IPs de datacenter
(AGENTS.md §8). Para que funcionen desde la nube (Render) sin una máquina con IP
residencial propia, enrutamos esos scrapers por un **proxy residencial**.

Reutiliza los scrapers Playwright ya validados — solo cambia la IP de salida; la
interacción y el parsing no se tocan, así que los resultados se mantienen correctos.

⚠️ Requiere un proxy residencial REAL. Un proxy de **datacenter** NO sirve (es justo lo
que estas fuentes bloquean). Nota: el plan **Apify FREE no incluye residencial** (solo
datacenter), así que esta vía exige un plan Apify de pago con residencial **u otro
proveedor** (Bright Data, IPRoyal, Smartproxy, etc.).

Config (todas opcionales; sin ninguna → sin proxy = comportamiento actual, directo):
  Opción A — proveedor genérico (recomendada, sirve para cualquiera):
    SCRAPER_PROXY_URL    URL completa, ej. http://usuario:pass@host:puerto
  Opción B — Apify por componentes (requiere plan con residencial):
    APIFY_PROXY_PASSWORD  contraseña de Apify Proxy (NO el API token).
    APIFY_PROXY_GROUPS    grupo (default "RESIDENTIAL").
    APIFY_PROXY_PAIS      país de la IP (default "EC").

ANT NO usa este proxy: funciona directo desde datacenter; el residencial solo
agregaría latencia y puntos de fallo.
"""
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

APIFY_PROXY_SERVER = "http://proxy.apify.com:8000"


def proxy_playwright() -> dict | None:
    """Devuelve el dict `proxy=` para `chromium.launch()`, o None si no hay proxy configurado."""
    # Opción A: URL completa de cualquier proveedor → se parte en server/username/password.
    url = os.getenv("SCRAPER_PROXY_URL", "").strip()
    if url:
        p = urlparse(url)
        if not p.hostname:
            logger.warning("SCRAPER_PROXY_URL inválida (sin host): %r", url)
            return None
        puerto = f":{p.port}" if p.port else ""
        proxy: dict = {"server": f"{p.scheme or 'http'}://{p.hostname}{puerto}"}
        if p.username:
            proxy["username"] = p.username
        if p.password:
            proxy["password"] = p.password
        return proxy

    # Opción B: Apify por componentes (username codifica grupo y país).
    password = os.getenv("APIFY_PROXY_PASSWORD", "").strip()
    if password:
        grupos = os.getenv("APIFY_PROXY_GROUPS", "RESIDENTIAL").strip() or "RESIDENTIAL"
        pais = os.getenv("APIFY_PROXY_PAIS", "EC").strip()
        partes = [f"groups-{grupos}"]
        if pais:
            partes.append(f"country-{pais}")
        return {
            "server": APIFY_PROXY_SERVER,
            "username": ",".join(partes),
            "password": password,
        }

    return None


def proxy_activo() -> bool:
    return proxy_playwright() is not None
