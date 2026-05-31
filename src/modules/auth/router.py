"""Endpoints de autenticación: registro, login y perfil del usuario actual."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.models import Usuario, TransaccionToken
from src.modules.auth.models import SALDO_INICIAL_TOKENS
from src.modules.auth.schemas import UsuarioCrear, UsuarioSalida, Token
from src.modules.auth.security import hashear_password, verificar_password, crear_token_acceso
from src.modules.auth.dependencies import usuario_actual, es_email_admin


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registro", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    datos: UsuarioCrear,
    sesion: Session = Depends(obtener_sesion),
):
    existente = sesion.execute(
        select(Usuario).where(Usuario.email == datos.email)
    ).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese email",
        )

    usuario = Usuario(
        email=datos.email,
        password_hash=hashear_password(datos.password),
        nombre=datos.nombre,
    )
    # Audita el saldo de cortesía inicial para que el ledger cuadre con el saldo.
    usuario.transacciones_tokens.append(
        TransaccionToken(monto=SALDO_INICIAL_TOKENS, motivo="saldo_inicial")
    )
    sesion.add(usuario)
    sesion.commit()
    sesion.refresh(usuario)
    return usuario


@router.post("/login", response_model=Token)
def iniciar_sesion(
    form: OAuth2PasswordRequestForm = Depends(),
    sesion: Session = Depends(obtener_sesion),
):
    """OAuth2PasswordRequestForm espera campos `username` y `password` (form-data).
    El `username` es el email del usuario.
    """
    usuario = sesion.execute(
        select(Usuario).where(Usuario.email == form.username)
    ).scalar_one_or_none()

    if usuario is None or not verificar_password(form.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o password incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = crear_token_acceso(subject=usuario.email)
    return Token(access_token=token)


@router.get("/me", response_model=UsuarioSalida)
def perfil(usuario: Usuario = Depends(usuario_actual)):
    # Atributo transitorio (no columna): le dice al frontend si mostrar moderación.
    usuario.es_admin = es_email_admin(usuario.email)
    return usuario
