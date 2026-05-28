from datetime import datetime
from sqlalchemy import String, DateTime, BigInteger, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class EnlaceCompartido(Base):
    """Enlace temporal de solo lectura sobre un vehículo, para mostrarle el
    historial a un comprador interesado sin que necesite cuenta (Fase 4).

    Reglas (CLAUDE.md 10.6):
    - `token` es único (UK) y se genera aleatorio; es la única credencial de acceso.
    - `fecha_expiracion` impone un TTL máximo de 7 días desde la creación.
    - `scope` (JSONB) es opt-in: enumera qué secciones del historial puede ver el
      portador (default mínimo = solo características del auto, ofuscadas).
    """

    __tablename__ = "enlaces_compartidos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    fecha_expiracion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    vehiculo: Mapped["Vehiculo"] = relationship(  # noqa: F821
        back_populates="enlaces_compartidos"
    )
