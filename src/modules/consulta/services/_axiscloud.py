"""Adaptador compartido para portales sobre la plataforma **AxisCloud AutoServicio**.

Varias agencias municipales de tránsito de Ecuador exponen su consulta de
infracciones sobre el mismo sistema JSP de AxisCloud
(`servicios.axiscloud.ec/AutoServicio/...?ps_empresa=NN&ps_accion=P55`), idéntico
salvo el código de empresa:

- AMT Quito → `ps_empresa=03` (ver [amt.py](amt.py)).
- EPMTSD Santo Domingo → `ps_empresa=06` (ver [epmtsd.py](epmtsd.py)).

Como el formulario (iframe + `<select>` Tipo de Búsqueda con Placa + input Valor +
botón Buscar + overlay "Consultando") y el formato de resultados (categorías
Pendientes/Pagadas/Anuladas/…) son los mismos, la mecánica vive aquí una sola vez.
Cada servicio público (`consultar_amt`, `consultar_epmtsd`) solo aporta su
`ps_empresa` y su código de fuente; el parser es común porque la página es la misma.

Mismo gotcha que AMT (AGENTS.md §8): el portal sirve `inputCode.jsp` / reCAPTCHA a
IPs de datacenter, así que en cloud va por el worker híbrido (IP residencial EC).
"""
import re

from playwright.async_api import async_playwright

from src.core.proxy_apify import proxy_playwright


def url_axiscloud(ps_empresa: str) -> str:
    return (
        "https://servicios.axiscloud.ec/AutoServicio/inicio.jsp"
        f"?ps_empresa={ps_empresa}&ps_accion=P55"
    )


def limpiar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def extraer_monto(texto: str, patron: str) -> float:
    match = re.search(patron, texto, re.IGNORECASE)
    if match:
        valor = match.group(1).replace(",", ".").strip()
        try:
            return float(valor)
        except ValueError:
            return 0.0
    return 0.0


# Categorías de estado de infracción que muestra el bloque inferior del resultado.
CATEGORIAS = (
    "Pendientes",
    "Pagadas",
    "Anuladas",
    "En Convenio",
    "En Coactiva",
    "En Impugnación",
)


def _extraer_categoria(texto: str, etiqueta: str) -> tuple[int, float]:
    """Parsea 'Pendientes (4) - $557.95' → (4, 557.95)."""
    patron = (
        rf"{re.escape(etiqueta)}\s*\(\s*(\d+)\s*\)\s*-?\s*\$?\s*([0-9]+(?:[.,][0-9]+)?)"
    )
    match = re.search(patron, texto, re.IGNORECASE)
    if not match:
        return (0, 0.0)
    cantidad = int(match.group(1))
    monto = float(match.group(2).replace(",", "."))
    return (cantidad, monto)


def parsear_infracciones(texto_original: str) -> dict:
    """Extrae infracciones por categoría del texto crudo de la página de resultados.

    Estructura observada en el portal axiscloud (Mayo 2026):
      - Bloque 'Infracciones' con 'TOTAL PENDIENTE: $X.XX'.
      - Bloque inferior con categorías 'Pendientes (N) - $X.XX', 'Pagadas (N) - $X.XX', etc.
    """
    texto = limpiar_texto(texto_original)

    total_pendiente = extraer_monto(
        texto,
        r"TOTAL\s+PENDIENTE\s*:?\s*\$?\s*([0-9]+(?:[.,][0-9]+)?)",
    )

    categorias = {}
    for etiqueta in CATEGORIAS:
        cantidad, monto = _extraer_categoria(texto, etiqueta)
        clave = (
            etiqueta.lower()
            .replace(" ", "_")
            .replace("ó", "o")
            .replace("á", "a")
        )
        categorias[clave] = {"cantidad": cantidad, "monto": monto}

    total_registros = sum(c["cantidad"] for c in categorias.values())
    pendientes_cantidad = categorias.get("pendientes", {}).get("cantidad", 0)

    return {
        "infracciones": {
            "total_registros": total_registros,
            "total_a_pagar": total_pendiente,
            "pendientes": pendientes_cantidad,
            "categorias": categorias,
        },
        "tiene_pendientes": pendientes_cantidad > 0 or total_pendiente > 0,
        "tiene_registros": total_registros > 0,
    }


async def consultar_axiscloud(ps_empresa: str, fuente: str, placa: str) -> dict:
    """Consulta infracciones por placa en un portal AxisCloud AutoServicio.

    Devuelve el contrato estándar (AGENTS.md §6). El `fuente` es el código corto
    (ej. "AMT", "EPMTSD") que el llamador quiere ver reflejado en la respuesta.
    """
    resultado = {
        "fuente": fuente,
        "placa": placa,
        "estado": "",
        "datos": None,
    }

    browser = None
    # Prefijo para los screenshots de debug (gitignored), por fuente.
    dbg = fuente.lower()

    try:
        async with async_playwright() as p:
            # Proxy residencial EC (Apify) si está configurado: permite scrapear el
            # portal AxisCloud (AMT/EPMTSD) desde la nube, donde la IP de datacenter
            # está bloqueada. Sin config → launch directo (comportamiento actual).
            browser = await p.chromium.launch(headless=True, proxy=proxy_playwright())
            page = await browser.new_page()

            # Timeouts cortos (15s) para no dejar al usuario esperando en el frontend:
            # si la fuente no responde a tiempo, preferimos fallar rápido y que el
            # worker reintente con backoff a colgar la consulta.
            page.set_default_timeout(15000)
            page.set_default_navigation_timeout(15000)

            try:
                await page.goto(
                    url_axiscloud(ps_empresa), wait_until="domcontentloaded", timeout=15000
                )
            except Exception:
                pass

            # Esperar a que termine de cargar todo (incluido contenido de iframes).
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            # AXIS suele cargar el form en un iframe. Buscar el frame que contenga el form.
            contexto = None
            for frame in page.frames:
                try:
                    if await frame.locator("text=Tipo de Búsqueda").count() > 0:
                        contexto = frame
                        break
                except Exception:
                    continue

            if contexto is None:
                # Fallback: ¿está en el main page directamente?
                try:
                    if await page.locator("text=Tipo de Búsqueda").count() > 0:
                        contexto = page.main_frame
                except Exception:
                    pass

            if contexto is None:
                info_frames = "\n".join(
                    f"  - {i}: {f.url}" for i, f in enumerate(page.frames)
                )
                await page.screenshot(path=f"debug_{dbg}_sin_form.png", full_page=True)
                raise Exception(
                    "Form no encontrado ni en main page ni en iframes. "
                    f"Frames disponibles:\n{info_frames}\n"
                    f"Screenshot en debug_{dbg}_sin_form.png."
                )

            # Cambiar el dropdown "Tipo de Búsqueda" de Cédula a Placa.
            # Es un <select> nativo con <option value="CED">Cédula</option>,
            # <option value="PLA">Placa</option>, etc. (revelado por error log).
            selects = contexto.locator("select")
            if await selects.count() == 0:
                await page.screenshot(path=f"debug_{dbg}_dropdown.png", full_page=True)
                raise Exception(
                    "No se encontró <select> de tipo de búsqueda. "
                    f"Screenshot en debug_{dbg}_dropdown.png."
                )

            seleccionado = False
            for kwargs in (
                {"label": "Placa"},
                {"value": "PLA"},
                {"label": "PLACA"},
                {"value": "PLACA"},
            ):
                try:
                    await selects.first.select_option(**kwargs)
                    seleccionado = True
                    break
                except Exception:
                    continue

            if not seleccionado:
                await page.screenshot(path=f"debug_{dbg}_dropdown.png", full_page=True)
                raise Exception(
                    "No pude seleccionar 'Placa' en el <select>. "
                    f"Screenshot en debug_{dbg}_dropdown.png."
                )

            await page.wait_for_timeout(500)

            # Llenar el campo "Valor".
            campo_valor = None
            for selector in (
                "input[type='text']",
                "input:not([type='hidden'])",
                "input",
            ):
                loc = contexto.locator(selector)
                if await loc.count() > 0:
                    campo_valor = loc.first
                    break

            if campo_valor is None:
                await page.screenshot(path=f"debug_{dbg}_sin_input.png", full_page=True)
                raise Exception(
                    f"No se encontró input para la placa. Screenshot en debug_{dbg}_sin_input.png."
                )

            await campo_valor.fill(placa)
            await page.wait_for_timeout(500)

            # Click en "Buscar" dentro del mismo contexto (page o iframe).
            click_realizado = False
            for selector in (
                "button:has-text('Buscar')",
                "text=Buscar",
                "button:has-text('Consultar')",
            ):
                try:
                    if await contexto.locator(selector).count() > 0:
                        await contexto.locator(selector).first.click()
                        click_realizado = True
                        break
                except Exception:
                    continue

            if not click_realizado:
                await campo_valor.press("Enter")

            # Esperar a que aparezca el overlay "Consultando" y luego desaparezca.
            try:
                await contexto.wait_for_selector(
                    "text=Consultando", state="visible", timeout=5000
                )
                # Este wait NO es latencia de red sino el cómputo del JSP: si lo
                # cortamos antes, se parsea una página a medio cargar y se cachea
                # un falso "0 infracciones" ~12h. Por eso se mantiene en 25s.
                await contexto.wait_for_selector(
                    "text=Consultando", state="hidden", timeout=25000
                )
            except Exception:
                pass

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(1500)

            await page.screenshot(path=f"debug_{dbg}_resultado.png", full_page=True)

            # inner_text del contexto correcto (iframe o page).
            try:
                texto_pagina = await contexto.locator("body").inner_text()
            except Exception:
                texto_pagina = await page.inner_text("body")
            datos = parsear_infracciones(texto_pagina)

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
