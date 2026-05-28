from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String, Integer, DateTime, BigInteger, Boolean, Numeric,
    ForeignKey, func, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Vehiculo(Base):
    """Vehículo registrado por un usuario. La placa es única por usuario
    (no globalmente — la misma placa puede tener varios dueños en el tiempo).
    """

    __tablename__ = "vehiculos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "placa", name="uq_vehiculos_usuario_placa"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    placa: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    numero_motor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    numero_chasis: Mapped[str | None] = mapped_column(String(50), nullable=True)
    marca: Mapped[str | None] = mapped_column(String(100), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    transmision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tipo_motor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ciudad_registro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Marketplace público (Fase 4). Un auto aparece en /marketplace solo si
    # en_venta es True y precio_venta_usd > 0 (regla de negocio 10.6).
    en_venta: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    precio_venta_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    url_externa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    eliminado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    usuario: Mapped["Usuario"] = relationship(back_populates="vehiculos")  # noqa: F821
    duenos_historico: Mapped[list["DuenoHistorico"]] = relationship(  # noqa: F821
        back_populates="vehiculo",
        cascade="all, delete-orphan",
    )
    kilometraje_lecturas: Mapped[list["KilometrajeLectura"]] = relationship(  # noqa: F821
        back_populates="vehiculo",
        cascade="all, delete-orphan",
    )
    mantenimientos: Mapped[list["Mantenimiento"]] = relationship(  # noqa: F821
        back_populates="vehiculo",
        cascade="all, delete-orphan",
    )
    enlaces_compartidos: Mapped[list["EnlaceCompartido"]] = relationship(  # noqa: F821
        back_populates="vehiculo",
        cascade="all, delete-orphan",
    )
