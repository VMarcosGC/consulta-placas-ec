"""Schemas Pydantic para auth: registro, login y respuestas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UsuarioCrear(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nombre: str | None = Field(default=None, max_length=255)


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    nombre: str | None
    saldo_tokens: int
    # True si el usuario está en ADMIN_EMAILS. El endpoint /auth/me lo setea; en otros
    # contextos (registro) queda en el default. No es una columna de la BD.
    es_admin: bool = False
    creado_en: datetime


class TransaccionTokenSalida(BaseModel):
    """Vista de una transacción de tokens (auditoría). `monto` positivo = crédito,
    negativo = débito."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    monto: int
    motivo: str
    fecha: datetime


class SaldoTokens(BaseModel):
    """Saldo actual de la billetera del usuario."""
    saldo_tokens: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
