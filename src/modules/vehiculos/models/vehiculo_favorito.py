from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String, DateTime, BigInteger, Numeric, ForeignKey, func, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class VehiculoFavorito(Base):
    """Placa marcada como favorita por un usuario.

    La placa se guarda como `String` (no FK a `vehiculos`) a propósito: un usuario
    puede seguir una placa que no existe en nuestra BD ni le pertenece. Única por
    usuario+placa (no se repite el mismo favorito).
    """

    __tablename__ = "vehiculos_favoritos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "placa", name="uq_favoritos_usuario_placa"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    placa: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    nota: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Precio del anuncio en el momento de guardarlo (MC1, carril comprador). Sirve de
    # referencia para avisar de una baja de precio: el frontend lo compara contra el
    # precio actual que ya trae del feed y pinta el badge si bajó. Nullable porque los
    # favoritos previos no lo tienen y porque una placa favorita puede no tener
    # publicación (el favorito es por placa, no FK); sin referencia, no hay badge.
    precio_al_guardar: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    usuario: Mapped["Usuario"] = relationship(back_populates="favoritos")  # noqa: F821
