"""Servicio de consulta al SRI (Servicio de Rentas Internas).

Portal público:
  https://srienlinea.sri.gob.ec/sri-en-linea/SriVehiculosWeb/...
Evidencia de descubrimiento (scripts/discover.py, mayo 2026):
  - NO está en iframe — el form vive en la página principal.
  - Input: <input id="busqueda" type="text" placeholder="MNA0123">
  - Botón: <button>Consultar</button> (deshabilitado hasta tipear)
  - reCAPTCHA **Enterprise v3** (score-based). sitekey en el script
    `enterprise.js?render=...`; el sitio llama `grecaptcha.enterprise.execute`
    con action `matriculacion_vehicular_valores_pagar`.

Anti-captcha (opcional, gateado por `CAPSOLVER_API_KEY`): se intercepta
`grecaptcha.enterprise.execute` para inyectar un token resuelto por Capsolver. Sin
key, el flujo queda igual (probable `bloqueado_captcha`). El v3 enterprise es
score-based: aun con token válido, SRI puede rechazarlo si el score es bajo
(considerar `CAPSOLVER_PROXY` residencial). Ver services/captcha.py y docs/bitacora.md.
"""

import re
from playwright.async_api import async_playwright

from src.modules.consulta.services.captcha import (
    resolver_recaptcha_v3_enterprise,
    hay_capsolver,
)


URL_SRI = (
    "https://srienlinea.sri.gob.ec/sri-en-linea/SriVehiculosWeb/"
    "ConsultaValoresPagarVehiculo/Consultas/consultaRubros"
)

# Action que SRI pasa a grecaptcha.enterprise.execute (descubierto interceptando
# execute). Debe coincidir con la del sitio o el backend rechaza el token.
SRI_RECAPTCHA_ACTION = "matriculacion_vehicular_valores_pagar"

# Init-script: intercepta grecaptcha.enterprise.execute para devolver el token que
# inyectemos (window.__cap_token). Se instala ANTES de cargar la página (add_init_script),
# y como grecaptcha carga async, se reintenta el hook con un intervalo corto.
_OVERRIDE_RECAPTCHA = r"""
(() => {
  window.__cap_token = null;
  const install = () => {
    const g = window.grecaptcha && window.grecaptcha.enterprise;
    if (g && !g.__patched) {
      const orig = g.execute.bind(g);
      g.execute = (sk, opts) => {
        if (window.__cap_token) return Promise.resolve(window.__cap_token);
        return orig(sk, opts);
      };
      g.__patched = true;
    }
  };
  const iv = setInterval(install, 30);
  setTimeout(() => clearInterval(iv), 30000);
})();
"""

USER_AGENT_REAL = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def extraer_monto(texto: str, patron: str) -> float:
    match = re.search(patron, texto, re.IGNORECASE)
    if match:
        valor = match.group(1).replace(",", ".").strip()
        try:
            return float(valor)
        except ValueError:
            return 0.0
    return 0.0


def parsear_respuesta_sri(texto_original: str) -> dict:
    tokens = [
        t.strip()
        for t in re.split(r"[\t\n]+", texto_original)
        if t.strip()
    ]

    def obtener_siguiente(etiqueta: str):
        for i, token in enumerate(tokens):
            if token.lower() == etiqueta.lower() and i + 1 < len(tokens):
                return tokens[i + 1]
        return None

    datos_vehiculo = {
        "placa": obtener_siguiente("Placa"),
        "ultimo_anio_pago": obtener_siguiente("Último año de pago"),
        "marca": None,
        "modelo": None,
        "anio_modelo": None,
        "pais": None,
        "estado_exoneracion": None,
    }

    for i, token in enumerate(tokens):
        if token.lower() == "estado exoneración":
            valores = tokens[i + 1:i + 6]
            if len(valores) >= 5:
                datos_vehiculo["marca"] = valores[0]
                datos_vehiculo["modelo"] = valores[1]
                datos_vehiculo["anio_modelo"] = valores[2]
                datos_vehiculo["pais"] = valores[3]
                datos_vehiculo["estado_exoneracion"] = valores[4]
            break

    valores = {
        "matricula": extraer_monto(
            texto_original,
            r"Matrícula\s*USD\s*\$?\s*([0-9]+(?:[.,][0-9]+)?)",
        ),
        "total_a_pagar": extraer_monto(
            texto_original,
            r"A pagar\s*:\s*USD\s*\$?\s*([0-9]+(?:[.,][0-9]+)?)",
        ),
    }

    return {
        "vehiculo": datos_vehiculo,
        "valores": valores,
        "tiene_valores_pendientes": valores["total_a_pagar"] > 0,
    }


async def consultar_sri(placa: str) -> dict:
    """Passthrough al portal oficial del SRI (vía ACTIVA).

    SRI usa reCAPTCHA Enterprise v3 que rechaza los tokens de solvers (ver
    docs/bitacora.md). En vez de pelear el captcha, exponemos el SERVICIO: devolvemos
    el enlace al portal para que el usuario consulte ahí el detalle. Es instantáneo,
    sin Playwright ni costo. El scraping + solver quedan DORMIDOS en
    `_consultar_sri_scraping` (reactivables si algún día se retoma la vía A).
    """
    return {
        "fuente": "SRI",
        "placa": placa,
        "estado": "consulta_externa",
        "datos": None,
        "url_consulta": URL_SRI,
    }


# ── Vía A (DORMIDA): scraping + solver de captcha (Capsolver). NO está en el path
# activo; se conserva para un eventual reintento. La activa es `consultar_sri` (arriba).
async def _consultar_sri_scraping(placa: str) -> dict:
    resultado = {
        "fuente": "SRI",
        "placa": placa,
        "estado": "",
        "datos": None,
    }

    browser = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=USER_AGENT_REAL)
            # Instalar el override de execute antes de cargar la página (solo si hay solver).
            if hay_capsolver():
                await ctx.add_init_script(_OVERRIDE_RECAPTCHA)
            page = await ctx.new_page()
            page.set_default_timeout(60000)
            page.set_default_navigation_timeout(60000)

            try:
                await page.goto(URL_SRI, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass

            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass

            # Dismiss overlay "navegador no soportado" → "Continuar Navegando".
            try:
                boton_continuar = page.locator("button:has-text('Continuar')").first
                if await boton_continuar.is_visible(timeout=2000):
                    await boton_continuar.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            try:
                await page.wait_for_selector("input#busqueda", timeout=15000)
            except Exception:
                await page.screenshot(path="debug_sri_sin_input.png", full_page=True)
                raise Exception(
                    "No apareció input#busqueda. Screenshot en debug_sri_sin_input.png."
                )

            await page.fill("input#busqueda", placa)
            await page.wait_for_timeout(800)

            # ── reCAPTCHA Enterprise v3: resolver con Capsolver e inyectar el token ──
            # Solo se activa si hay CAPSOLVER_API_KEY; sin key, el flujo queda idéntico al
            # previo (probable `bloqueado_captcha`) → cero cambio en prod hasta fondear.
            # El sitekey se EXTRAE de la página (no se hardcodea). El token se entrega vía
            # window.__cap_token: el override de `execute` (init-script) hace que, cuando el
            # sitio llame grecaptcha.enterprise.execute al enviar, reciba NUESTRO token.
            # Fallos del proveedor (sin saldo/timeout/sitekey ausente) → `except` → estado error.
            if hay_capsolver():
                sitekey = await page.evaluate(
                    """() => {
                        const el = document.querySelector('[data-sitekey]');
                        if (el) return el.getAttribute('data-sitekey');
                        const s = [...document.querySelectorAll('script')]
                            .map(x => x.src)
                            .find(u => u && u.includes('render='));
                        if (s) { const m = s.match(/render=([^&]+)/); if (m) return m[1]; }
                        return null;
                    }"""
                )
                if not sitekey:
                    raise Exception(
                        "Solver activo pero no se halló el sitekey de reCAPTCHA en la "
                        "página. Hacer discovery del DOM de SRI antes de seguir."
                    )

                token = await resolver_recaptcha_v3_enterprise(
                    sitekey=sitekey,
                    pageurl=URL_SRI,
                    action=SRI_RECAPTCHA_ACTION,
                    # proxy: usa CAPSOLVER_PROXY si está seteado (residencial sube el score).
                )
                # El override (init-script) devolverá este token cuando el sitio ejecute
                # grecaptcha.enterprise.execute al hacer el submit.
                await page.evaluate("(tok) => { window.__cap_token = tok; }", token)

            # Click en Consultar específico (excluyendo el "Continuar Navegando" del overlay).
            click_ok = False
            for selector in (
                "button:has-text('Consultar'):not(:has-text('Continuar'))",
                "button:text-is('Consultar')",
                "button:has-text('Consultar')",
            ):
                try:
                    loc = page.locator(selector).first
                    if await loc.is_visible(timeout=2000):
                        await loc.click()
                        click_ok = True
                        break
                except Exception:
                    continue

            if not click_ok:
                await page.press("input#busqueda", "Enter")

            # Esperar a que aparezca el panel de resultados (busca "Placa:" o "RAMV"
            # como markers de la card de resultado).
            try:
                await page.wait_for_selector(
                    "text=/Marca|Modelo|Último año|Matrícula/",
                    timeout=15000,
                )
            except Exception:
                # Tal vez no hay resultados — seguir y dejar que el parser lo decida.
                pass

            await page.wait_for_timeout(2000)

            await page.screenshot(path="debug_sri_resultado.png", full_page=True)

            texto_pagina = await page.inner_text("body")
            datos = parsear_respuesta_sri(texto_pagina)

            # Detección de bloqueo por reCAPTCHA invisible:
            # el form se envió aparentemente bien pero NINGÚN campo se llenó.
            # El portal usa Google reCAPTCHA Enterprise que bloquea bots silenciosamente.
            vehiculo = datos.get("vehiculo") or {}
            valores = datos.get("valores") or {}
            sin_datos = (
                all(v is None for v in vehiculo.values())
                and valores.get("matricula", 0) == 0
                and valores.get("total_a_pagar", 0) == 0
            )

            if sin_datos:
                resultado["estado"] = "bloqueado_captcha"
                resultado["error"] = (
                    "Submission probablemente bloqueada por reCAPTCHA invisible. "
                    "Sin datos en respuesta. Ver debug_sri_resultado.png."
                )
                resultado["datos"] = None
            else:
                resultado["estado"] = "consulta_realizada"
                resultado["datos"] = datos

            await browser.close()

    except Exception as e:
        resultado["estado"] = "error"
        resultado["error"] = repr(e)
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

    return resultado
