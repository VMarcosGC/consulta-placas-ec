"""Endpoint del plan de cuidado del vehículo (garage).

`GET /vehiculos/{vehiculo_id}/plan-cuidado` — devuelve, por ítem de mantenimiento
recomendado, si está al día / próximo / vencido / sin datos, cruzando reglas genéricas
(`services/plan_cuidado.py`) con lo que el dueño ya registró en `mantenimientos`.

El kilometraje de referencia sale del dato más alto conocido: la última lectura de
kilometraje o el km del último mantenimiento. Se puede forzar con `?km=`.

Solo el dueño (vía `vehiculo_propio`). Solo lectura, sin I/O externo. Gratis.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import vehiculo_propio
from src.modules.vehiculos.models.kilometraje_lectura import KilometrajeLectura
from src.modules.vehiculos.models.mantenimiento import Mantenimiento
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.schemas.plan_cuidado import ItemPlanSalida, PlanCuidadoSalida
from src.modules.vehiculos.services.plan_cuidado import generar_plan

router = APIRouter(prefix="/vehiculos/{vehiculo_id}/plan-cuidado", tags=["gastos"])


@router.get("", response_model=PlanCuidadoSalida)
def plan_cuidado(
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
    km: int | None = Query(default=None, ge=0, le=9_999_999),
):
    registros = [
        (m.tipo, m.fecha, m.kilometraje_relacionado)
        for m in sesion.execute(
            select(Mantenimiento).where(Mantenimiento.vehiculo_id == vehiculo.id)
        ).scalars()
    ]

    if km is None:
        km_lectura = sesion.execute(
            select(func.max(KilometrajeLectura.kilometros)).where(
                KilometrajeLectura.vehiculo_id == vehiculo.id
            )
        ).scalar_one_or_none()
        km_mant = max((r[2] for r in registros if r[2] is not None), default=None)
        candidatos = [v for v in (km_lectura, km_mant) if v is not None]
        km = max(candidatos) if candidatos else None

    plan = generar_plan(km_referencia=km, registros=registros)
    return PlanCuidadoSalida(
        fuente=plan.fuente,
        km_referencia=plan.km_referencia,
        vencidos=plan.vencidos,
        proximos=plan.proximos,
        nota_ia=plan.nota_ia,
        items=[ItemPlanSalida(**vars(i)) for i in plan.items],
    )
