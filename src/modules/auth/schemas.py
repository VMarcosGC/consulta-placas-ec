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


class GoogleLoginEntrada(BaseModel):
    """El `credential` que entrega Google Identity Services en el navegador.

    Es **solo** `id_token` y nada más. No hay `nonce` ni ningún otro campo: un `nonce`
    generado en el cliente no protegería de nada (un JWT va firmado, no cifrado — el
    `nonce` viaja en el payload del mismo token que se quiere proteger) y acoplaría el
    frontend a este contrato para nada. El antirreplay real espera a que haya Redis.
    """

    id_token: str
