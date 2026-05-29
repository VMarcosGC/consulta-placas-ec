"""Endpoints del histórico de dueños de un vehículo.

Rutas anidadas bajo `/vehiculos/{vehiculo_id}/duenos`. Cada operación requiere
auth y que el vehículo pertenezca al usuario (resuelto por `vehiculo_propio`).

Regla de negocio al POST con `hasta=None`:
- Si ya existe un dueño activo (hasta IS NULL), se cierra automáticamente
  poniéndole `hasta = nuevo.desde`. Esto evita tener dos dueños actuales
  al mismo tiempo y mantiene la línea temporal coherente.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.models.dueno_historico import DuenoHistorico
from src.modules.vehiculos.schemas.dueno_historico import (
    DuenoHistoricoCrear,
    DuenoHistoricoActualizar,
    DuenoHistoricoSalida,
)
from src.modules.auth.dependencies import vehiculo_propio


router = APIRouter(
    prefix="/vehiculos/{vehiculo_id}/duenos",
    tags=["duenos"],
)


def _dueno_del_vehiculo_o_404(
    sesion: Session, vehiculo: Vehiculo, dueno_id: int
) -> DuenoHistorico:
    dueno = sesion.execute(
        select(DuenoHistorico).where(
            and_(
                DuenoHistorico.id == dueno_id,
                DuenoHistorico.vehiculo_id == vehiculo.id,
            )
        )
    ).scalar_one_or_none()

    if dueno is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dueño no encontrado para este vehículo",
        )
    return dueno


@router.post(
    "", response_model=DuenoHistoricoSalida, status_code=status.HTTP_201_CREATED
)
def registrar_dueno(
    datos: DuenoHistoricoCrear,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    # Si el nuevo dueño es el actual (hasta=None), cerrar los activos previos.
    if datos.hasta is None:
        activos_previos = (
            sesion.execute(
                select(DuenoHistorico).where(
                    and_(
                        DuenoHistorico.vehiculo_id == vehiculo.id,
                        DuenoHistorico.hasta.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for previo in activos_previos:
            if previo.desde > datos.desde:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"El dueño actual (id={previo.id}) tiene desde={previo.desde} "
                        f"que es posterior al nuevo desde={datos.desde}. Corregí las fechas."
                    ),
                )
            previo.hasta = datos.desde

    dueno = DuenoHistorico(
        vehiculo_id=vehiculo.id,
        cedula_dueno=datos.cedula_dueno,
        nombre_dueno=datos.nombre_dueno,
        desde=datos.desde,
        hasta=datos.hasta,
    )
    sesion.add(dueno)
    sesion.commit()
    sesion.refresh(dueno)
    return dueno


@router.get("", response_model=list[DuenoHistoricoSalida])
def listar_duenos(
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Devuelve el histórico de dueños del más reciente al más antiguo."""
    duenos = (
        sesion.execute(
            select(DuenoHistorico)
            .where(DuenoHistorico.vehiculo_id == vehiculo.id)
            .order_by(DuenoHistorico.desde.desc())
        )
        .scalars()
        .all()
    )
    return duenos


@router.patch("/{dueno_id}", response_model=DuenoHistoricoSalida)
def corregir_dueno(
    dueno_id: int,
    datos: DuenoHistoricoActualizar,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    dueno = _dueno_del_vehiculo_o_404(sesion, vehiculo, dueno_id)

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(dueno, campo, valor)

    if dueno.hasta is not None and dueno.hasta < dueno.desde:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`hasta` no puede ser anterior a `desde`",
        )

    sesion.commit()
    sesion.refresh(dueno)
    return dueno


@router.delete("/{dueno_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_dueno(
    dueno_id: int,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Borrado físico — son registros históricos del usuario, sin valor para auditoría externa."""
    dueno = _dueno_del_vehiculo_o_404(sesion, vehiculo, dueno_id)
    sesion.delete(dueno)
    sesion.commit()
    return None
