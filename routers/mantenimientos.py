"""Endpoints de mantenimientos de un vehículo.

Reglas:
- Registros inmutables: solo POST/GET/DELETE, no PATCH (un cambio de fecha/km
  podría violar la monotonía). Para corregir, eliminar y volver a registrar.
- `fecha` y `kilometraje_relacionado` deben ser >= al máximo ya registrado para
  el vehículo (no se viaja en el tiempo ni se retrocede el odómetro).
- Solo el dueño del vehículo (vía JWT) puede registrar/ver/borrar.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from database import obtener_sesion
from models import Vehiculo, Mantenimiento
from schemas.mantenimiento import MantenimientoCrear, MantenimientoSalida
from auth.dependencies import vehiculo_propio


router = APIRouter(
    prefix="/vehiculos/{vehiculo_id}/mantenimientos",
    tags=["mantenimientos"],
)


@router.post(
    "", response_model=MantenimientoSalida, status_code=status.HTTP_201_CREATED
)
def registrar_mantenimiento(
    datos: MantenimientoCrear,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    # Validación monotónica: ni la fecha ni el kilometraje pueden ser menores
    # a los máximos ya registrados para este vehículo.
    maximos = sesion.execute(
        select(
            func.max(Mantenimiento.fecha),
            func.max(Mantenimiento.kilometraje_relacionado),
        ).where(Mantenimiento.vehiculo_id == vehiculo.id)
    ).one()
    fecha_maxima, km_maximo = maximos

    if fecha_maxima is not None and datos.fecha < fecha_maxima:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"La fecha ({datos.fecha}) es anterior al último mantenimiento "
                f"registrado ({fecha_maxima})."
            ),
        )
    if km_maximo is not None and datos.kilometraje_relacionado < km_maximo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El kilometraje ({datos.kilometraje_relacionado}) es menor al "
                f"máximo registrado ({km_maximo})."
            ),
        )

    mantenimiento = Mantenimiento(
        vehiculo_id=vehiculo.id,
        tipo=datos.tipo,
        fecha=datos.fecha,
        kilometraje_relacionado=datos.kilometraje_relacionado,
        taller=datos.taller,
        costo=datos.costo,
    )
    sesion.add(mantenimiento)
    sesion.commit()
    sesion.refresh(mantenimiento)
    return mantenimiento


@router.get("", response_model=list[MantenimientoSalida])
def listar_mantenimientos(
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Devuelve los mantenimientos del más reciente al más antiguo."""
    mantenimientos = (
        sesion.execute(
            select(Mantenimiento)
            .where(Mantenimiento.vehiculo_id == vehiculo.id)
            .order_by(Mantenimiento.fecha.desc(), Mantenimiento.id.desc())
        )
        .scalars()
        .all()
    )
    return mantenimientos


@router.delete("/{mantenimiento_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_mantenimiento(
    mantenimiento_id: int,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    mantenimiento = sesion.execute(
        select(Mantenimiento).where(
            and_(
                Mantenimiento.id == mantenimiento_id,
                Mantenimiento.vehiculo_id == vehiculo.id,
            )
        )
    ).scalar_one_or_none()

    if mantenimiento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mantenimiento no encontrado para este vehículo",
        )

    sesion.delete(mantenimiento)
    sesion.commit()
    return None
