"""Schemas Pydantic para favoritos del usuario.

Un favorito es una placa que el usuario sigue, exista o no en nuestra BD.
La placa se valida y normaliza con `validar_placa` (formato ecuatoriano).
"""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.validators import validar_placa


class FavoritoCrear(BaseModel):
    placa: str = Field(min_length=6, max_length=10)
    nota: str | None = Field(default=None, max_length=255)
    # Precio del anuncio al guardarlo, para avisar después de una baja de precio.
    # Opcional: si la placa no tiene publicación, se guarda sin referencia.
    precio_al_guardar: Decimal | None = Field(default=None, ge=0)

    @field_validator("placa")
    @classmethod
    def _placa_valida(cls, v: str) -> str:
        return validar_placa(v)


class FavoritoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    placa: str
    nota: str | None
    precio_al_guardar: Decimal | None
    creado_en: datetime
