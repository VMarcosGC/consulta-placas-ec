"""Firma de subida directa a Cloudinary (M2 — fotos de la publicación).

Decisión de arquitectura (2026-07-19, Marcos): el backend **no** recibe el binario
de la imagen. El navegador sube directo a Cloudinary usando una **firma** que este
servicio genera; luego el backend solo persiste la URL resultante.

Por qué firma manual con `hashlib.sha1` y no el SDK de Cloudinary:
- Evita una dependencia nueva (§4 y §15: sin deps sin justificar). La firma de
  subida de Cloudinary es un simple SHA-1 de los parámetros ordenados + el
  `api_secret`; no vale la pena arrastrar el SDK por esto.
- Toda credencial va por env var (`CLOUDINARY_*`), jamás hardcodeada.

Patrón de servicio externo config-por-env (igual que `consulta/services/vision.py`):
si falta la credencial, `esta_configurado()` es `False` y el endpoint responde **503**
(config faltante), nunca un 500.

Spec de la firma (https://cloudinary.com/documentation/upload_images#generating_authentication_signatures):
1. Tomar los parámetros a firmar (todos menos `file`, `cloud_name`, `resource_type`,
   `api_key` y la propia `signature`). Para una subida firmada mínima: `folder` y
   `timestamp` (+ los opcionales que se quieran fijar).
2. Ordenarlos alfabéticamente por clave y unirlos como `k=v` separados por `&`.
3. Concatenar el `api_secret` al final y calcular el SHA-1 hex de esa cadena.
"""

import hashlib
import os
import time
from urllib.parse import urlparse


# Carpeta raíz por defecto donde se agrupan las fotos del market. Se puede
# sobreescribir con CLOUDINARY_UPLOAD_FOLDER. Cada publicación cuelga de una
# subcarpeta propia (ver `carpeta_publicacion`).
_CARPETA_POR_DEFECTO = "revisa-carro-ec/publicaciones"

# Host de entrega (delivery) de Cloudinary. Las URLs válidas que aceptamos deben
# provenir de este host y de NUESTRO cloud (ver `url_es_de_nuestro_cloud`).
_HOST_ENTREGA = "res.cloudinary.com"


def nombre_cloud() -> str:
    """Nombre del cloud de Cloudinary (env). Cadena vacía si no está configurado."""
    return os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()


def _api_key() -> str:
    return os.getenv("CLOUDINARY_API_KEY", "").strip()


def _api_secret() -> str:
    return os.getenv("CLOUDINARY_API_SECRET", "").strip()


def carpeta_base() -> str:
    """Carpeta raíz configurada (o el default). Sin barras sobrantes."""
    return os.getenv("CLOUDINARY_UPLOAD_FOLDER", _CARPETA_POR_DEFECTO).strip().strip("/")


def esta_configurado() -> bool:
    """True solo si las tres credenciales de Cloudinary están presentes."""
    return bool(nombre_cloud() and _api_key() and _api_secret())


def carpeta_publicacion(publicacion_id: int) -> str:
    """Carpeta donde se suben las fotos de una publicación: `<base>/<id>`.

    Atar el `folder` a la publicación mantiene las fotos agrupadas y evita que el
    navegador suba a rutas arbitrarias (el `folder` va firmado).
    """
    return f"{carpeta_base()}/{publicacion_id}"


def _firmar_parametros(parametros: dict[str, str]) -> str:
    """SHA-1 hex de `k=v&...` (claves ordenadas) + api_secret. Excluye vacíos."""
    partes = [
        f"{clave}={valor}"
        for clave, valor in sorted(parametros.items())
        if valor != "" and valor is not None
    ]
    cadena = "&".join(partes) + _api_secret()
    return hashlib.sha1(cadena.encode("utf-8")).hexdigest()


def firmar_subida(folder: str, timestamp: int | None = None) -> dict:
    """Genera la firma que el navegador necesita para subir a Cloudinary.

    Devuelve todo lo que el cliente pasa al endpoint de subida de Cloudinary:
    `cloud_name`, `api_key`, `timestamp`, `signature` y `folder`. La firma es
    determinista: mismos `folder` + `timestamp` (+ mismo `api_secret`) ⇒ misma firma,
    lo que la hace reproducible en pruebas. `timestamp` se puede fijar para pruebas;
    en producción se usa el tiempo actual.
    """
    ts = int(time.time()) if timestamp is None else int(timestamp)
    a_firmar = {"folder": folder, "timestamp": str(ts)}
    firma = _firmar_parametros(a_firmar)
    return {
        "cloud_name": nombre_cloud(),
        "api_key": _api_key(),
        "timestamp": ts,
        "signature": firma,
        "folder": folder,
    }


def url_es_de_nuestro_cloud(url: str) -> bool:
    """True si `url` es https, del host de entrega de Cloudinary y de NUESTRO cloud.

    Bloquea que se registren URLs arbitrarias: solo aceptamos enlaces
    `https://res.cloudinary.com/<cloud_name>/...`. Requiere Cloudinary configurado
    (sin `cloud_name` no hay contra qué comparar).
    """
    cloud = nombre_cloud()
    if not cloud:
        return False
    try:
        partes = urlparse(url.strip())
    except (ValueError, AttributeError):
        return False
    if partes.scheme != "https":
        return False
    if (partes.hostname or "").lower() != _HOST_ENTREGA:
        return False
    # El primer segmento del path debe ser exactamente nuestro cloud_name.
    return partes.path.startswith(f"/{cloud}/")
