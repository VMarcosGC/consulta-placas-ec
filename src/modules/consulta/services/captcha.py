"""Clientes para resolver reCAPTCHA vía servicios externos (para SRI).

Dos proveedores, ambos con `httpx.AsyncClient` (async, no bloquea el event loop
durante el polling):

- **2Captcha** (`resolver_recaptcha`, env `TWOCAPTCHA_API_KEY`): API clásica
  in.php/res.php. Sirve para reCAPTCHA v2; SE COMPROBÓ que NO pasa el v3 Enterprise
  de SRI (score rechazado server-side). Se conserva por reusabilidad.
- **Capsolver** (`resolver_recaptcha_v3_enterprise`, env `CAPSOLVER_API_KEY`):
  createTask/getTaskResult; mejor rendimiento en reCAPTCHA Enterprise. Es el
  proveedor elegido para el intento de SRI v3. Soporta proxyless o con proxy
  residencial (env `CAPSOLVER_PROXY`).

Si no hay key del proveedor en uso, la función lanza `CaptchaNoConfigurado` — el
servicio que la llame debe degradar con elegancia (SRI deja su `bloqueado_captcha`),
nunca crashear.

Docs: https://2captcha.com/2captcha-api · https://docs.capsolver.com/en/guide/captcha/ReCaptchaV3/
"""

import os
import asyncio

import httpx

API_KEY_ENV = "TWOCAPTCHA_API_KEY"
BASE_URL = "https://2captcha.com"

# Polling: cada cuánto preguntar y cuánto esperar como máximo. Resolver un
# reCAPTCHA suele tardar 15-60s; 120s da margen sin colgar el request para siempre.
INTERVALO_POLL_S = 5
TIMEOUT_TOTAL_S = 120


class CaptchaError(Exception):
    """Error genérico del proveedor de captchas (la submission no se resolvió)."""


class CaptchaNoConfigurado(CaptchaError):
    """No hay `TWOCAPTCHA_API_KEY` en el entorno: el solver está deshabilitado."""


class CaptchaSinSaldo(CaptchaError):
    """La cuenta de 2Captcha no tiene fondos (ERROR_ZERO_BALANCE)."""


class CaptchaTimeout(CaptchaError):
    """El proveedor no devolvió solución dentro de `TIMEOUT_TOTAL_S`."""


def hay_api_key() -> bool:
    """True si el solver está configurado (hay API key en el entorno)."""
    return bool(os.getenv(API_KEY_ENV))


async def resolver_recaptcha(
    *,
    sitekey: str,
    pageurl: str,
    enterprise: bool = True,
    version: str = "v2",
    action: str | None = None,
    min_score: float | None = None,
    user_agent: str | None = None,
    timeout_total_s: int = TIMEOUT_TOTAL_S,
    intervalo_poll_s: int = INTERVALO_POLL_S,
) -> str:
    """Resuelve un reCAPTCHA y devuelve el token (`g-recaptcha-response`).

    Args:
        sitekey: data-sitekey del reCAPTCHA (extraído de la página, NO hardcodeado).
        pageurl: URL de la página donde vive el captcha.
        enterprise: True para reCAPTCHA Enterprise (caso SRI).
        version: "v2" (invisible/checkbox) o "v3" (score + action).
        action: acción de reCAPTCHA v3 (ignorado en v2).
        user_agent: UA a reportar al proveedor (debe coincidir con el del navegador).

    Raises:
        CaptchaNoConfigurado, CaptchaSinSaldo, CaptchaTimeout, CaptchaError.
    """
    api_key = os.getenv(API_KEY_ENV)
    if not api_key:
        raise CaptchaNoConfigurado(
            f"Falta {API_KEY_ENV} en el entorno; solver de captcha deshabilitado."
        )

    payload = {
        "key": api_key,
        "method": "userrecaptcha",
        "googlekey": sitekey,
        "pageurl": pageurl,
        "json": 1,
    }
    if enterprise:
        payload["enterprise"] = 1
    if version == "v3":
        payload["version"] = "v3"
        if action:
            payload["action"] = action
        if min_score is not None:
            payload["min_score"] = min_score
    if user_agent:
        payload["userAgent"] = user_agent

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) Enviar la tarea.
        try:
            r = await client.post(f"{BASE_URL}/in.php", data=payload)
            inicio = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise CaptchaError(f"No se pudo contactar a 2Captcha (in.php): {e!r}")

        if inicio.get("status") != 1:
            _mapear_error(inicio.get("request", "ERROR_DESCONOCIDO"))
        captcha_id = inicio["request"]

        # 2) Poll hasta resolver o agotar el tiempo.
        loop = asyncio.get_event_loop()
        limite = loop.time() + timeout_total_s
        while loop.time() < limite:
            await asyncio.sleep(intervalo_poll_s)
            try:
                rr = await client.get(
                    f"{BASE_URL}/res.php",
                    params={"key": api_key, "action": "get", "id": captcha_id, "json": 1},
                )
                estado = rr.json()
            except (httpx.HTTPError, ValueError) as e:
                raise CaptchaError(f"No se pudo contactar a 2Captcha (res.php): {e!r}")

            if estado.get("status") == 1:
                return estado["request"]
            if estado.get("request") == "CAPCHA_NOT_READY":
                continue
            _mapear_error(estado.get("request", "ERROR_DESCONOCIDO"))

        raise CaptchaTimeout(
            f"2Captcha no resolvió en {timeout_total_s}s (id={captcha_id})."
        )


def _mapear_error(codigo: str) -> None:
    """Traduce el código de error de 2Captcha a una excepción del módulo."""
    if codigo == "ERROR_ZERO_BALANCE":
        raise CaptchaSinSaldo("La cuenta de 2Captcha no tiene saldo.")
    raise CaptchaError(f"2Captcha devolvió error: {codigo}")


# ─────────────────────────────── Capsolver ───────────────────────────────
# Proveedor elegido para SRI (reCAPTCHA Enterprise v3). API JSON createTask /
# getTaskResult. Doc: https://docs.capsolver.com/en/guide/captcha/ReCaptchaV3/

CAPSOLVER_API_KEY_ENV = "CAPSOLVER_API_KEY"
# Proxy opcional para subir el score del v3 (formato Capsolver, p.ej.
# "http:host:port:user:pass"). Sin esto se usa la variante proxyless.
CAPSOLVER_PROXY_ENV = "CAPSOLVER_PROXY"
CAPSOLVER_BASE_URL = "https://api.capsolver.com"


def hay_capsolver() -> bool:
    """True si Capsolver está configurado (hay API key en el entorno)."""
    return bool(os.getenv(CAPSOLVER_API_KEY_ENV))


async def resolver_recaptcha_v3_enterprise(
    *,
    sitekey: str,
    pageurl: str,
    action: str,
    proxy: str | None = None,
    timeout_total_s: int = TIMEOUT_TOTAL_S,
    intervalo_poll_s: int = INTERVALO_POLL_S,
) -> str:
    """Resuelve un reCAPTCHA Enterprise v3 con Capsolver y devuelve el token.

    Usa la variante proxyless salvo que se pase `proxy` (o esté `CAPSOLVER_PROXY`),
    en cuyo caso usa `ReCaptchaV3EnterpriseTask` con ese proxy (útil para mejorar el
    score con una IP residencial EC).

    Raises: CaptchaNoConfigurado, CaptchaSinSaldo, CaptchaTimeout, CaptchaError.
    """
    api_key = os.getenv(CAPSOLVER_API_KEY_ENV)
    if not api_key:
        raise CaptchaNoConfigurado(
            f"Falta {CAPSOLVER_API_KEY_ENV} en el entorno; Capsolver deshabilitado."
        )

    proxy = proxy or os.getenv(CAPSOLVER_PROXY_ENV)
    task = {
        "type": "ReCaptchaV3EnterpriseTask" if proxy else "ReCaptchaV3EnterpriseTaskProxyLess",
        "websiteURL": pageurl,
        "websiteKey": sitekey,
        "pageAction": action,
    }
    if proxy:
        task["proxy"] = proxy

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(
                f"{CAPSOLVER_BASE_URL}/createTask",
                json={"clientKey": api_key, "task": task},
            )
            inicio = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise CaptchaError(f"No se pudo contactar a Capsolver (createTask): {e!r}")

        if inicio.get("errorId"):
            _mapear_error_capsolver(inicio)
        task_id = inicio.get("taskId")
        if not task_id:
            raise CaptchaError(f"Capsolver no devolvió taskId: {inicio!r}")

        loop = asyncio.get_event_loop()
        limite = loop.time() + timeout_total_s
        while loop.time() < limite:
            await asyncio.sleep(intervalo_poll_s)
            try:
                rr = await client.post(
                    f"{CAPSOLVER_BASE_URL}/getTaskResult",
                    json={"clientKey": api_key, "taskId": task_id},
                )
                estado = rr.json()
            except (httpx.HTTPError, ValueError) as e:
                raise CaptchaError(f"No se pudo contactar a Capsolver (getTaskResult): {e!r}")

            if estado.get("errorId"):
                _mapear_error_capsolver(estado)
            if estado.get("status") == "ready":
                token = (estado.get("solution") or {}).get("gRecaptchaResponse")
                if not token:
                    raise CaptchaError(f"Capsolver 'ready' sin token: {estado!r}")
                return token
            # status == "processing" → seguir esperando

        raise CaptchaTimeout(
            f"Capsolver no resolvió en {timeout_total_s}s (taskId={task_id})."
        )


def _mapear_error_capsolver(respuesta: dict) -> None:
    """Traduce un error de Capsolver a una excepción del módulo."""
    codigo = respuesta.get("errorCode") or ""
    desc = respuesta.get("errorDescription") or ""
    if codigo in ("ERROR_ZERO_BALANCE", "ERROR_INSUFFICIENT_BALANCE"):
        raise CaptchaSinSaldo("La cuenta de Capsolver no tiene saldo.")
    raise CaptchaError(f"Capsolver error: {codigo} {desc}".strip())
