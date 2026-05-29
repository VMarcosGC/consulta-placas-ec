"""Schemas Pydantic para mantenimientos del vehículo.

Registros inmutables (sin schema de actualización). La validación monotónica de
`fecha` y `kilometraje_relacionado` vive en el router porque requiere la BD.
"""

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class MantenimientoCrear(BaseModel):
    tipo: str = Field(min_length=1, max_length=100)
    fecha: date
    kilometraje_relacionado: int = Field(ge=0, le=9_999_999)
    taller: str | None = Field(default=None, max_length=255)
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class MantenimientoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehiculo_id: int
    tipo: str
    fecha: date
    kilometraje_relacionado: int
    taller: str | None
    costo: Decimal | None
    creado_en: datetime
