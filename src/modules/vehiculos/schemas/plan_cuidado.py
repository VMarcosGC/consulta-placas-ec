"""Schemas de salida del plan de cuidado del vehículo.

Espejan las dataclasses de `services/plan_cuidado.py`. `fuente` distingue el origen
("reglas" hoy; "ia" cuando exista el plan generado con IA) sin cambiar la forma.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

EstadoItemPlan = Literal["al_dia", "proximo", "vencido", "sin_datos"]


class ItemPlanSalida(BaseModel):
    clave: str
    titulo: str
    estado: EstadoItemPlan
    detalle: str
    cada_km: int | None = None
    cada_meses: int | None = None
    ultimo_km: int | None = None
    ultima_fecha: date | None = None
    proximo_km: int | None = None


class PlanCuidadoSalida(BaseModel):
    fuente: Literal["reglas", "ia"] = "reglas"
    km_referencia: int | None = None
    vencidos: int = 0
    proximos: int = 0
    nota_ia: str
    items: list[ItemPlanSalida] = []
