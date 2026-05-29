"""Marketplace público de vehículos en venta (Fase 4).

Endpoint anónimo: lista los autos marcados en venta. Solo toca la BD propia
(nunca invoca scraping). Nunca expone el VIN completo ni el nombre del dueño;
ver `VehiculoSalidaMarketplace` y regla de negocio 10.6.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.schemas.vehiculo import VehiculoSalidaMarketplace


router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("", response_model=list[VehiculoSalidaMarketplace])
def listar_marketplace(sesion: Session = Depends(obtener_sesion)):
    """Autos en venta: `en_venta = True` y `precio_venta_usd > 0`, no eliminados.

    Usa `selectinload` sobre `mantenimientos` para evitar N+1 al derivar el
    conteo que se publica como indicador de cuán documentado está el auto.
    """
    vehiculos = (
        sesion.execute(
            select(Vehiculo)
            .where(
                and_(
                    Vehiculo.en_venta.is_(True),
                    Vehiculo.precio_venta_usd > 0,
                    Vehiculo.eliminado_en.is_(None),
                )
            )
            .options(selectinload(Vehiculo.mantenimientos))
            .order_by(Vehiculo.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return [VehiculoSalidaMarketplace.desde_modelo(v) for v in vehiculos]
