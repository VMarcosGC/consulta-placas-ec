"""Hashing de password con bcrypt y firma/verificación de JWT."""

from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from jose import JWTError, jwt

from src.core.database import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRA_MINUTOS


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hashear_password(password_plano: str) -> str:
    return pwd_context.hash(password_plano)


def verificar_password(password_plano: str, password_hash: str) -> bool:
    return pwd_context.verify(password_plano, password_hash)


def crear_token_acceso(subject: str, expira_minutos: int | None = None) -> str:
    """Genera un JWT firmado con `sub=<email>` y `exp=<utc + N min>`."""
    expira = datetime.now(timezone.utc) + timedelta(
        minutes=expira_minutos or JWT_EXPIRA_MINUTOS
    )
    payload = {"sub": subject, "exp": expira}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_token(token: str) -> str:
    """Devuelve el `sub` del token o lanza ValueError si es inválido/expirado."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Token inválido: {e}") from e
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token sin sub")
    return sub
