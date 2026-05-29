from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, BigInteger, ForeignKey, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Mantenimiento(Base):
    """Registro de un mantenimiento del vehículo. Inmutable — no se edita.

    `fecha` y `kilometraje_relacionado` son monotónicos: un registro nuevo no
    puede ser menor al máximo ya registrado para el vehículo (la validación vive
    en el router porque requiere consultar la BD).
    """

    __tablename__ = "mantenimientos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    kilometraje_relacionado: Mapped[int] = mapped_column(Integer, nullable=False)
    taller: Mapped[str | None] = mapped_column(String(255), nullable=True)
    costo: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    vehiculo: Mapped["Vehiculo"] = relationship(  # noqa: F821
        back_populates="mantenimientos"
    )
