"""Schemas Pydantic para lecturas de kilometraje.

Las lecturas son INMUTABLES — no hay schema de actualización. Si una lectura
es incorrecta, el usuario la elimina (DELETE) y registra otra.

La validación monotónica (no permitir lecturas menores a la última) vive en
el router, no acá, porque requiere consultar la BD.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class KilometrajeLecturaCrear(BaseModel):
    kilometros: int = Field(ge=0, le=9_999_999)
    fecha_lectura: datetime
    nota: str | None = Field(default=None, max_length=500)


class KilometrajeLecturaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehiculo_id: int
    kilometros: int
    fecha_lectura: datetime
    nota: str | None
    creado_en: datetime
