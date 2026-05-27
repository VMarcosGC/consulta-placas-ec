import re
from playwright.async_api import async_playwright


def limpiar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def extraer_campo(texto: str, campo: str, siguiente_campo: str):
    patron = rf"{re.escape(campo)}\s*:?\s*(.*?)\s*(?={re.escape(siguiente_campo)}\s*:?)"
    match = re.search(patron, texto, re.IGNORECASE)

    if match:
        valor = match.group(1).strip()
        return valor if valor else None

    return None


def extraer_numero(texto: str, etiqueta: str):
    patron = rf"{etiqueta}\s*\((\d+)\)"
    match = re.search(patron, texto, re.IGNORECASE)

    if match:
        return int(match.group(1))

    return 0


def extraer_regex(texto: str, patron: str):
    match = re.search(patron, texto, re.IGNORECASE)

    if match:
        valor = match.group(1).strip()
        return valor if valor else None

    return None


def parsear_respuesta_ant(texto_original: str):
    texto = limpiar_texto(texto_original)

    datos_vehiculo = {
        "marca": extraer_campo(texto, "Marca", "Color"),
        "color": extraer_campo(texto, "Color", "Año de Matrícula"),

        # Año de matrícula, ejemplo: 2025
        "anio_matricula": extraer_regex(
            texto,
            r"Año de Matrícula\s*:?\s*(\d{4})"
        ),

        "modelo": extraer_campo(texto, "Modelo", "Clase"),
        "clase": extraer_campo(texto, "Clase", "Fecha de Matrícula"),

        # Fecha de matrícula, ejemplo: 25-06-2025
        "fecha_matricula": extraer_regex(
            texto,
            r"Fecha de Matrícula\s*:?\s*([0-9]{2}-[0-9]{2}-[0-9]{4})"
        ),

        # Año real del vehículo, ejemplo: 2009
        "anio_vehiculo": extraer_regex(
            texto,
            r"\bAño\s*:?\s*(\d{4})\s*Servicio"
        ),

        "servicio": extraer_campo(texto, "Servicio", "Fecha de Caducidad"),
        "fecha_caducidad": extraer_regex(
            texto,
            r"Servicio\s*:?.*?Fecha de Caducidad\s*:?\s*([0-9]{2}-[0-9]{2}-[0-9]{4})"
        ),
        "polarizado": extraer_campo(texto, "Polarizado", "Fecha Caducidad"),
    }

    citaciones = {
        "pendientes": extraer_numero(texto, "Pendientes"),
        "en_impugnacion": extraer_numero(texto, "En Impugnación"),
        "anuladas": extraer_numero(texto, "Anuladas"),
        "pagadas": extraer_numero(texto, "Pagadas"),
        "en_convenio": extraer_numero(texto, "En Convenio"),
    }

    citaciones["total_registros"] = sum(citaciones.values())

    return {
        "vehiculo": datos_vehiculo,
        "citaciones": citaciones,
        "tiene_pendientes": citaciones["pendientes"] > 0,
        "tiene_registros": citaciones["total_registros"] > 0,
    }


async def consultar_ant(placa: str):

    resultado = {
        "fuente": "ANT",
        "placa": placa,
        "estado": "",
        "datos": None
    }

    try:
        async with async_playwright() as p:

            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(
                "https://consultaweb.ant.gob.ec/PortalWEB/paginas/clientes/clp_criterio_consulta.jsp",
                timeout=60000
            )

            await page.wait_for_timeout(3000)

            await page.select_option("select", label="PLACA")

            campo = page.locator("input[type='text']").first
            await campo.fill(placa)
            await page.wait_for_timeout(1000)

            await campo.press("Enter")

            await page.wait_for_timeout(6000)

            texto_pagina = await page.inner_text("body")

            datos_limpios = parsear_respuesta_ant(texto_pagina)

            resultado["estado"] = "consulta_realizada"
            resultado["datos"] = datos_limpios

            await browser.close()

    except Exception as e:
        resultado["estado"] = "error"
        resultado["error"] = repr(e)

    return resultado
