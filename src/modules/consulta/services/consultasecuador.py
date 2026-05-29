"""Servicio ConsultasEcuador (portal de terceros, NO oficial).

Aportaría chasis/motor por placa, pero el descubrimiento (mayo 2026) mostró que
NO es una fuente de datos scrapeable: `consultasecuador.com/.../consultar-chasis`
es una página de contenido/SEO con un widget de afiliado (Bumper), mucha
publicidad y **reCAPTCHA** — el mismo muro que bloquea al SRI (AGENTS.md §8).
No hay endpoint libre "placa → chasis/motor" automatizable.

Por eso se expone como **`consulta_externa`** (igual que el SRI): passthrough
instantáneo al portal para que el usuario consulte ahí, con disclaimer de fuente
no oficial en el frontend. No se scrapea ni se pelea el captcha; si en el futuro
se quiere el dato real, haría falta un solver de captcha de pago (vía dormida del
SRI) o una fuente alternativa.
"""

URL_CONSULTASEC = "https://consultasecuador.com/en-linea/transito/consultar-chasis"


async def consultar_consultasecuador(placa: str) -> dict:
    """Passthrough no oficial al portal de ConsultasEcuador (chasis/VIN por placa).

    Instantáneo: no toca la red. Devuelve `consulta_externa` con la URL del portal.
    """
    return {
        "fuente": "ConsultasEcuador",
        "placa": placa,
        "estado": "consulta_externa",
        "datos": None,
        "url_consulta": URL_CONSULTASEC,
    }
