"""Endpoints públicos de consulta vehicular (Pilar 1).

Extraídos de `main.py` en la mudanza a monolito modular. La lógica es idéntica:
ANT/SRI vía Playwright con caché; AMT/FGE vía worker híbrido (encolado + en_proceso).
"""
import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion, SessionLocal
from src.core.validators import validar_placa, validar_cedula
from src.modules.auth.dependencies import usuario_actual_opcional
from src.modules.auth.models import Usuario
from src.modules.consulta.services.desbloqueos import (
    catalogo_activo,
    productos_desbloqueados,
)
from src.modules.consulta.services.ant import consultar_ant
from src.modules.consulta.services.amt import consultar_amt
from src.modules.consulta.services.epmtsd import consultar_epmtsd
from src.modules.consulta.services.fiscalia import consultar_fiscalia
from src.modules.consulta.services.sri import consultar_sri
from src.modules.consulta.services.consultasecuador import consultar_consultasecuador
from src.modules.consulta.services.ecuadorlegalonline import consultar_ecuadorlegalonline
from src.modules.consulta.services.cache import (
    obtener_consulta_reciente,
    guardar_consulta,
    TTL_TRANSACCIONAL_MINUTOS,
)
from src.modules.consulta.services.cola import encolar_scraping, fuente_en_error_reciente
from src.modules.consulta.services.consolidador import consolidar_placa
from src.modules.consulta.schemas import VehiculoConsolidadoResponse

logger = logging.getLogger(__name__)

# Fuentes que se sirven vía worker híbrido: AMT y FGE bloquean IPs de datacenter
# (ver docs/arquitectura_hibrida.md). La API no las scrapea; encola y responde
# en_proceso. El worker (IP residencial) las procesa y llena la caché `consultas`.
ESTADO_EN_PROCESO = "en_proceso"
# Fuente caída: el worker agotó los reintentos. El cliente deja de pollear y puede
# reintentar manualmente. Durante esta ventana la API no re-encola a ciegas.
ESTADO_ERROR_FUENTE = "error_fuente"
VENTANA_ERROR_FUENTE_MINUTOS = TTL_TRANSACCIONAL_MINUTOS

# Fuentes servidas por el worker híbrido (las únicas reintentables). FGE salió: el
# portal SIAF agregó hCaptcha y pasó a `consulta_externa` (ver fiscalia.py).
FUENTES_WORKER = {"AMT", "EPMTSD"}

# (El precio de cada microdesbloqueo vive en services/catalogo_productos.py, no aquí.)

# Modo SÍNCRONO: si el backend corre desde una IP que SÍ alcanza las fuentes (IP
# residencial de Ecuador), scrapea AMT/EPMTSD/FGE en el acto (en paralelo) en vez de
# encolarlas al worker. Así el endpoint devuelve datos reales en una sola llamada, sin
# depender de un worker aparte ni dejar todo en `en_proceso`. Activar con
# SCRAPING_SINCRONO=true (recomendado al desplegar el backend en una máquina residencial EC).
# En la nube datacenter (Render) dejar en false: ahí AMT/EPMTSD/FGE están bloqueadas y van
# por worker/proxy residencial.
SCRAPING_SINCRONO = os.getenv("SCRAPING_SINCRONO", "false").strip().lower() in (
    "1", "true", "yes", "si", "sí",
)

# Fuentes que se scrapean con Playwright en modo síncrono (clave → función de servicio).
# FGE NO está: su portal agregó hCaptcha → es `consulta_externa` (passthrough instantáneo).
_FUENTES_SCRAPING_DIRECTO = {
    "ANT": consultar_ant,
    "AMT": consultar_amt,
    "EPMTSD": consultar_epmtsd,
}


async def _scrapear_con_cache_propia(identificador: str, fuente: str, fn_consultar) -> tuple[str, dict]:
    """Scrapea una fuente con su PROPIA sesión de BD (segura para asyncio.gather).

    Cada coroutine paralela necesita su sesión: las Session de SQLAlchemy no son
    concurrency-safe. La caché (lectura/escritura) se hace sobre esa sesión propia.
    """
    sesion = SessionLocal()
    try:
        return fuente, await consultar_con_cache(sesion, identificador, fuente, fn_consultar)
    finally:
        sesion.close()


def _normalizar_identificador_worker(fuente: str, identificador: str) -> str:
    """Normaliza el identificador según la fuente, lanzando ValueError si es inválido.

    AMT y EPMTSD siempre van por placa. FGE acepta placa **o** cédula porque su `termino`
    depende del flujo de origen: `/consultar/{placa}` lo encola con la placa;
    `/consultar-judicial/{cedula}` con la cédula. El reintento debe aceptar el mismo
    identificador con que se encoló.
    """
    if fuente in ("AMT", "EPMTSD"):
        return validar_placa(identificador)
    # FGE
    try:
        return validar_placa(identificador)
    except ValueError:
        return validar_cedula(identificador)


router = APIRouter(tags=["consulta"])


async def consultar_con_cache(
    sesion: Session,
    identificador: str,
    fuente: str,
    fn_consultar,
) -> dict:
    """Devuelve respuesta cacheada si existe; si no, consulta la fuente y persiste.

    Si la BD falla, se ignora y se consulta la fuente directamente.
    El endpoint nunca debe fallar por problemas de caché.
    """
    try:
        cacheada = obtener_consulta_reciente(sesion, identificador, fuente)
        if cacheada is not None:
            return {**cacheada, "_cache": True}
    except Exception as e:
        logger.warning("Cache lookup falló para %s/%s: %r", fuente, identificador, e)
        sesion.rollback()

    respuesta = await fn_consultar(identificador)

    try:
        guardar_consulta(sesion, identificador, fuente, respuesta)
    except Exception as e:
        logger.warning("Cache write falló para %s/%s: %r", fuente, identificador, e)
        sesion.rollback()

    return respuesta


def consultar_via_worker(
    sesion: Session,
    identificador: str,
    fuente: str,
    campo_id: str = "placa",
) -> dict:
    """Devuelve la respuesta cacheada si existe; si no, encola para el worker.

    A diferencia de `consultar_con_cache`, NUNCA invoca Playwright: estas fuentes
    (AMT/FGE) se scrapean desde una IP residencial vía el worker híbrido. Flujo:

    1. Cache hit en `consultas` → devuelve el resultado.
    2. Si el último trabajo terminó en `error_fuente` dentro de la ventana de
       enfriamiento → devuelve `error_fuente` (NO re-encola; el cliente deja de
       pollear y ofrece "Reintentar", que va al endpoint dedicado).
    3. Cache miss normal → inserta trabajo `pendiente` (idempotente) y devuelve
       `en_proceso` con `datos: null`. El cliente reintenta hasta que llene la caché.
    """
    try:
        cacheada = obtener_consulta_reciente(sesion, identificador, fuente)
        if cacheada is not None:
            return {**cacheada, "_cache": True}
    except Exception as e:
        logger.warning("Cache lookup falló para %s/%s: %r", fuente, identificador, e)
        sesion.rollback()

    try:
        error = fuente_en_error_reciente(
            sesion, identificador, fuente, VENTANA_ERROR_FUENTE_MINUTOS
        )
        if error is not None:
            return {
                "fuente": fuente,
                campo_id: identificador,
                "estado": ESTADO_ERROR_FUENTE,
                "datos": None,
                "error": error or "La fuente oficial no respondió tras varios intentos",
            }
    except Exception as e:
        logger.warning("Lectura de cola falló para %s/%s: %r", fuente, identificador, e)
        sesion.rollback()

    try:
        encolar_scraping(sesion, identificador, fuente)
    except Exception as e:
        logger.warning("Encolado falló para %s/%s: %r", fuente, identificador, e)
        sesion.rollback()

    return {
        "fuente": fuente,
        campo_id: identificador,
        "estado": ESTADO_EN_PROCESO,
        "datos": None,
    }


@router.get("/")
def inicio():
    return {"mensaje": "API de consulta de placas activa"}


@router.get("/health")
def health():
    """Health check para la plataforma de hosting (Render/Fly/etc).
    No toca BD ni dependencias externas: responde instantáneo.
    """
    return {"status": "ok"}


@router.get("/consultar-judicial/{cedula}")
async def consultar_judicial(cedula: str, sesion: Session = Depends(obtener_sesion)):
    try:
        cedula_limpia = validar_cedula(cedula)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # FGE pasó a consulta_externa (el SIAF agregó hCaptcha): passthrough instantáneo
    # con enlace al portal, no scraping. Ver fiscalia.py.
    resultado = await consultar_fiscalia(cedula_limpia)

    datos = resultado.get("datos") or {}
    denuncias = datos.get("denuncias") or {}
    total = denuncias.get("total_encontradas", 0)

    return {
        "cedula": cedula_limpia,
        "fge": resultado,
        "resumen": {
            "fge_consultado": resultado.get("estado") == "consulta_realizada",
            "fge_consulta_externa": resultado.get("estado") == "consulta_externa",
            "url_consulta_fge": resultado.get("url_consulta"),
            "total_denuncias": total,
            "tiene_denuncias": total > 0,
        },
    }


async def _obtener_fuentes_placa(sesion: Session, placa_limpia: str) -> dict:
    """Obtiene las respuestas por-fuente para una placa (keyed por clave de catálogo).

    Compartido por `/consultar/{placa}` (vista por fuente) y `/consultar/{placa}/perfil`
    (vista consolidada). SRI + las no oficiales son passthrough instantáneo
    (`consulta_externa`). ANT/AMT/EPMTSD/FGE se scrapean con Playwright:
    - **Modo síncrono** (`SCRAPING_SINCRONO=true`, IP residencial EC): se scrapean en el
      acto y EN PARALELO → datos reales en una sola llamada, sin worker.
    - **Modo worker** (default, nube datacenter): AMT/EPMTSD/FGE se encolan y devuelven
      `en_proceso`; el worker (IP residencial) las procesa. ANT siempre directo.
    """
    # Instantáneas (no se scrapean): SRI, FGE y las no oficiales → enlace al portal.
    # FGE pasó a consulta_externa (hCaptcha en el SIAF, ver fiscalia.py).
    resultado_sri = await consultar_sri(placa_limpia)
    resultado_fge = await consultar_fiscalia(placa_limpia)
    resultado_consultasec = await consultar_consultasecuador(placa_limpia)
    resultado_eclegal = await consultar_ecuadorlegalonline(placa_limpia)

    if SCRAPING_SINCRONO:
        # ANT/AMT/EPMTSD directo y en paralelo (cada una con su sesión de caché).
        pares = await asyncio.gather(
            *[
                _scrapear_con_cache_propia(placa_limpia, clave, fn)
                for clave, fn in _FUENTES_SCRAPING_DIRECTO.items()
            ]
        )
        directos = dict(pares)
        resultado_ant = directos["ANT"]
        resultado_amt = directos["AMT"]
        resultado_epmtsd = directos["EPMTSD"]
    else:
        # Nube datacenter: ANT directo; AMT/EPMTSD vía worker híbrido (en_proceso).
        resultado_ant = await consultar_con_cache(sesion, placa_limpia, "ANT", consultar_ant)
        resultado_amt = consultar_via_worker(sesion, placa_limpia, "AMT")
        resultado_epmtsd = consultar_via_worker(sesion, placa_limpia, "EPMTSD")

    return {
        "ANT": resultado_ant,
        "SRI": resultado_sri,
        "AMT": resultado_amt,
        "EPMTSD": resultado_epmtsd,
        "FGE": resultado_fge,
        "ConsultasEcuador": resultado_consultasec,
        "EcuadorLegalOnline": resultado_eclegal,
    }


@router.get("/consultar/{placa}/perfil", response_model=VehiculoConsolidadoResponse)
async def consultar_perfil(
    placa: str,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario | None = Depends(usuario_actual_opcional),
):
    """Perfil consolidado del vehículo: agrega las fuentes en secciones temáticas.

    Misma orquestación que `/consultar/{placa}` pero orientada a la entidad. **Gateado por
    microdesbloqueos**: si hay sesión, las secciones que el usuario ya pagó para esta placa
    vienen reveladas; el resto va como teaser (ver modelo_tokens_microdesbloqueos.md). Sin
    sesión, todo va en teaser. El bloque `estado_fuentes` permite pollear mientras AMT carga.
    """
    try:
        placa_limpia = validar_placa(placa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    desbloqueados = (
        productos_desbloqueados(sesion, usuario.id, placa_limpia) if usuario else set()
    )
    catalogo = catalogo_activo(sesion)
    fuentes = await _obtener_fuentes_placa(sesion, placa_limpia)
    return consolidar_placa(placa_limpia, fuentes, desbloqueados, catalogo)


# Los endpoints de microdesbloqueo (GET productos / POST desbloquear / GET desbloqueos)
# viven en src/modules/consulta/routers/desbloqueos.py (router dedicado).


@router.get("/consultar/{placa}")
async def consultar_placa(placa: str, sesion: Session = Depends(obtener_sesion)):
    try:
        placa_limpia = validar_placa(placa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    fuentes = await _obtener_fuentes_placa(sesion, placa_limpia)
    resultado_ant = fuentes["ANT"]
    resultado_sri = fuentes["SRI"]
    resultado_amt = fuentes["AMT"]
    resultado_fge = fuentes["FGE"]

    datos_ant = resultado_ant.get("datos") or {}
    citaciones_ant = datos_ant.get("citaciones") or {}
    pendientes_ant = citaciones_ant.get("pendientes", 0)
    total_citaciones_ant = citaciones_ant.get("total_registros", 0)

    datos_sri = resultado_sri.get("datos") or {}
    valores_sri = datos_sri.get("valores") or {}
    total_sri = valores_sri.get("total_a_pagar", 0)

    datos_amt = resultado_amt.get("datos") or {}
    infracciones_amt = datos_amt.get("infracciones") or {}
    pendientes_amt = infracciones_amt.get("pendientes", 0)
    total_pendiente_amt = infracciones_amt.get("total_a_pagar", 0)
    total_registros_amt = infracciones_amt.get("total_registros", 0)

    datos_fge = resultado_fge.get("datos") or {}
    denuncias_fge = datos_fge.get("denuncias") or {}
    total_denuncias_fge = denuncias_fge.get("total_encontradas", 0)

    hay_pendientes = (
        pendientes_ant > 0
        or total_sri > 0
        or pendientes_amt > 0
        or total_pendiente_amt > 0
        or total_denuncias_fge > 0
    )

    return {
        "placa": placa_limpia,
        "ant": resultado_ant,
        "sri": resultado_sri,
        "amt": resultado_amt,
        "fge": resultado_fge,
        "resumen": {
            "fuentes_consultadas": 4,
            "ant_consultado": resultado_ant.get("estado") == "consulta_realizada",
            "sri_consultado": resultado_sri.get("estado") == "consulta_realizada",
            "amt_consultado": resultado_amt.get("estado") == "consulta_realizada",
            "fge_consultado": resultado_fge.get("estado") == "consulta_realizada",
            "amt_en_proceso": resultado_amt.get("estado") == ESTADO_EN_PROCESO,
            "fge_en_proceso": resultado_fge.get("estado") == ESTADO_EN_PROCESO,
            "amt_error_fuente": resultado_amt.get("estado") == ESTADO_ERROR_FUENTE,
            "fge_error_fuente": resultado_fge.get("estado") == ESTADO_ERROR_FUENTE,
            "tiene_citaciones_pendientes_ant": pendientes_ant > 0,
            "total_citaciones_ant": total_citaciones_ant,
            "valor_pendiente_sri": total_sri,
            "tiene_valores_pendientes_sri": total_sri > 0,
            "sri_consulta_externa": resultado_sri.get("estado") == "consulta_externa",
            "url_consulta_sri": resultado_sri.get("url_consulta"),
            "total_infracciones_amt": total_registros_amt,
            "infracciones_pendientes_amt": pendientes_amt,
            "valor_pendiente_amt": total_pendiente_amt,
            "tiene_infracciones_pendientes_amt": pendientes_amt > 0 or total_pendiente_amt > 0,
            "total_denuncias_fge": total_denuncias_fge,
            "tiene_denuncias_fge": total_denuncias_fge > 0,
            "estado_general": "con_pendientes" if hay_pendientes else "sin_pendientes",
        },
    }


@router.post("/consultar/{identificador}/reintentar/{fuente}")
def reintentar_fuente(
    identificador: str, fuente: str, sesion: Session = Depends(obtener_sesion)
):
    """Fuerza un nuevo intento de scraping de una fuente que quedó en `error_fuente`.

    Lo dispara el botón "Reintentar conexión" del frontend. Re-encola el trabajo
    saltándose la ventana de enfriamiento (un trabajo `error_fuente` no es activo, así
    que el insert idempotente crea una fila `pendiente` nueva). Solo aplica a las
    fuentes servidas por el worker híbrido (AMT/FGE); ANT es directo y SRI passthrough.
    """
    fuente = fuente.upper()
    if fuente not in FUENTES_WORKER:
        raise HTTPException(
            status_code=400,
            detail=f"Fuente no reintentable vía worker: {fuente!r}. Válidas: AMT, FGE.",
        )

    try:
        identificador_limpio = _normalizar_identificador_worker(fuente, identificador)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    campo_id = "termino" if fuente == "FGE" else "placa"

    try:
        encolar_scraping(sesion, identificador_limpio, fuente)
    except Exception as e:
        logger.warning("Re-encolado falló para %s/%s: %r", fuente, identificador_limpio, e)
        sesion.rollback()
        raise HTTPException(status_code=503, detail="No se pudo reencolar el trabajo")

    return {
        "fuente": fuente,
        campo_id: identificador_limpio,
        "estado": ESTADO_EN_PROCESO,
        "datos": None,
    }
