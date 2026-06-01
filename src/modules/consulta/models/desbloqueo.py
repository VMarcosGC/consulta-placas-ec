from datetime import datetime

from sqlalchemy import String, Integer, DateTime, BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Desbloqueo(Base):
    """Un producto de consulta desbloqueado por un usuario para una placa (Pilar 1+).

    Modelo de microdesbloqueos (ver docs/producto/modelo_tokens_microdesbloqueos.md):
    cada fila = un producto del catálogo que el usuario ya pagó con tokens para una
    placa concreta. Sirve para **no cobrar dos veces**: si el producto ya está aquí,
    el dato se sirve sin nuevo débito (idempotencia por la UK usuario+placa+producto).

    Guarda solo *qué* se compró (código + placa + tokens), **nunca** el contenido del
    dato sensible (eso vive en la fuente/caché). `tokens_cobrados` es histórico: lo que
    costó al momento de la compra (el precio del catálogo puede cambiar después).
    """

    __tablename__ = "desbloqueos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "placa", "producto", name="uq_desbloqueo_usuario_placa_producto"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    placa: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    producto: Mapped[str] = mapped_column(String(40), nullable=False)
    tokens_cobrados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
