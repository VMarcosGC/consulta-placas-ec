"""Endpoints de favoritos del usuario autenticado.

Un favorito es una placa seguida por el usuario. La placa se guarda como String
(no FK), así que puede no existir en nuestra BD. Única por usuario+placa.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.models import Usuario
from src.modules.vehiculos.models.vehiculo_favorito import VehiculoFavorito
from src.modules.vehiculos.schemas.favorito import FavoritoCrear, FavoritoSalida
from src.modules.auth.dependencies import usuario_actual


router = APIRouter(prefix="/favoritos", tags=["favoritos"])


@router.post("", response_model=FavoritoSalida, status_code=status.HTTP_201_CREATED)
def agregar_favorito(
    datos: FavoritoCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    favorito = VehiculoFavorito(
        usuario_id=usuario.id,
        placa=datos.placa,
        nota=datos.nota,
        precio_al_guardar=datos.precio_al_guardar,
    )
    sesion.add(favorito)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La placa {datos.placa} ya está en tus favoritos",
        )
    sesion.refresh(favorito)
    return favorito


@router.get("", response_model=list[FavoritoSalida])
def listar_favoritos(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Devuelve los favoritos del usuario, del más reciente al más antiguo."""
    favoritos = (
        sesion.execute(
            select(VehiculoFavorito)
            .where(VehiculoFavorito.usuario_id == usuario.id)
            .order_by(VehiculoFavorito.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return favoritos


@router.delete("/{favorito_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_favorito(
    favorito_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    favorito = sesion.execute(
        select(VehiculoFavorito).where(
            and_(
                VehiculoFavorito.id == favorito_id,
                VehiculoFavorito.usuario_id == usuario.id,
            )
        )
    ).scalar_one_or_none()

    if favorito is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorito no encontrado",
        )

    sesion.delete(favorito)
    sesion.commit()
    return None
