"""Dependencias FastAPI para autenticar y autorizar acceso a recursos del usuario."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from database import obtener_sesion
from models import Usuario, Vehiculo
from auth.security import decodificar_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def usuario_actual(
    token: str = Depends(oauth2_scheme),
    sesion: Session = Depends(obtener_sesion),
) -> Usuario:
    """Resuelve el Usuario a partir del Bearer token. 401 si falla."""
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        email = decodificar_token(token)
    except ValueError:
        raise credenciales_invalidas

    usuario = sesion.execute(
        select(Usuario).where(Usuario.email == email)
    ).scalar_one_or_none()

    if usuario is None:
        raise credenciales_invalidas

    return usuario


def vehiculo_propio(
    vehiculo_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
) -> Vehiculo:
    """Resuelve un vehículo del usuario autenticado o lanza 404.

    Excluye soft-deleted (`eliminado_en IS NOT NULL`). Útil para todos los
    endpoints anidados bajo `/vehiculos/{vehiculo_id}/...`.
    """
    vehiculo = sesion.execute(
        select(Vehiculo).where(
            and_(
                Vehiculo.id == vehiculo_id,
                Vehiculo.usuario_id == usuario.id,
                Vehiculo.eliminado_en.is_(None),
            )
        )
    ).scalar_one_or_none()

    if vehiculo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no encontrado",
        )
    return vehiculo
