"""Servicio Ecuador Legal Online (portal de terceros, NO oficial).

El descubrimiento (mayo 2026) confirmó que NO es una fuente de datos scrapeable:
`ecuadorlegalonline.com` es un sitio WordPress de guías/SEO con ad-gate ("VER
ANUNCIO Y CONTINUAR"), publicidad masiva y reCAPTCHA; el dato real (propietario por
placa) está tras un **pago PayPal de USD 4.99** y, además, es información de
propietario (PII) que por privacidad (AGENTS.md §9) no se expone en la consulta
pública anónima.

Por eso se expone como **`consulta_externa`** (enlace + disclaimer no oficial), sin
scraping ni datos en la respuesta — mismo criterio que ConsultasEcuador y SRI.
"""

URL_ECUADORLEGAL = (
    "https://www.ecuadorlegalonline.com/consultas/buscar-propietario-de-vehiculo-por-placa/"
)


async def consultar_ecuadorlegalonline(placa: str) -> dict:
    """Passthrough no oficial al portal de Ecuador Legal Online. Instantáneo, sin red."""
    return {
        "fuente": "EcuadorLegalOnline",
        "placa": placa,
        "estado": "consulta_externa",
        "datos": None,
        "url_consulta": URL_ECUADORLEGAL,
    }
