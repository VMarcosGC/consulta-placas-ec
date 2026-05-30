"""Cliente de extracción en la nube vía **Apify** (responsabilidad única: traer HTML).

Delega el renderizado del navegador y la rotación de IP a la infraestructura de Apify,
para no gastar recursos locales ni mantener proxies propios. Llama a un Actor de Apify
(por defecto `apify/playwright-scraper`), le pasa la URL y un `pageFunction` que devuelve
el HTML crudo de la página renderizada.

RESPONSABILIDAD ÚNICA: este módulo SOLO obtiene el HTML. No parsea ni extrae datos
específicos — eso es trabajo de cada `services/<fuente>.py`.

⚠️ Uso responsable (importante): Apify es una plataforma legítima, pero úsese con criterio.
- **Uso defendible**: fuentes OFICIALES públicas que bloquean IPs de datacenter (ANT/AMT/
  EPMTSD/FGE, AGENTS.md §8) — son datos públicos a los que el ciudadano tiene derecho.
- **Zona gris (evitar / pedir asesoría legal)**: evadir el reCAPTCHA/anti-bot de sitios
  PRIVADOS de terceros (ConsultasEcuador, EcuadorLegalOnline) puede violar sus ToS y normas
  anti-circumvención, además de costo y fragilidad. Estas fuentes hoy son `consulta_externa`.
- Respetar el skill `scraping-respetuoso` (un request por fuente, sin paralelizar contra la
  misma, backoff). Este cliente no debe usarse para scraping masivo.

Config: `APIFY_API_TOKEN` por variable de entorno (os.getenv). Si falta, `obtener_datos`
lanza `ApifyExtractorError` (la feature queda deshabilitada, no rompe el resto de la app).
La dependencia `apify-client` se importa de forma perezosa para no exigirla en el arranque.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Actor por defecto: renderiza con navegador real (evade WAF/JS). Configurable.
ACTOR_PLAYWRIGHT_SCRAPER = "apify/playwright-scraper"

# pageFunction (JS) que corre en el Actor. En playwright-scraper el contexto trae `page`
# (Node), así que el outerHTML se obtiene evaluando en el navegador.
_PAGE_FUNCTION = """
async function pageFunction(context) {
    const { page, request, log } = context;
    log.info('extractor_apify: extrayendo HTML de ' + request.url);
    const html = await page.evaluate(() => document.documentElement.outerHTML);
    return { url: request.url, html };
}
""".strip()


class ApifyExtractorError(RuntimeError):
    """Falla al extraer HTML vía Apify (token ausente, actor fallido, timeout, etc.)."""


class ApifyExtractor:
    """Obtiene el HTML renderizado de una URL delegando en un Actor de Apify.

    Uso:
        extractor = ApifyExtractor()
        html = await extractor.obtener_datos("https://ejemplo.com")
    """

    def __init__(
        self,
        token: str | None = None,
        actor_id: str = ACTOR_PLAYWRIGHT_SCRAPER,
        *,
        usar_proxy: bool = True,
        actor_timeout_segundos: int = 90,
        max_reintentos: int = 2,
    ) -> None:
        # Lee el token por env var (no se hardcodea ni se commitea).
        self._token = token or os.getenv("APIFY_API_TOKEN", "")
        self._actor_id = actor_id
        self._usar_proxy = usar_proxy
        self._actor_timeout_segundos = actor_timeout_segundos
        self._max_reintentos = max_reintentos

    @property
    def configurado(self) -> bool:
        return bool(self._token)

    def _crear_cliente(self):
        """Importa `apify-client` de forma perezosa y crea el cliente ASÍNCRONO.

        Async (`ApifyClientAsync`) para NO bloquear el event loop de FastAPI.
        """
        try:
            from apify_client import ApifyClientAsync
        except ImportError as e:  # dependencia opcional, aún no instalada
            raise ApifyExtractorError(
                "Falta la dependencia 'apify-client'. Instalá con: pip install apify-client"
            ) from e
        return ApifyClientAsync(token=self._token)

    def _run_input(self, url: str) -> dict:
        run_input: dict = {
            "startUrls": [{"url": url}],
            "pageFunction": _PAGE_FUNCTION,
            "headless": True,
            # Una sola URL por llamada; sin crawling.
            "maxPagesPerCrawl": 1,
            "maxRequestRetries": 1,
        }
        if self._usar_proxy:
            # Proxy de Apify (rotación de IP). Para IP residencial real se requiere plan
            # pago con grupos RESIDENTIAL; por defecto usamos el proxy estándar de Apify.
            run_input["proxyConfiguration"] = {"useApifyProxy": True}
        return run_input

    async def obtener_datos(self, url: str) -> str:
        """Devuelve el HTML crudo renderizado de `url`.

        Lanza `ApifyExtractorError` si no hay token, si el Actor falla tras los reintentos,
        o si la corrida no produce HTML. Reintenta ante errores transitorios del proveedor
        (5xx / timeouts) con backoff corto.
        """
        if not self.configurado:
            raise ApifyExtractorError(
                "APIFY_API_TOKEN no configurado: extracción vía Apify deshabilitada."
            )

        cliente = self._crear_cliente()
        run_input = self._run_input(url)
        ultimo_error: Exception | None = None

        for intento in range(1, self._max_reintentos + 1):
            try:
                # `.call()` (async) dispara el Actor y espera a que termine, con tope.
                run = await cliente.actor(self._actor_id).call(
                    run_input=run_input,
                    timeout_secs=self._actor_timeout_segundos,
                )

                if not run or run.get("status") != "SUCCEEDED":
                    raise ApifyExtractorError(
                        f"Actor {self._actor_id} no terminó OK "
                        f"(status={run.get('status') if run else 'sin run'})"
                    )

                dataset_id = run.get("defaultDatasetId")
                if not dataset_id:
                    raise ApifyExtractorError("La corrida del Actor no devolvió dataset.")

                pagina = await cliente.dataset(dataset_id).list_items()
                items = getattr(pagina, "items", None) or []
                html = items[0].get("html") if items else None
                if not html:
                    raise ApifyExtractorError("El Actor no devolvió HTML para la URL.")

                return html

            except ApifyExtractorError:
                # Errores "de negocio" del extractor: no reintentar a ciegas, propagar.
                raise
            except Exception as e:  # ApifyApiError, timeouts, red: transitorios
                ultimo_error = e
                logger.warning(
                    "Apify intento %s/%s falló para %s: %r",
                    intento, self._max_reintentos, url, e,
                )
                if intento < self._max_reintentos:
                    await asyncio.sleep(2 * intento)  # backoff corto

        raise ApifyExtractorError(
            f"Apify agotó {self._max_reintentos} intentos para {url}: {ultimo_error!r}"
        )
