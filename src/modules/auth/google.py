"""Verificación del ID token de Google (Google Identity Services) y caché del JWKS.

El frontend obtiene un `credential` de GIS (un JWT firmado por Google) y lo manda **una
sola vez** a `POST /auth/google`. Aquí se verifica su firma y sus claims; el token se
descarta enseguida: no se guarda, no se reenvía y no se refresca. La sesión la sostiene
el JWT propio del proyecto (`security.crear_token_acceso`).

Se usa `python-jose` —ya instalado para el JWT propio— en vez de `google-auth`, para no
sumar cinco paquetes a una imagen Docker que ya arrastra Playwright y Chromium. La
contrapartida es que **las validaciones son nuestras**, y por eso cada una está escrita
explícita y comentada con el default de la librería que corrige.

`python-jose` está **pineado a 3.5.0** en `requirements.txt`: todo lo de abajo está
escrito contra el comportamiento interno de esa versión (qué valida `_validate_aud`, qué
opciones vienen en `False`, cómo `_get_keys` trata un JWK Set). Son detalles de
implementación, no API pública: si sube la versión hay que repetir la auditoría. Un
agujero de autenticación no falla ruidosamente, sigue devolviendo 200.

**El ID token NUNCA se registra** — ni en logs, ni en trazas, ni dentro del `detail` de
una excepción. Al capturar un fallo de jose se registra el *tipo* de error, jamás el
token que lo causó: la vía realista de filtración de un ID token no es la red, es
nuestro propio logging.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass

import httpx
from jose import JWTError, jwt


logger = logging.getLogger(__name__)


# Constantes del módulo, no env vars: no son secretos, no cambian por entorno, y cada
# variable de más es una forma más de desplegar mal (§7 de la spec). Los tests las
# sustituyen por monkeypatch.
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# Google emite las dos formas del issuer, con y sin esquema. Se aceptan ambas y nada más.
ISSUERS_GOOGLE = ("https://accounts.google.com", "accounts.google.com")
ALGORITMO_ESPERADO = "RS256"

# TTL por defecto del JWKS cacheado en memoria del proceso. Se honra el `max-age` del
# header `Cache-Control` de Google cuando sea parseable.
JWKS_TTL_SEGUNDOS = 3600
# Piso entre refrescos del JWKS. Sin él, un token basura con un `kid` inventado
# convierte cada request en un golpe al endpoint de claves de Google.
PISO_REFRESCO_SEGUNDOS = 300
TIMEOUT_JWKS_SEGUNDOS = 5.0

# Dominios cuyo buzón opera Google. Ver `identidad_google_autoritativa`.
# `googlemail.com` es el dominio alterno del mismo servicio: omitirlo crearía cuentas
# duplicadas para el mismo buzón real.
DOMINIOS_GOOGLE = ("gmail.com", "googlemail.com")


class CredencialGoogleInvalida(Exception):
    """El token no se puede creer: firma, `aud`, `azp`, `iss`, `exp`, `alg` o `kid`.

    El router la traduce a **401** con un mensaje genérico: no se detalla qué claim
    falló, para no darle a quien prueba tokens un oráculo de validación.
    """


class ClaimsGoogleInsuficientes(Exception):
    """El token es legítimo pero la identidad no sirve para identificar a nadie:
    `email_verified` distinto de `True`, o sin `email`. Es validación de negocio → 422.
    """


class GoogleNoDisponible(Exception):
    """Falta `GOOGLE_CLIENT_ID`, o el JWKS es inalcanzable y no hay caché válida.
    Es un fallo de despliegue, no del usuario → 503 (mismo precedente que
    `POST /consultar-foto` sin `GOOGLE_VISION_API_KEY`).
    """


@dataclass(frozen=True)
class ClaimsGoogle:
    """Los claims del ID token que este producto necesita, ya verificados.

    `hd` NO se persiste: no hay columna para él y la etapa 1 no tiene nada que hacer con
    dominios de Workspace. Vive solo para decidir autoritatividad (§0.1 de la spec).
    """

    sub: str
    email: str
    email_verificado: bool
    nombre: str | None = None
    hd: str | None = None


# ── Caché del JWKS (memoria del proceso) ─────────────────────────────────────────
# El lock es de `threading` a propósito: los handlers de `auth/router.py` son `def`
# síncronos, así que FastAPI los corre en el threadpool y la concurrencia es de hilos.
# Si algún día el endpoint pasara a `async def`, esto hay que revisarlo: un Lock de
# threading bloquearía el event loop.
_lock = threading.Lock()
_jwks: dict[str, dict] = {}
_jwks_expira_en: float = 0.0
# `-inf`, no 0.0: `time.monotonic()` cuenta desde el arranque de la máquina, así que en un
# contenedor recién levantado vale unos pocos segundos. Con 0.0, `ahora - _ultimo_refresco`
# daría menos que el piso durante los primeros 5 minutos de vida del proceso y NINGÚN
# refresco se permitiría — el login caído justo después de cada deploy, que es cuando más
# se mira. Con `-inf` la diferencia es infinita y el primer refresco siempre pasa.
_ultimo_refresco: float = float("-inf")


def _client_id() -> str:
    """`GOOGLE_CLIENT_ID` se lee del entorno **en el módulo**, como `GOOGLE_VISION_API_KEY`
    en `services/vision.py`. Por eso `src/core/database.py` no se toca."""
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


def _ttl_de_cache_control(cabecera: str | None) -> int:
    """Extrae `max-age` de un `Cache-Control`. Si no es parseable, cae al TTL propio."""
    if not cabecera:
        return JWKS_TTL_SEGUNDOS
    for parte in cabecera.split(","):
        parte = parte.strip().lower()
        if parte.startswith("max-age="):
            try:
                segundos = int(parte.split("=", 1)[1])
            except ValueError:
                return JWKS_TTL_SEGUNDOS
            # Un max-age absurdo (0 o negativo) haría un refresco por token.
            return segundos if segundos > 0 else JWKS_TTL_SEGUNDOS
    return JWKS_TTL_SEGUNDOS


def _refrescar_jwks() -> None:
    """Trae el JWKS de Google y reemplaza la caché. **Se llama con `_lock` tomado.**

    Marca el instante del intento en un `finally`: aunque Google falle, no se vuelve a
    intentar hasta que pase el piso. Reintentar en ráfaga contra una fuente caída es
    justo lo que prohíbe el skill `scraping-respetuoso`.
    """
    global _jwks, _jwks_expira_en, _ultimo_refresco

    try:
        with httpx.Client(timeout=TIMEOUT_JWKS_SEGUNDOS) as cliente:
            respuesta = cliente.get(JWKS_URL)
            respuesta.raise_for_status()
            documento = respuesta.json()
            ttl = _ttl_de_cache_control(respuesta.headers.get("cache-control"))
    except Exception as exc:  # red, HTTP, JSON: ninguna debe escapar como 500
        logger.warning("No se pudo traer el JWKS de Google: %s", type(exc).__name__)
        return
    finally:
        _ultimo_refresco = time.monotonic()

    claves = {}
    for clave in documento.get("keys", []) if isinstance(documento, dict) else []:
        kid = clave.get("kid")
        if isinstance(kid, str) and kid:
            claves[kid] = clave

    if not claves:
        logger.warning("El JWKS de Google llegó sin claves utilizables.")
        return

    _jwks = claves
    _jwks_expira_en = time.monotonic() + ttl


def _obtener_jwk(kid: str) -> dict | None:
    """Devuelve la JWK de ese `kid`, o `None` si no existe ni tras el refresco permitido.

    Todo —lectura de la caché, decisión de refrescar, piso de 5 minutos y escritura—
    ocurre **dentro del lock**: leer, decidir y escribir fuera de él es exactamente la
    carrera que hace que una ráfaga de N tokens con `kid` inventado se convierta en N
    golpes al endpoint de claves de Google. Patrón single-flight con doble comprobación:
    quien espera el lock encuentra el JWKS ya actualizado por el primero y no refresca.

    El alcance del límite es **por proceso** y eso es sabido: garantiza una llamada por
    proceso, no una en total. Hoy Render free corre una instancia. La coordinación
    distribuida es una mejora para cuando se escale, no un requisito de esta tarea.
    """
    with _lock:
        ahora = time.monotonic()

        # 1. Caché vigente y el `kid` está: el camino normal, sin red.
        if ahora < _jwks_expira_en and kid in _jwks:
            return _jwks[kid]

        # 2. Caché vencida (o vacía): toca refrescar por TTL.
        if ahora >= _jwks_expira_en:
            # El piso se respeta también acá, y no solo en el refresco forzado del punto
            # 3. La spec solo lo exige para el forzado, pero sin esto queda abierta la
            # misma puerta por el otro lado: con la caché vencida y Google caído, cada
            # petición vuelve a golpear su endpoint de claves — N peticiones, N golpes
            # contra una fuente que ya está sufriendo, que es justo lo que prohíbe el
            # skill `scraping-respetuoso`.
            #
            # El costo es explícito: si Google parpadea un segundo justo cuando vence el
            # TTL, los logins responden 503 hasta 5 minutos en vez de recuperarse solos.
            # Se elige no amplificar la caída ajena; con un TTL de 1 hora la ventana es
            # rara. Si algún día ese 503 molesta más que el golpeteo, se cambia acá.
            if ahora - _ultimo_refresco >= PISO_REFRESCO_SEGUNDOS:
                _refrescar_jwks()
            if ahora >= _jwks_expira_en:
                # El refresco no prosperó (si hubiera, habría movido la expiración al
                # futuro). Sin caché VÁLIDA y con Google inalcanzable: fallo de
                # despliegue, no del usuario. Una caché vencida no se sirve: con ella se
                # verificarían firmas contra claves que Google pudo haber rotado.
                raise GoogleNoDisponible(
                    "No se pudo verificar la credencial con Google en este momento."
                )
            # Se acaba de consultar a Google: si el kid no está, no está. No se vuelve
            # a pedir (el piso, que `_refrescar_jwks` acaba de marcar, lo impide igual).
            return _jwks.get(kid)

        # 3. Caché vigente pero `kid` desconocido: puede ser una rotación legítima de
        #    claves. Se fuerza UN refresco, respetando el piso.
        if ahora - _ultimo_refresco >= PISO_REFRESCO_SEGUNDOS:
            _refrescar_jwks()

        return _jwks.get(kid)


def verificar_id_token_google(id_token: str) -> ClaimsGoogle:
    """Verifica firma y claims del ID token de Google y devuelve la identidad.

    Lanza `CredencialGoogleInvalida` (→401), `ClaimsGoogleInsuficientes` (→422) o
    `GoogleNoDisponible` (→503). Nunca devuelve datos sin verificar.
    """
    cliente_id = _client_id()
    if not cliente_id:
        raise GoogleNoDisponible("El inicio de sesión con Google no está configurado.")

    # ── Cabecera: entrada hostil, se usa SOLO para seleccionar la clave ───────────
    try:
        cabecera = jwt.get_unverified_header(id_token)
    except Exception as exc:  # jose envuelve el fallo de base64/JSON de varias formas
        logger.info("Cabecera de ID token ilegible: %s", type(exc).__name__)
        raise CredencialGoogleInvalida("Credenciales de Google inválidas") from exc

    # Nunca se lee el `alg` de la cabecera para decidir CÓMO verificar (esa es la puerta
    # de la confusión de algoritmos: `none`, o HS256 firmado con la clave pública como
    # secreto). Se exige que declare el único que aceptamos y se rechaza el resto.
    if cabecera.get("alg") != ALGORITMO_ESPERADO:
        raise CredencialGoogleInvalida("Credenciales de Google inválidas")

    kid = cabecera.get("kid")
    if not isinstance(kid, str) or not kid:
        # `kid` ausente = token malformado. Se rechaza SIN tocar el JWKS: refrescar acá
        # sería un vector de DoS contra el endpoint de claves de Google (basta con mandar
        # tokens sin `kid`). No hay excepción ni "por si acaso".
        raise CredencialGoogleInvalida("Credenciales de Google inválidas")

    jwk_elegida = _obtener_jwk(kid)
    if jwk_elegida is None:
        # `kid` presente pero desconocido incluso tras el refresco permitido.
        raise CredencialGoogleInvalida("Credenciales de Google inválidas")

    # ── Verificación criptográfica ───────────────────────────────────────────────
    # Se le pasa UNA sola JWK, no el set: `jose._get_keys` devuelve el set entero sin
    # filtrar y `_sig_matches_keys` prueba todas las claves hasta que alguna valide, lo
    # que dejaría el `kid` sin validar. Con una sola clave, un token cuyo `kid` miente
    # falla en vez de colarse porque otra clave del set casualmente sirvió.
    try:
        claims = jwt.decode(
            id_token,
            jwk_elegida,
            algorithms=[ALGORITMO_ESPERADO],
            audience=cliente_id,
            issuer=ISSUERS_GOOGLE,
            options={
                # `_validate_aud` hace `if "aud" not in claims: return` (el raise está
                # comentado en la librería) y `require_aud` viene en False: sin esto, un
                # token SIN `aud` pasa en silencio.
                "require_aud": True,
                # `verify_exp` viene en True pero `require_exp` en False: un token sin
                # `exp` no expira nunca y pasaría. Es la única protección temporal real.
                "require_exp": True,
                # NO es una protección temporal: solo exige que el claim exista. Un token
                # emitido hace 50 minutos con `exp` vigente lo satisface igual. Se pide
                # porque `iat` es obligatorio en un ID token de OIDC.
                "require_iat": True,
                # `sub` es lo que se escribe en `id_google`.
                "require_sub": True,
                # Defensa en profundidad: quien valida el VALOR del issuer es el
                # parámetro `issuer=` de arriba (`_validate_iss` no hace nada si no se
                # pasa). Esto solo exige que el claim esté presente.
                "require_iss": True,
                # Obligatorio o el flujo no funciona: `_validate_at_hash` lanza si el
                # claim está y no hay `access_token` que comparar. En este flujo no
                # existe access token. No debilita nada: `at_hash` solo liga el ID token
                # a un access token que aquí no hay.
                "verify_at_hash": False,
            },
        )
    except JWTError as exc:
        # Se registra el TIPO de fallo, jamás el token (§5.6, mitigación 3).
        logger.info("ID token de Google rechazado: %s", type(exc).__name__)
        raise CredencialGoogleInvalida("Credenciales de Google inválidas") from exc

    # ── Claims que jose no comprueba y hay que revisar a mano ────────────────────
    # `aud` debe ser EXACTAMENTE el nuestro. jose valida pertenencia, no igualdad:
    # `if audience not in audience_claims` acepta `aud: [nuestro_id, otro_id]`. Un ID
    # token con audiencia múltiple no fue emitido para nosotros en exclusiva, y aceptarlo
    # permite que otra aplicación reutilice contra nuestro backend un token que sus
    # usuarios le entregaron a ella.
    aud = claims.get("aud")
    if isinstance(aud, list):
        aud_exacto = len(aud) == 1 and aud[0] == cliente_id
    else:
        aud_exacto = aud == cliente_id
    if not aud_exacto:
        raise CredencialGoogleInvalida("Credenciales de Google inválidas")

    # `azp` (authorized party) nombra la aplicación a la que Google entregó el token.
    # jose no lo mira en absoluto. Presente-y-distinto es una contradicción: se rechaza,
    # nunca se ignora.
    if "azp" in claims and claims.get("azp") != cliente_id:
        raise CredencialGoogleInvalida("Credenciales de Google inválidas")

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise CredencialGoogleInvalida("Credenciales de Google inválidas")

    # A partir de acá el token es creíble; lo que falta es si la identidad sirve.
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise ClaimsGoogleInsuficientes(
            "Tu cuenta de Google no compartió un correo. Revisa los permisos e inténtalo de nuevo."
        )

    # `is True` a propósito: un `"true"` en string no es un booleano y no se acomoda por
    # cuenta propia. Si alguna variante del token lo mandara así, se reporta.
    if claims.get("email_verified") is not True:
        raise ClaimsGoogleInsuficientes(
            "Google no confirma que ese correo sea tuyo. Verifícalo en tu cuenta de Google."
        )

    hd = claims.get("hd")
    nombre = claims.get("name")
    return ClaimsGoogle(
        sub=sub,
        email=email.strip(),
        email_verificado=True,
        nombre=nombre if isinstance(nombre, str) and nombre.strip() else None,
        hd=hd if isinstance(hd, str) else None,
    )


def identidad_google_autoritativa(claims: ClaimsGoogle) -> bool:
    """¿Esta identidad de Google alcanza para tomar posesión de una cuenta ya existente?

    **Solo gobierna el enlace a una cuenta preexistente**, que es donde está el riesgo.
    Un alta nueva no necesita ser autoritativa: sin cuenta previa no hay nada que tomar.

    `email_verified: true` NO alcanza: el claim afirma que *en algún momento* Google
    comprobó que quien creó esa cuenta controlaba ese buzón, no que **hoy** lo controle.
    Un correo corporativo se reasigna al rotar el personal, un dominio caduca y lo compra
    otro, un proveedor recicla direcciones abandonadas. Quien reciba hoy ese correo puede
    crear una cuenta de Google con él y `email_verified` llegaría en `true` describiendo
    una verificación vieja: vincular por ese claim entregaría la cuenta que otra persona
    tiene en la plataforma, con sus vehículos y su saldo.

    Es autoritativa cuando `email_verified is True` y además:

    - el dominio del correo es `gmail.com` / `googlemail.com` → Google **es** el dueño
      del dominio y el operador del buzón: la dirección no cambió de manos fuera de
      Google; o
    - viene el claim `hd` → la cuenta pertenece a un dominio de Google Workspace, cuyo
      administrador controla hoy ese buzón y puede desactivarla.

    Cualquier otro caso (incluida una cuenta de Google creada con un `@hotmail.com`
    verificado) **no** auto-enlaza. Si esa regla parece excesiva, léase de nuevo el
    párrafo de arriba: ya se intentó vincular por email a secas y era una toma de cuenta.
    """
    if claims.email_verificado is not True:
        return False

    if claims.hd is not None and claims.hd.strip():
        return True

    dominio = claims.email.rsplit("@", 1)[-1].strip().lower()
    return dominio in DOMINIOS_GOOGLE
