"""Schemas Pydantic del histórico de dueños de un vehículo.

Convención del campo `hasta`:
  - `hasta = None`  → dueño actual.
  - `hasta = fecha` → ex-dueño que vendió ese día.

Al crear un nuevo dueño con `hasta=None`, el router cierra el dueño actual
previo (si existe) seteándole `hasta` al `desde` del nuevo. Ver routers/duenos.py.
"""

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from utils.validators import validar_cedula


class DuenoHistoricoCrear(BaseModel):
    cedula_dueno: str
    nombre_dueno: str | None = Field(default=None, max_length=255)
    desde: date
    hasta: date | None = Field(
        default=None,
        description="Si es None, el dueño se considera actual y cierra el anterior.",
    )

    @field_validator("cedula_dueno")
    @classmethod
    def _cedula_valida(cls, v: str) -> str:
        return validar_cedula(v)

    @model_validator(mode="after")
    def _rango_coherente(self):
        if self.hasta is not None and self.hasta < self.desde:
            raise ValueError("`hasta` no puede ser anterior a `desde`")
        return self


class DuenoHistoricoActualizar(BaseModel):
    """Corrección de un registro existente. La cédula no se cambia (es la
    identidad del registro); si está mal, eliminar y crear de nuevo.
    """
    nombre_dueno: str | None = Field(default=None, max_length=255)
    desde: date | None = None
    hasta: date | None = None


class DuenoHistoricoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehiculo_id: int
    cedula_dueno: str
    nombre_dueno: str | None
    desde: date
    hasta: date | None
    creado_en: datetime
