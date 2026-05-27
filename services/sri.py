"""Servicio de consulta al SRI (Servicio de Rentas Internas).

Portal público:
  https://srienlinea.sri.gob.ec/sri-en-linea/SriVehiculosWeb/...
Evidencia de descubrimiento (scripts/discover.py, mayo 2026):
  - NO está en iframe — el form vive en la página principal.
  - Input: <input id="busqueda" type="text" placeholder="MNA0123">
  - Botón: <button>Consultar</button> (deshabilitado hasta tipear)
  - Hay reCAPTCHA invisible (riesgo de bloqueo)
"""

import re
from playwright.async_api import async_playwright


URL_SRI = (
    "https://srienlinea.sri.gob.ec/sri-en-linea/SriVehiculosWeb/"
    "ConsultaValoresPagarVehiculo/Consultas/consultaRubros"
)

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
