"""Endpoints de control de gastos de un vehículo (garage).

Reglas:
- Solo el dueño del vehículo (vía JWT, `vehiculo_propio`) registra/ve/borra.
- Un gasto se puede borrar y volver a cargar (registro contable simple, no inmutable
  como los mantenimientos).
- El `GET` devuelve el listado + un `resumen` derivado (total, promedio mensual,
  desglose por tipo) en una sola llamada, para que el garage no haga dos.
- Solo BD propia (§10.2). Gratis (§1.0.3).
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import vehiculo_propio
from src.modules.vehiculos.models.gasto import GastoVehiculo
from src.modules.vehiculos.models.mantenimiento import Mantenimiento
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.schemas.gasto import (
    GastoCrear,
    GastoPorTipo,
    GastoSalida,
    GastosVehiculoSalida,
    ResumenGastos,
)

router = APIRouter(prefix="/vehiculos/{vehiculo_id}/gastos", tags=["gastos"])


def _meses_entre(desde: date, hasta: date) -> int:
    """Cantidad de meses calendario que toca el rango [desde, hasta], inclusive."""
    return (hasta.year - desde.year) * 12 + (hasta.month - desde.month) + 1


def _resumen(sesion: Session, vehiculo_id: int, filas: list[GastoVehiculo]) -> ResumenGastos:
    if not filas:
        mant = sesion.execute(
            select(func.coalesce(func.sum(Mantenimiento.costo), 0)).where(
                Mantenimiento.vehiculo_id == vehiculo_id
            )
        ).scalar_one()
        return ResumenGastos(mantenimientos_costo_usd=Decimal(mant))

    total = sum((f.monto_usd for f in filas), Decimal("0"))

    por_tipo: dict[str, list[Decimal | int]] = {}
    for f in filas:
        acc = por_tipo.setdefault(f.tipo, [Decimal("0"), 0])
        acc[0] += f.monto_usd
        acc[1] += 1
    desglose = sorted(
        (
            GastoPorTipo(tipo=t, total_usd=v[0], cantidad=v[1])  # type: ignore[arg-type]
            for t, v in por_tipo.items()
        ),
        key=lambda g: g.total_usd,
        reverse=True,
    )

    fechas = [f.fecha for f in filas]
    meses = _meses_entre(min(fechas), max(fechas))
    promedio = (total / meses) if meses else Decimal("0")

    mant = sesion.execute(
        select(func.coalesce(func.sum(Mantenimiento.costo), 0)).where(
            Mantenimiento.vehiculo_id == vehiculo_id
        )
    ).scalar_one()

    return ResumenGastos(
        total_usd=total,
        cantidad=len(filas),
        por_tipo=desglose,
        promedio_mensual_usd=promedio.quantize(Decimal("0.01")),
        meses_con_datos=meses,
        ultimo_registro=max(fechas),
        mantenimientos_costo_usd=Decimal(mant),
    )


@router.post("", response_model=GastoSalida, status_code=status.HTTP_201_CREATED)
def registrar_gasto(
    datos: GastoCrear,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    gasto = GastoVehiculo(
        vehiculo_id=vehiculo.id,
        tipo=datos.tipo,
        monto_usd=datos.monto_usd,
        fecha=datos.fecha,
        kilometraje=datos.kilometraje,
        nota=(datos.nota or None),
    )
    sesion.add(gasto)
    sesion.commit()
    sesion.refresh(gasto)
    return gasto


@router.get("", response_model=GastosVehiculoSalida)
def listar_gastos(
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Listado (más reciente primero) + resumen derivado en una sola respuesta."""
    filas = (
        sesion.execute(
            select(GastoVehiculo)
            .where(GastoVehiculo.vehiculo_id == vehiculo.id)
            .order_by(GastoVehiculo.fecha.desc(), GastoVehiculo.id.desc())
        )
        .scalars()
        .all()
    )
    return GastosVehiculoSalida(
        resumen=_resumen(sesion, vehiculo.id, list(filas)),
        items=[GastoSalida.model_validate(f) for f in filas],
    )


@router.delete("/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_gasto(
    gasto_id: int,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    gasto = sesion.execute(
        select(GastoVehiculo).where(
            and_(
                GastoVehiculo.id == gasto_id,
                GastoVehiculo.vehiculo_id == vehiculo.id,
            )
        )
    ).scalar_one_or_none()
    if gasto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gasto no encontrado para este vehículo",
        )
    sesion.delete(gasto)
    sesion.commit()
    return None
