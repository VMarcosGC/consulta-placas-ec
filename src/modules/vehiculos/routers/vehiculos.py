"""CRUD de vehículos del usuario autenticado.

Reglas de autorización:
- Cada operación requiere `usuario_actual`.
- Solo se accede a vehículos donde `vehiculo.usuario_id == usuario.id`.
- Vehículos eliminados (`eliminado_en IS NOT NULL`) NO aparecen en lista ni detalle.
- DELETE es soft delete (marca `eliminado_en`).

La placa es única por usuario (no globalmente — distintos usuarios pueden tener
el mismo vehículo en su árbol histórico).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.models import Usuario
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.schemas.vehiculo import (
    VehiculoCrear,
    VehiculoActualizar,
    VehiculoSalidaCompleta,
)
from src.modules.auth.dependencies import usuario_actual, vehiculo_propio


router = APIRouter(prefix="/vehiculos", tags=["vehiculos"])


@router.post(
    "", response_model=VehiculoSalidaCompleta, status_code=status.HTTP_201_CREATED
)
def crear_vehiculo(
    datos: VehiculoCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    vehiculo = Vehiculo(usuario_id=usuario.id, **datos.model_dump())
    sesion.add(vehiculo)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya tenés un vehículo con la placa {datos.placa}",
        )
    sesion.refresh(vehiculo)
    return vehiculo


@router.get("", response_model=list[VehiculoSalidaCompleta])
def listar_vehiculos(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    vehiculos = (
        sesion.execute(
            select(Vehiculo)
            .where(
                Vehiculo.usuario_id == usuario.id,
                Vehiculo.eliminado_en.is_(None),
            )
            .order_by(Vehiculo.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return vehiculos


@router.get("/{vehiculo_id}", response_model=VehiculoSalidaCompleta)
def obtener_vehiculo(vehiculo: Vehiculo = Depends(vehiculo_propio)):
    return vehiculo


@router.patch("/{vehiculo_id}", response_model=VehiculoSalidaCompleta)
def actualizar_vehiculo(
    datos: VehiculoActualizar,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(vehiculo, campo, valor)

    sesion.commit()
    sesion.refresh(vehiculo)
    return vehiculo


@router.delete("/{vehiculo_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_vehiculo(
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Soft delete: marca `eliminado_en` con timestamp actual."""
    vehiculo.eliminado_en = datetime.now(timezone.utc)
    sesion.commit()
    return None
