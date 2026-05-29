from datetime import datetime
from sqlalchemy import (
    String, Integer, DateTime, BigInteger, ForeignKey, CheckConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

# Saldo de cortesía con el que nace toda cuenta nueva (regla de negocio 10.3).
SALDO_INICIAL_TOKENS = 5


class Usuario(Base):
    """Cuenta de usuario autenticada. Dueño lógico de sus vehículos en el sistema."""

    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("saldo_tokens >= 0", name="ck_usuarios_saldo_tokens_no_negativo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    saldo_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="5", default=SALDO_INICIAL_TOKENS
    )
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

    vehiculos: Mapped[list["Vehiculo"]] = relationship(  # noqa: F821
        back_populates="usuario",
        cascade="all, delete-orphan",
    )
    transacciones_tokens: Mapped[list["TransaccionToken"]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
    )
    favoritos: Mapped[list["VehiculoFavorito"]] = relationship(  # noqa: F821
        back_populates="usuario",
        cascade="all, delete-orphan",
    )


class TransaccionToken(Base):
    """Registro de auditoría de toda alteración del saldo de tokens de un usuario.
    Inmutable — no se edita ni borra. `monto` es positivo (crédito) o negativo (débito).
    """

    __tablename__ = "transacciones_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monto: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    usuario: Mapped["Usuario"] = relationship(back_populates="transacciones_tokens")
