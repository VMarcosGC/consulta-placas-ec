"""Pruebas del login con Google (TASK-015, migración 0025).

Cubren las tres capas donde esto se rompe en silencio:

1. **Verificación del ID token** (`src/modules/auth/google.py`): audiencia exacta, `azp`,
   issuer, `exp`, algoritmo y selección de la clave por `kid`. Un fallo acá no produce un
   stacktrace: sigue devolviendo 200 con la identidad equivocada, así que cada regla
   tiene su prueba negativa.
2. **Caché del JWKS**: cuándo se golpea al endpoint de claves de Google y cuándo no,
   incluida la **ráfaga paralela** que distingue un single-flight real de la intención de
   tener uno. Esa prueba **no** se puede sustituir por una secuencial: la implementación
   ingenua pasa la secuencial y falla la paralela, que es el punto.
3. **Resolución de la cuenta** en `/auth/google` y `/auth/google/vincular`: el orden
   `id_google` → email → alta, la regla de identidad autoritativa (que existe para que
   `email_verified` no sirva para tomar posesión de una cuenta ajena) y el saldo de
   cortesía exactamente una vez.

No requieren PostgreSQL ni red: las claves RSA se generan en el proceso, el JWKS se
sustituye por un doble que cuenta invocaciones y la sesión de SQLAlchemy se aísla con un
falso que registra lo que se le agrega. Lo que no se puede probar así queda dicho en el
reporte de la tarea, no simulado acá.

Se usa `unittest` de la stdlib (el repo no tiene pytest y no se agrega una dependencia
por esto, §4):

    python -m unittest tests.test_login_google -v
"""

import json
import os
import threading
import time
import unittest
from base64 import urlsafe_b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwt

import main
from src.core.database import obtener_sesion
from src.modules.auth import google
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import SALDO_INICIAL_TOKENS, TransaccionToken, Usuario
from src.modules.auth.google import ClaimsGoogle, identidad_google_autoritativa
from src.modules.auth.security import crear_token_acceso, decodificar_token


CLIENT_ID = "1234567890-pruebas.apps.googleusercontent.com"
OTRO_CLIENT_ID = "9999999999-ajeno.apps.googleusercontent.com"
SUB_GOOGLE = "110000000000000000001"

KID_A = "clave-a"
KID_B = "clave-b"
KID_AJENA = "clave-que-no-publicamos"

# Sentinela para pedir que un claim NO aparezca en el token (distinto de `None`, que sí
# aparecería con valor nulo).
AUSENTE = object()


# ── Claves RSA de prueba ────────────────────────────────────────────────────────────
# Se generan una vez por proceso. A y B se publican en el JWKS falso; la tercera nunca,
# para poder firmar un token con una clave que Google no reconoce.

def _b64_entero(valor: int) -> str:
    crudo = valor.to_bytes((valor.bit_length() + 7) // 8, "big")
    return urlsafe_b64encode(crudo).rstrip(b"=").decode("ascii")


def _generar_clave(kid: str):
    """Devuelve (PEM privado, JWK pública) listos para firmar y para el JWKS falso."""
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    numeros = privada.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
        "n": _b64_entero(numeros.n),
        "e": _b64_entero(numeros.e),
    }
    return pem, jwk


PEM_A, JWK_A = _generar_clave(KID_A)
PEM_B, JWK_B = _generar_clave(KID_B)
PEM_AJENA, _JWK_AJENA = _generar_clave(KID_AJENA)

JWKS_GOOGLE = {"keys": [JWK_A, JWK_B]}


# ── Doble del JWKS ──────────────────────────────────────────────────────────────────

class RespuestaFalsa:
    def __init__(self, documento, cache_control):
        self._documento = documento
        self.headers = {"cache-control": cache_control} if cache_control else {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._documento


class DobleJWKS:
    """Sustituye a `httpx.Client` dentro de `google.py` y **cuenta sus invocaciones**.

    El contador es lo que distingue las reglas de refresco: `kid` ausente debe dar cero
    llamadas, `kid` desconocido exactamente una, y una ráfaga de 20 también una.

    `retraso` alarga la llamada a propósito: sin él, la prueba de ráfaga podría pasar por
    casualidad incluso sin el lock, porque el GIL alcanzaría a serializar los hilos.
    """

    def __init__(self, documento=None, retraso=0.0, falla=False,
                 cache_control="public, max-age=3600"):
        self.documento = JWKS_GOOGLE if documento is None else documento
        self.retraso = retraso
        self.falla = falla
        self.cache_control = cache_control
        self.llamadas = 0
        self._lock = threading.Lock()

    # httpx.Client(timeout=...)
    def __call__(self, timeout=None):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url):
        with self._lock:
            self.llamadas += 1
        if self.retraso:
            time.sleep(self.retraso)
        if self.falla:
            raise RuntimeError("no hay red")
        return RespuestaFalsa(self.documento, self.cache_control)


# ── Sesión falsa ────────────────────────────────────────────────────────────────────

class ResultadoFalso:
    def __init__(self, valor):
        if isinstance(valor, list):
            self._lista = valor
            self._unico = valor[0] if len(valor) == 1 else None
        else:
            self._lista = [] if valor is None else [valor]
            self._unico = valor

    def scalar_one_or_none(self):
        return self._unico

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._lista))


class SesionFalsa:
    """Sesión de SQLAlchemy sustituida: cada `execute()` devuelve el siguiente resultado.

    `commit()` aplica los defaults **de Python** declarados en las columnas (lo mismo que
    haría el INSERT real con `saldo_tokens`, `proveedor_autenticacion` y
    `email_verificado`), para poder afirmar sobre ellos sin levantar Postgres. Los
    `server_default` que solo existen en la BD (`creado_en`) se rellenan a mano.
    """

    def __init__(self, resultados=()):
        self._resultados = list(resultados)
        self.agregados = []
        self.commits = 0
        self.consultas = 0

    def execute(self, *_a, **_k):
        self.consultas += 1
        valor = self._resultados.pop(0) if self._resultados else None
        return ResultadoFalso(valor)

    def add(self, obj):
        self.agregados.append(obj)

    def commit(self):
        self.commits += 1
        for obj in self.agregados:
            self._materializar(obj)

    def refresh(self, obj):
        self._materializar(obj)

    def close(self):
        return None

    @staticmethod
    def _materializar(obj):
        if not isinstance(obj, Usuario):
            return
        for columna in Usuario.__table__.columns:
            defecto = columna.default
            if defecto is not None and not defecto.is_callable:
                if getattr(obj, columna.name, None) is None:
                    setattr(obj, columna.name, defecto.arg)
        if obj.id is None:
            obj.id = 99
        if obj.creado_en is None:
            obj.creado_en = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


# ── Constructores de tokens ─────────────────────────────────────────────────────────

def claims_google(**cambios):
    ahora = int(time.time())
    base = {
        "iss": "https://accounts.google.com",
        "azp": CLIENT_ID,
        "aud": CLIENT_ID,
        "sub": SUB_GOOGLE,
        "email": "ana@gmail.com",
        "email_verified": True,
        "name": "Ana Pérez",
        "iat": ahora,
        "exp": ahora + 3600,
    }
    base.update(cambios)
    return {clave: valor for clave, valor in base.items() if valor is not AUSENTE}


def firmar(claims, kid=KID_A, pem=PEM_A):
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})


def firmar_sin_kid(claims):
    return jwt.encode(claims, PEM_A, algorithm="RS256")


def token_alg_none(claims):
    """`alg: none` se arma a mano: no hace falta ninguna clave, y esa es la gracia."""
    def _b64(datos):
        return urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()

    return f"{_b64({'alg': 'none', 'typ': 'JWT', 'kid': KID_A})}.{_b64(claims)}."


def reiniciar_jwks(claves=(JWK_A, JWK_B), vigente=True, refresco_hace=10_000):
    """Deja la caché del módulo en un estado conocido antes de cada prueba."""
    google._jwks = {jwk["kid"]: jwk for jwk in claves}
    google._jwks_expira_en = time.monotonic() + 3600 if vigente else 0.0
    google._ultimo_refresco = time.monotonic() - refresco_hace


class BaseGoogle(unittest.TestCase):
    """Entorno común: `GOOGLE_CLIENT_ID` configurado, JWKS en caché y doble instalado."""

    def setUp(self):
        parche_env = patch.dict(os.environ, {"GOOGLE_CLIENT_ID": CLIENT_ID})
        parche_env.start()
        self.addCleanup(parche_env.stop)

        self.doble = DobleJWKS()
        parche_httpx = patch.object(
            google, "httpx", SimpleNamespace(Client=self.doble)
        )
        parche_httpx.start()
        self.addCleanup(parche_httpx.stop)

        reiniciar_jwks()
        self.addCleanup(reiniciar_jwks)

        self.cliente = TestClient(main.app)
        self.addCleanup(main.app.dependency_overrides.clear)

    def sesion(self, resultados=()):
        sesion = SesionFalsa(resultados)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        return sesion

    def entrar(self, token, resultados=()):
        self.sesion(resultados)
        return self.cliente.post("/auth/google", json={"id_token": token})


def usuario_local(email="juan@hotmail.com", id_=7, id_google=None, saldo=5):
    usuario = Usuario(
        id=id_,
        email=email,
        password_hash="$2b$12$hash-falso",
        nombre="Juan",
        saldo_tokens=saldo,
        proveedor_autenticacion="local",
        id_google=id_google,
        email_verificado=False,
        creado_en=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return usuario


# ════════════════════════════════════════════════════════════════════════════════════
# 1. Identidad autoritativa — la regla como función, sin HTTP
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaIdentidadAutoritativa(unittest.TestCase):
    """`email_verified: true` NO alcanza para tomar posesión de una cuenta existente.

    El claim afirma que en ALGÚN momento Google comprobó el buzón, no que hoy lo controle
    la misma persona: los correos corporativos se reasignan y los dominios caducan. Solo
    es autoritativa una identidad cuyo buzón opere Google (gmail/googlemail) o que
    pertenezca a un dominio de Workspace (`hd`).
    """

    @staticmethod
    def _claims(email, verificado=True, hd=None):
        return ClaimsGoogle(
            sub=SUB_GOOGLE, email=email, email_verificado=verificado, hd=hd
        )

    def test_gmail_es_autoritativa(self):
        self.assertTrue(identidad_google_autoritativa(self._claims("ana@gmail.com")))

    def test_googlemail_se_trata_igual_que_gmail(self):
        # Dominio alterno del mismo servicio: omitirlo crearía cuentas duplicadas para el
        # mismo buzón real.
        self.assertTrue(
            identidad_google_autoritativa(self._claims("ana@googlemail.com"))
        )

    def test_mayusculas_del_dominio_no_importan(self):
        self.assertTrue(identidad_google_autoritativa(self._claims("Ana@GMAIL.com")))

    def test_workspace_con_hd_es_autoritativa(self):
        self.assertTrue(
            identidad_google_autoritativa(
                self._claims("gerencia@empresa.com.ec", hd="empresa.com.ec")
            )
        )

    def test_hd_vacio_no_es_autoritativa(self):
        self.assertFalse(
            identidad_google_autoritativa(self._claims("gerencia@empresa.com", hd=""))
        )

    def test_correo_externo_sin_hd_no_es_autoritativa(self):
        # El caso que la revisión 1 aceptaba y era una toma de cuenta.
        self.assertFalse(identidad_google_autoritativa(self._claims("juan@hotmail.com")))
        self.assertFalse(identidad_google_autoritativa(self._claims("juan@yahoo.com")))
        self.assertFalse(identidad_google_autoritativa(self._claims("j@dominio.propio")))

    def test_email_no_verificado_nunca_es_autoritativa(self):
        self.assertFalse(
            identidad_google_autoritativa(
                self._claims("ana@gmail.com", verificado=False)
            )
        )
        self.assertFalse(
            identidad_google_autoritativa(
                self._claims("gerencia@empresa.com", verificado=False, hd="empresa.com")
            )
        )


# ════════════════════════════════════════════════════════════════════════════════════
# 2. Verificación criptográfica del ID token
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaVerificacionToken(BaseGoogle):

    def test_token_legitimo_entra(self):
        respuesta = self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertEqual(respuesta.status_code, 200)

    def test_los_dos_issuers_de_google_son_validos(self):
        for issuer in ("https://accounts.google.com", "accounts.google.com"):
            with self.subTest(issuer=issuer):
                respuesta = self.entrar(
                    firmar(claims_google(iss=issuer)), resultados=[None, []]
                )
                self.assertEqual(respuesta.status_code, 200)

    def test_issuer_desconocido_rechaza(self):
        respuesta = self.entrar(firmar(claims_google(iss="https://malicioso.example")))
        self.assertEqual(respuesta.status_code, 401)

    def test_token_sin_issuer_rechaza(self):
        respuesta = self.entrar(firmar(claims_google(iss=AUSENTE)))
        self.assertEqual(respuesta.status_code, 401)

    def test_aud_de_otro_client_id_rechaza(self):
        respuesta = self.entrar(
            firmar(claims_google(aud=OTRO_CLIENT_ID, azp=OTRO_CLIENT_ID))
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_token_sin_aud_rechaza(self):
        # Prueba directa de `require_aud`: jose trae la opción en False y `_validate_aud`
        # hace `if "aud" not in claims: return` — sin la opción, un ID token emitido para
        # CUALQUIER otra aplicación entraría a la plataforma.
        respuesta = self.entrar(firmar(claims_google(aud=AUSENTE)))
        self.assertEqual(respuesta.status_code, 401)

    def test_aud_como_lista_con_nuestro_id_y_otro_rechaza(self):
        # jose valida PERTENENCIA, no igualdad: esto pasa su `_validate_aud` y lo tiene
        # que atajar código nuestro. Sin esta prueba el bug es invisible.
        respuesta = self.entrar(
            firmar(claims_google(aud=[CLIENT_ID, OTRO_CLIENT_ID]))
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_aud_como_lista_de_un_solo_elemento_nuestro_entra(self):
        respuesta = self.entrar(
            firmar(claims_google(aud=[CLIENT_ID])), resultados=[None, []]
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_azp_distinto_con_aud_correcto_rechaza(self):
        # `azp` nombra la aplicación a la que Google entregó el token. Presente y
        # distinto es una contradicción; jose no lo mira en absoluto.
        respuesta = self.entrar(firmar(claims_google(azp=OTRO_CLIENT_ID)))
        self.assertEqual(respuesta.status_code, 401)

    def test_token_sin_azp_entra(self):
        respuesta = self.entrar(
            firmar(claims_google(azp=AUSENTE)), resultados=[None, []]
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_token_sin_exp_rechaza(self):
        # Prueba directa de `require_exp`: es la única protección temporal real.
        respuesta = self.entrar(firmar(claims_google(exp=AUSENTE)))
        self.assertEqual(respuesta.status_code, 401)

    def test_token_expirado_rechaza(self):
        ayer = int(time.time()) - 86400
        respuesta = self.entrar(firmar(claims_google(iat=ayer, exp=ayer + 3600)))
        self.assertEqual(respuesta.status_code, 401)

    def test_token_sin_iat_rechaza(self):
        respuesta = self.entrar(firmar(claims_google(iat=AUSENTE)))
        self.assertEqual(respuesta.status_code, 401)

    def test_token_sin_sub_rechaza(self):
        respuesta = self.entrar(firmar(claims_google(sub=AUSENTE)))
        self.assertEqual(respuesta.status_code, 401)

    def test_firma_con_otra_clave_rsa_rechaza(self):
        respuesta = self.entrar(firmar(claims_google(), kid=KID_A, pem=PEM_AJENA))
        self.assertEqual(respuesta.status_code, 401)

    def test_kid_que_apunta_a_una_clave_distinta_de_la_que_firmo_rechaza(self):
        # Firmado con A, cabecera diciendo B. Si se le pasara el JWK Set completo a jose,
        # probaría todas las claves y ESTO DARÍA 200: es la prueba de que seleccionamos
        # UNA clave por `kid`.
        respuesta = self.entrar(firmar(claims_google(), kid=KID_B, pem=PEM_A))
        self.assertEqual(respuesta.status_code, 401)

    def test_alg_none_rechaza(self):
        respuesta = self.entrar(token_alg_none(claims_google()))
        self.assertEqual(respuesta.status_code, 401)

    def test_alg_hs256_rechaza(self):
        # Confusión de algoritmos: HS256 firmado con un secreto cualquiera.
        token = jwt.encode(
            claims_google(), "secreto", algorithm="HS256", headers={"kid": KID_A}
        )
        respuesta = self.entrar(token)
        self.assertEqual(respuesta.status_code, 401)

    def test_basura_en_lugar_de_token_rechaza(self):
        respuesta = self.entrar("esto-no-es-un-jwt")
        self.assertEqual(respuesta.status_code, 401)

    def test_el_detalle_del_401_es_generico(self):
        respuesta = self.entrar(firmar(claims_google(iss="https://malicioso.example")))
        self.assertEqual(respuesta.json()["detail"], "Credenciales de Google inválidas")

    def test_email_no_verificado_da_422_y_no_toca_la_base(self):
        sesion = self.sesion()
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email_verified=False))},
        )
        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(sesion.agregados, [])
        self.assertEqual(sesion.commits, 0)
        self.assertEqual(sesion.consultas, 0)

    def test_token_sin_email_da_422(self):
        respuesta = self.entrar(firmar(claims_google(email=AUSENTE)))
        self.assertEqual(respuesta.status_code, 422)

    def test_email_verified_como_string_no_se_acomoda(self):
        # La regla escrita es `is True`, a propósito. Si Google mandara `"true"`, esto se
        # reporta antes que ampliar la comparación por cuenta propia.
        respuesta = self.entrar(firmar(claims_google(email_verified="true")))
        self.assertEqual(respuesta.status_code, 422)

    def test_sin_google_client_id_da_503(self):
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": ""}):
            respuesta = self.entrar(firmar(claims_google()))
        self.assertEqual(respuesta.status_code, 503)


# ════════════════════════════════════════════════════════════════════════════════════
# 3. Caché del JWKS: cuándo se golpea a Google y cuándo no
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaCacheJWKS(BaseGoogle):

    def test_token_valido_con_cache_vigente_no_llama_a_google(self):
        self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertEqual(self.doble.llamadas, 0)

    def test_cabecera_sin_kid_rechaza_sin_tocar_el_jwks(self):
        # Refrescar ante un `kid` ausente sería un DoS contra el endpoint de claves de
        # Google: bastaría con mandar tokens basura. Cero llamadas, sin excepción.
        respuesta = self.entrar(firmar_sin_kid(claims_google()))
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(self.doble.llamadas, 0)

    def test_alg_invalido_rechaza_sin_tocar_el_jwks(self):
        self.entrar(token_alg_none(claims_google()))
        self.assertEqual(self.doble.llamadas, 0)

    def test_kid_desconocido_fuerza_un_refresco_y_rechaza(self):
        # Caso distinto del anterior: `kid` presente puede ser una rotación legítima de
        # claves, así que se pide el JWKS UNA vez. Si sigue sin estar, 401.
        respuesta = self.entrar(firmar(claims_google(), kid=KID_AJENA, pem=PEM_AJENA))
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(self.doble.llamadas, 1)

    def test_segundo_kid_desconocido_dentro_de_los_cinco_minutos_no_vuelve_a_llamar(self):
        self.entrar(firmar(claims_google(), kid=KID_AJENA, pem=PEM_AJENA))
        self.assertEqual(self.doble.llamadas, 1)
        self.entrar(firmar(claims_google(), kid="otro-kid-inventado", pem=PEM_AJENA))
        self.assertEqual(self.doble.llamadas, 1)

    def test_rotacion_legitima_se_absorbe_sin_esperar_al_ttl(self):
        # La caché solo tiene A; Google ya publica A y B. Un token firmado con B entra
        # gracias al refresco forzado.
        reiniciar_jwks(claves=(JWK_A,))
        respuesta = self.entrar(
            firmar(claims_google(), kid=KID_B, pem=PEM_B), resultados=[None, []]
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.doble.llamadas, 1)

    def test_cache_vencida_se_refresca_una_vez(self):
        reiniciar_jwks(claves=(), vigente=False)
        respuesta = self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.doble.llamadas, 1)

    def test_jwks_inalcanzable_sin_cache_valida_da_503(self):
        reiniciar_jwks(claves=(), vigente=False)
        self.doble.falla = True
        respuesta = self.entrar(firmar(claims_google()))
        self.assertEqual(respuesta.status_code, 503)

    def test_google_caido_no_se_golpea_una_vez_por_peticion(self):
        # Con la caché vencida y Google inalcanzable, sin el piso cada petición volvería
        # a golpear su endpoint de claves: N peticiones, N golpes contra una fuente que
        # ya está sufriendo. Sigue respondiendo 503, pero sin amplificar la caída.
        reiniciar_jwks(claves=(), vigente=False)
        self.doble.falla = True
        for _ in range(5):
            self.assertEqual(self.entrar(firmar(claims_google())).status_code, 503)
        self.assertEqual(self.doble.llamadas, 1)

    def test_proceso_recien_arrancado_puede_refrescar(self):
        # `time.monotonic()` cuenta desde el arranque de la máquina: en un contenedor
        # recién levantado vale unos segundos. Si el piso partiera de 0.0, el primer
        # refresco quedaría bloqueado 5 minutos y el login estaría caído justo después
        # de cada deploy.
        google._jwks = {}
        google._jwks_expira_en = 0.0
        google._ultimo_refresco = float("-inf")
        respuesta = self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.doble.llamadas, 1)

    def test_jwks_inalcanzable_con_cache_valida_sigue_sirviendo(self):
        self.doble.falla = True
        respuesta = self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.doble.llamadas, 0)

    def test_max_age_del_cache_control_se_honra(self):
        reiniciar_jwks(claves=(), vigente=False)
        self.doble.cache_control = "public, max-age=120"
        antes = time.monotonic()
        self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertLessEqual(google._jwks_expira_en - antes, 121)
        self.assertGreater(google._jwks_expira_en - antes, 60)

    def test_cache_control_sin_max_age_cae_al_ttl_propio(self):
        reiniciar_jwks(claves=(), vigente=False)
        self.doble.cache_control = "no-store"
        antes = time.monotonic()
        self.entrar(firmar(claims_google()), resultados=[None, []])
        self.assertGreater(google._jwks_expira_en - antes, 3000)


class PruebaRafagaParalela(BaseGoogle):
    """El single-flight del refresco forzado, con concurrencia real.

    **No se puede sustituir por una prueba secuencial.** La carrera es leer el último
    refresco, decidir y escribirlo sin exclusión mutua: N peticiones simultáneas con un
    `kid` inventado leen todas el mismo valor viejo, todas concluyen "puedo refrescar" y
    todas golpean a Google a la vez. El piso de 5 minutos no protege, porque nadie llegó
    todavía a escribirlo cuando las demás decidieron.

    Con el lock: 20 peticiones → **una** llamada. Sin el lock: ~20, y esta prueba falla,
    que es exactamente lo que tiene que hacer.
    """

    PETICIONES = 20

    def test_veinte_peticiones_simultaneas_producen_una_sola_llamada(self):
        # El retraso mantiene abierta la ventana de la carrera durante el fetch, para que
        # el resultado no dependa de cómo el GIL reparta los hilos.
        self.doble.retraso = 0.05
        self.sesion()

        barrera = threading.Barrier(self.PETICIONES)
        tokens = [
            firmar(claims_google(sub=f"{SUB_GOOGLE}{i}"), kid=KID_AJENA, pem=PEM_AJENA)
            for i in range(self.PETICIONES)
        ]

        def _pedir(token):
            barrera.wait()
            return self.cliente.post("/auth/google", json={"id_token": token}).status_code

        with ThreadPoolExecutor(max_workers=self.PETICIONES) as pool:
            codigos = list(pool.map(_pedir, tokens))

        self.assertEqual(codigos, [401] * self.PETICIONES)
        self.assertEqual(self.doble.llamadas, 1)


# ════════════════════════════════════════════════════════════════════════════════════
# 4. Resolución de la cuenta en /auth/google
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaResolucionCuenta(BaseGoogle):

    def test_alta_nueva_crea_usuario_con_saldo_y_una_transaccion(self):
        sesion = self.sesion([None, []])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="nueva@gmail.com"))},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["token_type"], "bearer")
        # El JWT que sale es el NUESTRO, con `sub=<email>`: el frontend no distingue de
        # dónde vino la sesión.
        self.assertEqual(
            decodificar_token(respuesta.json()["access_token"]), "nueva@gmail.com"
        )

        self.assertEqual(len(sesion.agregados), 1)
        creado = sesion.agregados[0]
        self.assertEqual(creado.email, "nueva@gmail.com")
        self.assertIsNone(creado.password_hash)
        self.assertEqual(creado.id_google, SUB_GOOGLE)
        self.assertTrue(creado.email_verificado)
        self.assertEqual(creado.proveedor_autenticacion, "google")
        self.assertEqual(creado.nombre, "Ana Pérez")
        self.assertEqual(creado.saldo_tokens, SALDO_INICIAL_TOKENS)
        self.assertEqual(SALDO_INICIAL_TOKENS, 5)

        transacciones = list(creado.transacciones_tokens)
        self.assertEqual(len(transacciones), 1)
        self.assertEqual(transacciones[0].motivo, "saldo_inicial")
        self.assertEqual(transacciones[0].monto, SALDO_INICIAL_TOKENS)

    def test_cuenta_hallada_por_id_google_entra_sin_tocar_el_email(self):
        # Aunque Google mande hoy otro correo, el email guardado NO se actualiza: es el
        # `sub` de nuestro JWT y la clave de negocio de toda la app.
        usuario = usuario_local(email="viejo@gmail.com", id_google=SUB_GOOGLE)
        sesion = self.sesion([usuario])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="nuevo@gmail.com"))},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            decodificar_token(respuesta.json()["access_token"]), "viejo@gmail.com"
        )
        self.assertEqual(usuario.email, "viejo@gmail.com")
        self.assertEqual(sesion.agregados, [])
        self.assertEqual(sesion.commits, 0)

    def test_gmail_existente_vincula_sin_acreditar_tokens_de_nuevo(self):
        usuario = usuario_local(email="ana@gmail.com", saldo=5)
        sesion = self.sesion([None, [usuario]])
        respuesta = self.cliente.post(
            "/auth/google", json={"id_token": firmar(claims_google(email="ana@gmail.com"))}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)
        self.assertTrue(usuario.email_verificado)
        # La cuenta se creó local y eso no cambia por vincular Google.
        self.assertEqual(usuario.proveedor_autenticacion, "local")
        # Y conserva su contraseña: `proveedor_autenticacion` no es una exclusividad.
        self.assertIsNotNone(usuario.password_hash)
        # El saldo no se mueve y NO aparece una segunda `saldo_inicial`: si no, quien
        # descubriera que puede entrar por Google se llevaría 10 tokens.
        self.assertEqual(usuario.saldo_tokens, 5)
        self.assertEqual(list(usuario.transacciones_tokens), [])
        self.assertEqual(sesion.agregados, [])

    def test_googlemail_tambien_vincula(self):
        usuario = usuario_local(email="ana@googlemail.com")
        self.sesion([None, [usuario]])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="ana@googlemail.com"))},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)

    def test_email_con_distinta_capitalizacion_vincula_y_no_crea_otra_fila(self):
        # Sin la búsqueda insensible a mayúsculas, esto saltaría al alta e intentaría
        # insertar una segunda fila con el mismo correo real → IntegrityError → 500.
        usuario = usuario_local(email="Marcos@Gmail.com")
        sesion = self.sesion([None, [usuario]])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="marcos@gmail.com"))},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)
        self.assertEqual(sesion.agregados, [])
        self.assertEqual(usuario.email, "Marcos@Gmail.com")

    def test_workspace_con_hd_vincula_cuenta_existente(self):
        usuario = usuario_local(email="gerencia@empresa.com.ec")
        self.sesion([None, [usuario]])
        respuesta = self.cliente.post(
            "/auth/google",
            json={
                "id_token": firmar(
                    claims_google(email="gerencia@empresa.com.ec", hd="empresa.com.ec")
                )
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)

    def test_correo_no_autoritativo_ya_existente_da_409_y_no_escribe_nada(self):
        # LA prueba de que la toma de cuenta quedó cerrada.
        usuario = usuario_local(email="juan@hotmail.com", saldo=5)
        sesion = self.sesion([None, [usuario]])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="juan@hotmail.com"))},
        )

        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("vincula Google desde tu perfil", respuesta.json()["detail"])
        self.assertIsNone(usuario.id_google)
        self.assertFalse(usuario.email_verificado)
        self.assertEqual(usuario.saldo_tokens, 5)
        self.assertEqual(sesion.agregados, [])
        self.assertEqual(sesion.commits, 0)

    def test_correo_no_autoritativo_que_no_existe_da_alta_normal(self):
        # La autoritatividad NO bloquea altas: sin cuenta previa no hay nada que tomar.
        sesion = self.sesion([None, []])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="nadie@hotmail.com"))},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(sesion.agregados), 1)
        self.assertEqual(sesion.agregados[0].email, "nadie@hotmail.com")

    def test_cuenta_con_otro_id_google_da_409(self):
        usuario = usuario_local(email="ana@gmail.com", id_google="otro-sub-de-google")
        sesion = self.sesion([None, [usuario]])
        respuesta = self.cliente.post(
            "/auth/google", json={"id_token": firmar(claims_google(email="ana@gmail.com"))}
        )
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(usuario.id_google, "otro-sub-de-google")
        self.assertEqual(sesion.commits, 0)

    def test_dos_cuentas_que_solo_difieren_en_mayusculas_dan_409(self):
        # Conflicto real que un humano debe resolver: elegir una fila a dedo sería
        # entregarle a alguien la cuenta de otro.
        duplicadas = [usuario_local(email="Ana@gmail.com", id_=1),
                      usuario_local(email="ana@gmail.com", id_=2)]
        sesion = self.sesion([None, duplicadas])
        respuesta = self.cliente.post(
            "/auth/google", json={"id_token": firmar(claims_google(email="ana@gmail.com"))}
        )
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(sesion.commits, 0)
        self.assertEqual(sesion.agregados, [])

    def test_un_campo_extra_en_el_body_no_se_exige_ni_se_usa(self):
        # `GoogleLoginEntrada` es solo `id_token`: no hay `nonce` ni acoplamiento con el
        # frontend (un `nonce` de cliente viaja dentro del mismo token que protegería).
        self.sesion([None, []])
        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google()), "nonce": "lo-que-sea"},
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_body_sin_id_token_da_422_de_pydantic(self):
        self.sesion()
        self.assertEqual(self.cliente.post("/auth/google", json={}).status_code, 422)


# ════════════════════════════════════════════════════════════════════════════════════
# 5. /auth/google/vincular
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaVincularGoogle(BaseGoogle):

    def _autenticar(self, usuario):
        main.app.dependency_overrides[usuario_actual] = lambda: usuario

    def test_vincula_identidad_no_autoritativa_con_sesion_propia(self):
        # Autenticarse ES la prueba de posesión que el claim `email_verified` no da, así
        # que acá la autoritatividad deja de importar.
        usuario = usuario_local(email="juan@hotmail.com", saldo=5)
        self._autenticar(usuario)
        sesion = self.sesion([None])

        respuesta = self.cliente.post(
            "/auth/google/vincular",
            json={"id_token": firmar(claims_google(email="juan@hotmail.com"))},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)
        # `email_verificado` NO se toca: sigue describiendo el correo DE LA CUENTA, que
        # Google no verificó. Tampoco cambia el origen ni se acreditan tokens.
        self.assertFalse(usuario.email_verificado)
        self.assertEqual(usuario.proveedor_autenticacion, "local")
        self.assertEqual(usuario.saldo_tokens, 5)
        self.assertEqual(list(usuario.transacciones_tokens), [])
        self.assertEqual(sesion.agregados, [])

    def test_el_email_del_token_no_tiene_que_coincidir(self):
        usuario = usuario_local(email="juan@hotmail.com")
        self._autenticar(usuario)
        self.sesion([None])
        respuesta = self.cliente.post(
            "/auth/google/vincular",
            json={"id_token": firmar(claims_google(email="otro.correo@gmail.com"))},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)

    def test_sin_jwt_propio_da_401(self):
        self.sesion()
        respuesta = self.cliente.post(
            "/auth/google/vincular", json={"id_token": firmar(claims_google())}
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_cuenta_que_ya_tiene_otro_id_google_da_409(self):
        usuario = usuario_local(id_google="sub-anterior")
        self._autenticar(usuario)
        sesion = self.sesion([None])
        respuesta = self.cliente.post(
            "/auth/google/vincular", json={"id_token": firmar(claims_google())}
        )
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(usuario.id_google, "sub-anterior")
        self.assertEqual(sesion.commits, 0)

    def test_sub_ya_vinculado_a_otra_cuenta_da_409_y_no_500(self):
        # El índice único lo garantizaría, pero a costa de un IntegrityError → 500.
        usuario = usuario_local(id_=7)
        ajena = usuario_local(email="otra@gmail.com", id_=8, id_google=SUB_GOOGLE)
        self._autenticar(usuario)
        sesion = self.sesion([ajena])
        respuesta = self.cliente.post(
            "/auth/google/vincular", json={"id_token": firmar(claims_google())}
        )
        self.assertEqual(respuesta.status_code, 409)
        self.assertIsNone(usuario.id_google)
        self.assertEqual(sesion.commits, 0)

    def test_revincular_el_mismo_sub_es_idempotente(self):
        usuario = usuario_local(id_=7, id_google=SUB_GOOGLE)
        self._autenticar(usuario)
        self.sesion([usuario])
        respuesta = self.cliente.post(
            "/auth/google/vincular", json={"id_token": firmar(claims_google())}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(usuario.id_google, SUB_GOOGLE)

    def test_token_de_google_invalido_da_401(self):
        usuario = usuario_local()
        self._autenticar(usuario)
        self.sesion()
        respuesta = self.cliente.post(
            "/auth/google/vincular",
            json={"id_token": firmar(claims_google(aud=OTRO_CLIENT_ID, azp=AUSENTE))},
        )
        self.assertEqual(respuesta.status_code, 401)
        self.assertIsNone(usuario.id_google)


# ════════════════════════════════════════════════════════════════════════════════════
# 6. Consecuencia en /auth/login (§6): password_hash NULL
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaLoginSinPassword(unittest.TestCase):
    """Una cuenta creada por Google no tiene contraseña. Sin la guarda, `passlib`
    recibiría None y reventaría con TypeError → 500 por una condición de negocio
    perfectamente esperable."""

    def setUp(self):
        self.cliente = TestClient(main.app)
        self.addCleanup(main.app.dependency_overrides.clear)

    def _login(self, usuario):
        sesion = SesionFalsa([usuario])
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        return self.cliente.post(
            "/auth/login",
            data={"username": "ana@gmail.com", "password": "loquesea1234"},
        )

    def test_usuario_de_google_no_puede_entrar_por_contrasena(self):
        usuario = Usuario(
            id=3,
            email="ana@gmail.com",
            password_hash=None,
            proveedor_autenticacion="google",
            id_google=SUB_GOOGLE,
            email_verificado=True,
            saldo_tokens=5,
        )
        respuesta = self._login(usuario)
        self.assertEqual(respuesta.status_code, 401)
        # El MISMO mensaje que una contraseña equivocada: decir "esa cuenta usa Google"
        # revelaría qué correos están registrados y con qué proveedor.
        self.assertEqual(respuesta.json()["detail"], "Email o password incorrectos")

    def test_usuario_inexistente_da_el_mismo_mensaje(self):
        respuesta = self._login(None)
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.json()["detail"], "Email o password incorrectos")


# ════════════════════════════════════════════════════════════════════════════════════
# 7. Barrido: ningún caso de negocio termina en 500
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaSinQuinientos(BaseGoogle):
    """`TestClient` propaga las excepciones del servidor, así que un 500 real reventaría
    la prueba. Igual se afirma sobre el código: §10.2 no admite un 500 de negocio."""

    def test_ningun_camino_devuelve_500(self):
        casos = {
            "firma ajena": (firmar(claims_google(), pem=PEM_AJENA), [None, []]),
            "aud ajeno": (firmar(claims_google(aud=OTRO_CLIENT_ID, azp=AUSENTE)), []),
            "sin aud": (firmar(claims_google(aud=AUSENTE)), []),
            "aud múltiple": (firmar(claims_google(aud=[CLIENT_ID, OTRO_CLIENT_ID])), []),
            "azp ajeno": (firmar(claims_google(azp=OTRO_CLIENT_ID)), []),
            "sin exp": (firmar(claims_google(exp=AUSENTE)), []),
            "sin kid": (firmar_sin_kid(claims_google()), []),
            "kid ajeno": (firmar(claims_google(), kid=KID_AJENA, pem=PEM_AJENA), []),
            "alg none": (token_alg_none(claims_google()), []),
            "sin verificar": (firmar(claims_google(email_verified=False)), []),
            "sin email": (firmar(claims_google(email=AUSENTE)), []),
            "basura": ("no-es-un-jwt", []),
            "vacío": ("", []),
        }
        for nombre, (token, resultados) in casos.items():
            with self.subTest(caso=nombre):
                reiniciar_jwks()
                respuesta = self.entrar(token, resultados=resultados)
                self.assertLess(respuesta.status_code, 500, respuesta.text)
                self.assertIn(
                    respuesta.status_code, (200, 401, 409, 422, 503), respuesta.text
                )


# ════════════════════════════════════════════════════════════════════════════════════
# 8. La guarda del downgrade de la 0025
# ════════════════════════════════════════════════════════════════════════════════════

class PruebaGuardaDowngrade(unittest.TestCase):
    """Volver `password_hash` a NOT NULL con usuarios de Google vivos falla con un error
    de Postgres ilegible, y la "solución" tentadora —rellenar con un hash placeholder—
    es justo lo que la migración prohíbe. El downgrade tiene que detenerse y decirlo.

    Acá se prueba **la decisión**, no el DDL: la migración no se aplica a ninguna base.
    """

    @staticmethod
    def _cargar_migracion():
        import importlib.util
        from pathlib import Path

        ruta = (
            Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "0025_login_google.py"
        )
        spec = importlib.util.spec_from_file_location("migracion_0025", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def _correr_downgrade(self, filas_sin_password, offline=False):
        modulo = self._cargar_migracion()
        bind = Mock()
        bind.execute.return_value = Mock(
            scalar_one=Mock(return_value=filas_sin_password)
        )
        with patch.object(modulo, "context", Mock(is_offline_mode=lambda: offline)), \
                patch.object(
                    modulo, "op", Mock(get_bind=Mock(return_value=bind))
                ) as op_falso:
            modulo.downgrade()
        return op_falso

    def test_aborta_con_mensaje_legible_si_hay_cuentas_de_google(self):
        with self.assertRaises(RuntimeError) as capturado:
            self._correr_downgrade(filas_sin_password=3)
        mensaje = str(capturado.exception)
        self.assertIn("0025", mensaje)
        self.assertIn("3", mensaje)
        self.assertIn("password_hash", mensaje)
        self.assertIn("placeholder", mensaje)

    def test_corre_limpio_si_no_hay_cuentas_de_google(self):
        op_falso = self._correr_downgrade(filas_sin_password=0)
        op_falso.drop_index.assert_called_once()
        op_falso.alter_column.assert_called_once()

    def test_en_modo_sql_no_consulta_la_base(self):
        # En `--sql` no hay conexión: alembic solo emite el DDL y la comprobación la hace
        # quien lo aplique. Sin esta guarda, el downgrade offline reventaría.
        op_falso = self._correr_downgrade(filas_sin_password=99, offline=True)
        op_falso.get_bind.assert_not_called()
        op_falso.alter_column.assert_called_once()


if __name__ == "__main__":
    unittest.main()
