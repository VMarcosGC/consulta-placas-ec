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
    creado_en: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
