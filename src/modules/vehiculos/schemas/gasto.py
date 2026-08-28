"""Schemas Pydantic para el control de gastos del vehículo (garage).

`tipo` es un catálogo cerrado es-EC validado acá (no en la BD). El resumen (total,
promedio mensual, desglose por tipo) lo calcula el router; estos schemas solo lo
transportan.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TipoGasto = Literal[
    "combustible",
    "mantenimiento",
    "seguro",
    "matricula",
    "peajes",
    "multas",
    "repuestos",
    "lavado",
    "otro",
]


class GastoCrear(BaseModel):
    tipo: TipoGasto
    monto_usd: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    fecha: date
    kilometraje: int | None = Field(default=None, ge=0, le=9_999_999)
    nota: str | None = Field(default=None, max_length=300)


class GastoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehiculo_id: int
    tipo: TipoGasto
    monto_usd: Decimal
    fecha: date
    kilometraje: int | None
    nota: str | None
    creado_en: datetime


class GastoPorTipo(BaseModel):
    tipo: TipoGasto
    total_usd: Decimal
    cantidad: int


class ResumenGastos(BaseModel):
    total_usd: Decimal = Decimal("0")
    cantidad: int = 0
    por_tipo: list[GastoPorTipo] = []
    # Promedio de gasto por mes sobre el rango que va del primer al último registro.
    promedio_mensual_usd: Decimal = Decimal("0")
    meses_con_datos: int = 0
    ultimo_registro: date | None = None
    # Suma de `costo` de los mantenimientos del vehículo (tabla aparte). Se expone para
    # que el garage muestre el gasto TOTAL sin obligar a recargar el mantenimiento como
    # gasto (evita el doble registro).
    mantenimientos_costo_usd: Decimal = Decimal("0")


class GastosVehiculoSalida(BaseModel):
    resumen: ResumenGastos
    items: list[GastoSalida]
