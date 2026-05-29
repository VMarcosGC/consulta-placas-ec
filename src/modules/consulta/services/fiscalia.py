"""Servicio de consulta a la Fiscalía General del Estado (FGE).

Portal público (SIAF — Sistema Integrado de Actuaciones Fiscales):
  https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/noticiasdelito/index.php

Evidencia de descubrimiento (scripts/discover.py, mayo 2026):
  - NO está en iframe — un solo frame.
  - 1 input: <input id="pwd" type="text"> — acepta cualquier identificador:
      cédula (10), RUC (13), placa (ABC0123), nombres, noticia del delito (NDD),
      número de oficio. El portal detecta el tipo automáticamente.
  - 3 botones tipo input: btn_limpiar_campo, btn_limpiar_pantalla, btn_buscar_denuncia.
  - Datos de acceso público (Constitución art. 76 num. 7 lit. d).

Una sola función `consultar_fiscalia(termino)` sirve para placa o cédula porque
el portal no distingue: pasa lo que tengas y devuelve denuncias asociadas.
"""

import re
from playwright.async_api import async_playwright


URL_FGE = (
    "https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/"
    "noticiasdelito/index.php"
)

USER_AGENT_REAL = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


RE_NDD_BLOQUE = re.compile(
    r"NOTICIA\s+DEL\s+DELITO\s+Nro\.\s*(\d+)\s*"
    r"(?P<cuerpo>.*?)(?=NOTICIA\s+DEL\s+DELITO\s+Nro\.|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _extraer_campo(cuerpo: str, etiqueta: str) -> str | None:
    """Extrae 'ETIQUETA <texto hasta siguiente etiqueta o salto>'."""
    patron = rf"{re.escape(etiqueta)}\s*:?\s*(.+?)\s*(?=\b(?:LUGAR|FECHA|HORA|ESTADO|DELITO|UNIDAD|DIGITADOR|Nro\.\s*OFICIO|FISCAL|SUJETOS|VEHICULOS|NOTICIA\s+DEL\s+DELITO|\Z))"
    match = re.search(patron, cuerpo, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    valor = re.sub(r"\s+", " ", match.group(1)).strip()
    return valor or None


def parsear_respuesta_fge(texto_original: str) -> dict:
    """Extrae denuncias del SIAF de Fiscalía.

    Estructura observada: cada denuncia es un bloque que arranca con
    'NOTICIA DEL DELITO Nro. NNNNNNN' seguido de campos LUGAR, FECHA, HORA,
    DELITO, UNIDAD, SUJETOS, VEHICULOS, etc.
    """
    texto = texto_original

    sin_resultados = bool(
        re.search(
            r"no\s+se\s+(encontr[óo]|hallaron)|sin\s+resultados|"
            r"no\s+existen?\s+(denuncia|registro|noticia)",
            texto,
            re.IGNORECASE,
        )
    )

    denuncias = []
    for match in RE_NDD_BLOQUE.finditer(texto):
        ndd = match.group(1)
        cuerpo = match.group("cuerpo")
        denuncias.append(
            {
                "ndd": ndd,
                "lugar": _extraer_campo(cuerpo, "LUGAR"),
                "fecha": _extraer_campo(cuerpo, "FECHA"),
                "hora": _extraer_campo(cuerpo, "HORA"),
                "delito": _extraer_campo(cuerpo, "DELITO"),
                "unidad": _extraer_campo(cuerpo, "UNIDAD"),
            }
        )

    total = len(denuncias)

    return {
        "denuncias": {
            "total_encontradas": total,
            "detalle": denuncias,
        },
        "sin_resultados": sin_resultados or total == 0,
        "tiene_denuncias": total > 0,
    }


async def consultar_fiscalia(termino: str) -> dict:
    """Consulta el SIAF de Fiscalía con cualquier identificador (placa o cédula).

    El campo `fuente` siempre es 'FGE'. Quien llame puede pasar `termino_tipo`
    en el resultado si necesita distinguir el tipo de búsqueda.
    """
    resultado = {
        "fuente": "FGE",
        "termino": termino,
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
                await page.goto(URL_FGE, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            try:
                await page.wait_for_selector("input#pwd", timeout=10000)
            except Exception:
                await page.screenshot(path="debug_fge_sin_input.png", full_page=True)
                raise Exception(
                    "No apareció input#pwd. Screenshot en debug_fge_sin_input.png."
                )

            await page.fill("input#pwd", termino)
            await page.wait_for_timeout(300)

            try:
                await page.click("input#btn_buscar_denuncia", timeout=5000)
            except Exception:
                await page.press("input#pwd", "Enter")

            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(2500)

            await page.screenshot(path="debug_fge_resultado.png", full_page=True)

            texto_pagina = await page.inner_text("body")
            datos = parsear_respuesta_fge(texto_pagina)

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
