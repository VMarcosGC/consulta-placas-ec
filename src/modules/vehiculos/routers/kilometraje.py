"""Endpoints de lecturas de kilometraje de un vehículo.

Reglas:
- Lecturas inmutables: solo POST/GET/DELETE, no PATCH.
- Una lectura nueva debe ser >= a la máxima lectura existente (los odómetros
  no retroceden). Si hay un caso legítimo de reseteo (cambio de tablero),
  eliminar la lectura errónea y registrar la nueva con `nota` aclaratoria.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.models.kilometraje_lectura import KilometrajeLectura
from src.modules.vehiculos.schemas.kilometraje import KilometrajeLecturaCrear, KilometrajeLecturaSalida
from src.modules.auth.dependencies import vehiculo_propio


router = APIRouter(
    prefix="/vehiculos/{vehiculo_id}/kilometraje",
    tags=["kilometraje"],
)


@router.post(
    "", response_model=KilometrajeLecturaSalida, status_code=status.HTTP_201_CREATED
)
def registrar_lectura(
    datos: KilometrajeLecturaCrear,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    # Validación monotónica: la nueva lectura no puede ser menor a la máxima.
    maximo_existente = sesion.execute(
        select(func.max(KilometrajeLectura.kilometros)).where(
            KilometrajeLectura.vehiculo_id == vehiculo.id
        )
    ).scalar()

    if maximo_existente is not None and datos.kilometros < maximo_existente:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"La lectura ({datos.kilometros}) es menor a la máxima registrada "
                f"({maximo_existente}). Si es un cambio de tablero, eliminá la lectura "
                f"errónea primero y registrá la nueva con una nota."
            ),
        )

    lectura = KilometrajeLectura(
        vehiculo_id=vehiculo.id,
        kilometros=datos.kilometros,
        fecha_lectura=datos.fecha_lectura,
        nota=datos.nota,
    )
    sesion.add(lectura)
    sesion.commit()
    sesion.refresh(lectura)
    return lectura


@router.get("", response_model=list[KilometrajeLecturaSalida])
def listar_lecturas(
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Devuelve las lecturas del más reciente al más antiguo."""
    lecturas = (
        sesion.execute(
            select(KilometrajeLectura)
            .where(KilometrajeLectura.vehiculo_id == vehiculo.id)
            .order_by(KilometrajeLectura.fecha_lectura.desc())
        )
        .scalars()
        .all()
    )
    return lecturas


@router.delete("/{lectura_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_lectura(
    lectura_id: int,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    """Borrado físico de una lectura errónea."""
    lectura = sesion.execute(
        select(KilometrajeLectura).where(
            and_(
                KilometrajeLectura.id == lectura_id,
                KilometrajeLectura.vehiculo_id == vehiculo.id,
            )
        )
    ).scalar_one_or_none()

    if lectura is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lectura no encontrada para este vehículo",
        )

    sesion.delete(lectura)
    sesion.commit()
    return None
