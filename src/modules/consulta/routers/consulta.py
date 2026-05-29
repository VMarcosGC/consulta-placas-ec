"""Endpoints públicos de consulta vehicular (Pilar 1).

Extraídos de `main.py` en la mudanza a monolito modular. La lógica es idéntica:
ANT/SRI vía Playwright con caché; AMT/FGE vía worker híbrido (encolado + en_proceso).
"""
import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion, CACHE_TTL_MINUTOS
from src.core.validators import validar_placa, validar_cedula
from src.modules.consulta.services.ant import consultar_ant
from src.modules.consulta.services.sri import consultar_sri
from src.modules.consulta.services.cache import obtener_consulta_reciente, guardar_consulta
from src.modules.consulta.services.cola import encolar_scraping

logger = logging.getLogger(__name__)

# Fuentes que se sirven vía worker híbrido: AMT y FGE bloquean IPs de datacenter
# (ver docs/arquitectura_hibrida.md). La API no las scrapea; encola y responde
# en_proceso. El worker (IP residencial) las procesa y llena la caché `consultas`.
ESTADO_EN_PROCESO = "en_proceso"

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
        cacheada = obtener_consulta_reciente(sesion, identificador, fuente, CACHE_TTL_MINUTOS)
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
    (AMT/FGE) se scrapean desde una IP residencial vía el worker híbrido. En cache
    miss inserta un trabajo `pendiente` (idempotente) y devuelve `en_proceso` con
    `datos: null`. El cliente reintenta hasta que el worker llena la caché.
    """
    try:
        cacheada = obtener_consulta_reciente(sesion, identificador, fuente, CACHE_TTL_MINUTOS)
        if cacheada is not None:
            return {**cacheada, "_cache": True}
    except Exception as e:
        logger.warning("Cache lookup falló para %s/%s: %r", fuente, identificador, e)
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
    resultado_sri = await consultar_con_cache(sesion, placa_limpia, "SRI", consultar_sri)
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
            "tiene_citaciones_pendientes_ant": pendientes_ant > 0,
            "total_citaciones_ant": total_citaciones_ant,
            "valor_pendiente_sri": total_sri,
            "tiene_valores_pendientes_sri": total_sri > 0,
            "total_infracciones_amt": total_registros_amt,
            "infracciones_pendientes_amt": pendientes_amt,
            "valor_pendiente_amt": total_pendiente_amt,
            "tiene_infracciones_pendientes_amt": pendientes_amt > 0 or total_pendiente_amt > 0,
            "total_denuncias_fge": total_denuncias_fge,
            "tiene_denuncias_fge": total_denuncias_fge > 0,
            "estado_general": "con_pendientes" if hay_pendientes else "sin_pendientes",
        },
    }
