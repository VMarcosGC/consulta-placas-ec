from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class GastoVehiculo(Base):
    """Un desembolso puntual sobre el vehículo (combustible, mantenimiento, seguro…).

    A diferencia de `Mantenimiento`, un gasto NO es monotónico ni inmutable de forma
    dura: se puede borrar y volver a cargar (registro contable simple). El `tipo` es un
    catálogo cerrado validado en Pydantic (`schemas/gasto.py`), no en la BD.

    El resumen (total, promedio mensual, desglose por tipo) lo calcula el router a
    partir de estas filas; no hay columna agregada.
    """

    __tablename__ = "gastos_vehiculo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    kilometraje: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nota: Mapped[str | None] = mapped_column(String(300), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vehiculo: Mapped["Vehiculo"] = relationship()  # noqa: F821
