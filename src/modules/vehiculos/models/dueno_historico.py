from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, BigInteger, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class DuenoHistorico(Base):
    """Cambio de propietario de un vehículo. `hasta` NULL significa dueño actual."""

    __tablename__ = "duenos_historico"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cedula_dueno: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre_dueno: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    vehiculo: Mapped["Vehiculo"] = relationship(  # noqa: F821
        back_populates="duenos_historico"
    )
