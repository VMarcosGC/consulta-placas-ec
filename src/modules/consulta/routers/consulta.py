"""Endpoints públicos de consulta vehicular (Pilar 1).

Extraídos de `main.py` en la mudanza a monolito modular. La lógica es idéntica:
ANT/SRI vía Playwright con caché; AMT/FGE vía worker híbrido (encolado + en_proceso).
"""
import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.core.validators import validar_placa, validar_cedula
from src.modules.consulta.services.ant import consultar_ant
from src.modules.consulta.services.sri import consultar_sri
from src.modules.consulta.services.cache import (
    obtener_consulta_reciente,
    guardar_consulta,
    TTL_TRANSACCIONAL_MINUTOS,
)
from src.modules.consulta.services.cola import encolar_scraping, fuente_en_error_reciente

logger = logging.getLogger(__name__)

# Fuentes que se sirven vía worker híbrido: AMT y FGE bloquean IPs de datacenter
# (ver docs/arquitectura_hibrida.md). La API no las scrapea; encola y responde
# en_proceso. El worker (IP residencial) las procesa y llena la caché `consultas`.
ESTADO_EN_PROCESO = "en_proceso"
# Fuente caída: el worker agotó los reintentos. El cliente deja de pollear y puede
# reintentar manualmente. Durante esta ventana la API no re-encola a ciegas.
ESTADO_ERROR_FUENTE = "error_fuente"
VENTANA_ERROR_FUENTE_MINUTOS = TTL_TRANSACCIONAL_MINUTOS

# Fuentes válidas para el worker híbrido y su validador de identificador.
VALIDADOR_FUENTE_WORKER = {"AMT": validar_placa, "FGE": validar_cedula}

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

    # FGE vía worker híbrido (encolado + en_proceso), no Playwright directo.
    resultado = consultar_via_worker(sesion, cedula_limpia, "FGE", campo_id="termino")

    datos = resultado.get("datos") or {}
    denuncias = datos.get("denuncias") or {}
    total = denuncias.get("total_encontradas", 0)

    return {
        "cedula": cedula_limpia,
        "fge": resultado,
        "resumen": {
            "fge_consultado": resultado.get("estado") == "consulta_realizada",
            "fge_en_proceso": resultado.get("estado") == ESTADO_EN_PROCESO,
            "fge_error_fuente": resultado.get("estado") == ESTADO_ERROR_FUENTE,
            "total_denuncias": total,
            "tiene_denuncias": total > 0,
        },
    }


@router.get("/consultar/{placa}")
async def consultar_placa(placa: str, sesion: Session = Depends(obtener_sesion)):
    try:
        placa_limpia = validar_placa(placa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resultado_ant = await consultar_con_cache(sesion, placa_limpia, "ANT", consultar_ant)
    # SRI: passthrough instantáneo al portal oficial (no se scrapea por el reCAPTCHA
    # Enterprise v3; devuelve url_consulta para que el usuario consulte ahí).
    resultado_sri = await consultar_sri(placa_limpia)
    # AMT y FGE se sirven vía worker híbrido (encolado + en_proceso), no Playwright.
    resultado_amt = consultar_via_worker(sesion, placa_limpia, "AMT")
    resultado_fge = consultar_via_worker(sesion, placa_limpia, "FGE", campo_id="termino")

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
    validador = VALIDADOR_FUENTE_WORKER.get(fuente)
    if validador is None:
        raise HTTPException(
            status_code=400,
            detail=f"Fuente no reintentable vía worker: {fuente!r}. Válidas: AMT, FGE.",
        )

    try:
        identificador_limpio = validador(identificador)
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
