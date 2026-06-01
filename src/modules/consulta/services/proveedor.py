"""Puente entre la capa de proveedores y la caché (`consultas`).

Reglas (Fase 2.5/3, modelo_tokens_microdesbloqueos.md §9 + reglas_monetizacion_tokens.md §6):
- La consulta GRATUITA nunca llama al proveedor. `capacidades_proveedor()` y
  `leer_proveedor_cacheado()` no invocan al proveedor (solo leen estado/caché).
- El proveedor se invoca SOLO al desbloquear un producto pagado, vía `asegurar_datos_proveedor`,
  que cachea la respuesta. Si el dato ya está en caché vigente, NO se vuelve a llamar.
- El resultado se guarda en `consultas` bajo la fuente `PROVEEDOR` (reusa el TTL/limpieza
  existentes), con el contrato `ResultadoVehicular.to_dict()` como `respuesta`.

Tolerancia a fallos: un fallo de caché o del proveedor no rompe el flujo; se degrada a "sin
datos" y el endpoint no cobra (cobrar solo lo entregado).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from src.modules.consulta.providers import obtener_proveedor
from src.modules.consulta.providers.base import ESTADO_OK, ResultadoVehicular
from src.modules.consulta.services.cache import (
    obtener_consulta_reciente,
    guardar_consulta,
)

logger = logging.getLogger(__name__)

# Clave de fuente bajo la que se cachea el resultado del proveedor en `consultas`.
FUENTE_PROVEEDOR = "PROVEEDOR"


def capacidades_proveedor() -> set[str]:
    """Códigos de producto que el proveedor activo puede entregar (SIN llamarlo).

    Sirve para marcar `disponible` en el preview gratis sin invocar al proveedor.
    """
    try:
        return set(obtener_proveedor().capacidades)
    except Exception as e:  # nunca romper el perfil por la capa de proveedores
        logger.warning("No se pudieron leer capacidades del proveedor: %r", e)
        return set()


def leer_proveedor_cacheado(sesion: Session, placa: str) -> dict | None:
    """Resultado del proveedor cacheado para la placa (None si no hay). NO llama al proveedor."""
    try:
        return obtener_consulta_reciente(sesion, placa, FUENTE_PROVEEDOR)
    except Exception as e:
        logger.warning("Lectura de caché del proveedor falló para %s: %r", placa, e)
        sesion.rollback()
        return None


async def asegurar_datos_proveedor(sesion: Session, placa: str) -> dict | None:
    """Devuelve los datos del proveedor para la placa, llamándolo SOLO si no hay caché.

    Usar al desbloquear un producto pagado que dependa del proveedor. Cachea la respuesta
    cuando es cacheable (`consulta_realizada`/`sin_resultados`). Devuelve el dict del contrato
    o None si el proveedor no entregó datos utilizables (el caller decide no cobrar → 409).
    """
    cacheado = leer_proveedor_cacheado(sesion, placa)
    if cacheado is not None:
        return cacheado

    try:
        resultado: ResultadoVehicular = await obtener_proveedor().consultar(placa)
    except Exception as e:  # un proveedor no debe propagar excepciones (defensa extra)
        logger.warning("Proveedor falló para %s: %r", placa, e)
        return None

    datos = resultado.to_dict()
    try:
        guardar_consulta(sesion, placa, FUENTE_PROVEEDOR, datos)
    except Exception as e:
        logger.warning("Cache write del proveedor falló para %s: %r", placa, e)
        sesion.rollback()

    return datos if resultado.estado == ESTADO_OK else None


def proveedor_y_costo(datos: dict | None) -> tuple[str | None, Decimal | None]:
    """Extrae (proveedor, costo_estimado) de un dict de resultado del proveedor para auditoría."""
    if not datos:
        return None, None
    costo = datos.get("costo_estimado_usd")
    return datos.get("proveedor"), (Decimal(str(costo)) if costo is not None else None)
