from datetime import datetime
from sqlalchemy import String, DateTime, BigInteger, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Consulta(Base):
    """Caché de respuestas crudas de fuentes públicas por placa+fuente."""

    __tablename__ = "consultas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    placa: Mapped[str] = mapped_column(String(10), nullable=False)
    fuente: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(String(30), nullable=False)
    respuesta: Mapped[dict] = mapped_column(JSONB, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_consultas_placa_fuente_creado", "placa", "fuente", "creado_en"),
    )
