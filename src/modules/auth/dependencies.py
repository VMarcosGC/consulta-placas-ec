"""Dependencias FastAPI para autenticar y autorizar acceso a recursos del usuario."""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.models import Usuario
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.auth.security import decodificar_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
# Variante que NO exige token (auto_error=False): para endpoints públicos que dan más
# datos si hay sesión (ej. el perfil con microdesbloqueos del usuario).
oauth2_opcional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _emails_admin() -> set[str]:
    """Lista blanca de administradores, por env var (config sensible, §12).

    `ADMIN_EMAILS` es una lista separada por comas. No hay rol en la BD: para el MVP
    el admin se define por configuración, sin migrar el modelo Usuario.
    """
    crudo = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in crudo.split(",") if e.strip()}


def es_email_admin(email: str) -> bool:
    """True si el email está en `ADMIN_EMAILS`. Lo usa /auth/me para que el frontend
    sepa si mostrar las pantallas de moderación."""
    return email.lower() in _emails_admin()


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


def usuario_actual_opcional(
    token: str | None = Depends(oauth2_opcional),
    sesion: Session = Depends(obtener_sesion),
) -> Usuario | None:
    """Devuelve el Usuario si hay un Bearer token válido, o None si no hay/está mal.

    No lanza 401: el endpoint es público y solo enriquece la respuesta cuando hay sesión.
    """
    if not token:
        return None
    try:
        email = decodificar_token(token)
    except ValueError:
        return None
    return sesion.execute(
        select(Usuario).where(Usuario.email == email)
    ).scalar_one_or_none()


def admin_actual(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """Exige que el usuario autenticado esté en `ADMIN_EMAILS`. 403 si no lo está.

    Se usa para moderar contenido (aprobar/rechazar referencias del marketplace).
    """
    if usuario.email.lower() not in _emails_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requiere privilegios de administrador",
        )
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
