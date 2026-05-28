"""OCR de placas vía Google Cloud Vision (REST con API key).

Se usa la API REST (`images:annotate`) en vez del SDK `google-cloud-vision` para
mantener la imagen Docker liviana y configurar la credencial como una env var simple
(`GOOGLE_VISION_API_KEY`), en línea con "toda config sensible va en env vars".

Sigue la disciplina de servicios externos del proyecto: captura todo y devuelve un
dict estructurado; NUNCA propaga excepciones al endpoint.
"""

import base64
import os
import re

import httpx

from utils.validators import validar_placa


VISION_URL = "https://vision.googleapis.com/v1/images:annotate"

# Placa ecuatoriana dentro de un texto: 3 letras + 3 o 4 dígitos, tolerando un
# separador (guion/espacio) que validar_placa normaliza después. Los lookarounds
# anclan a fronteras de token para no capturar fragmentos de palabras ("uTIL123")
# ni prefijos de números más largos ("PBX 022345" → no es GHQ0987).
_PATRON_PLACA = re.compile(r"(?<![A-Z0-9])[A-Z]{3}[\s-]?[0-9]{3,4}(?![0-9])")


def _extraer_placa(texto: str) -> str | None:
    """Busca la primera secuencia con forma de placa válida en el texto del OCR."""
    candidato_normalizado = texto.upper()
    for bruto in _PATRON_PLACA.findall(candidato_normalizado):
        try:
            return validar_placa(bruto)
        except ValueError:
            continue
    return None


async def extraer_placa_de_imagen(imagen: bytes) -> dict:
    """Extrae la placa de una imagen usando Cloud Vision.

    Devuelve un dict con `estado`:
      - `placa_detectada`  → `placa` contiene la placa normalizada.
      - `sin_placa`        → la imagen se leyó pero no hay placa válida.
      - `no_configurado`   → falta GOOGLE_VISION_API_KEY (error de despliegue).
      - `error`            → fallo técnico (red, API). Incluye `error`.
    """
    api_key = os.getenv("GOOGLE_VISION_API_KEY", "").strip()
    if not api_key:
        return {"estado": "no_configurado", "placa": None}

    cuerpo = {
        "requests": [
            {
                "image": {"content": base64.b64encode(imagen).decode("ascii")},
                "features": [{"type": "TEXT_DETECTION", "maxResults": 1}],
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as cliente:
            respuesta = await cliente.post(
                VISION_URL, params={"key": api_key}, json=cuerpo
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
    except Exception as e:  # red, timeout, HTTP 4xx/5xx, JSON inválido
        return {"estado": "error", "placa": None, "error": repr(e)}

    anotaciones = (datos.get("responses") or [{}])[0]

    # Vision puede devolver HTTP 200 con un objeto `error` embebido (cuota agotada,
    # clave inválida, imagen corrupta). No es "sin placa": es un fallo técnico.
    error_api = anotaciones.get("error")
    if error_api:
        return {"estado": "error", "placa": None, "error": repr(error_api)}

    texto = (anotaciones.get("fullTextAnnotation") or {}).get("text", "")
    if not texto:
        anotaciones_texto = anotaciones.get("textAnnotations") or []
        texto = anotaciones_texto[0].get("description", "") if anotaciones_texto else ""

    placa = _extraer_placa(texto) if texto else None
    if placa is None:
        return {"estado": "sin_placa", "placa": None}

    return {"estado": "placa_detectada", "placa": placa}
