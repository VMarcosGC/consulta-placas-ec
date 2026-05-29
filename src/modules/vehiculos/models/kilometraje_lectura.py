from datetime import datetime
from sqlalchemy import String, Integer, DateTime, BigInteger, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class KilometrajeLectura(Base):
    """Lectura de kilometraje en un momento dado. Inmutable — no se edita ni borra."""

    __tablename__ = "kilometraje_lecturas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kilometros: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_lectura: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    nota: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    vehiculo: Mapped["Vehiculo"] = relationship(  # noqa: F821
        back_populates="kilometraje_lecturas"
    )
