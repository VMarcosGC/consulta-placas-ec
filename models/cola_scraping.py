from datetime import datetime

from sqlalchemy import String, Integer, DateTime, BigInteger, Text, Index, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# Estados del ciclo de vida de un trabajo en la cola (ver docs/arquitectura_hibrida.md).
ESTADO_PENDIENTE = "pendiente"
ESTADO_EN_PROCESO = "en_proceso"
ESTADO_COMPLETADO = "completado"
ESTADO_FALLIDO = "fallido"

# Estados "vivos": un trabajo en estos estados aún ocupa el cupo de idempotencia
# (no se puede encolar otro para el mismo identificador+fuente).
ESTADOS_ACTIVOS = (ESTADO_PENDIENTE, ESTADO_EN_PROCESO)


class ColaScraping(Base):
    """Cola de trabajos de scraping para el worker híbrido (IP residencial).

    La API encola aquí cuando hay cache miss de AMT/FGE desde una IP de datacenter
    (que esos portales bloquean). Un worker pull-only en IP residencial toma los
    trabajos con FOR UPDATE SKIP LOCKED, ejecuta services/<fuente>.py y guarda el
    resultado en `consultas` (la caché). Esta tabla solo coordina el trabajo; el
    resultado del scraping NO vive aquí.

    Ver diseño completo en docs/arquitectura_hibrida.md.
    """

    __tablename__ = "cola_scraping"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # placa o cédula (FGE), ya normalizada por el validador correspondiente.
    identificador: Mapped[str] = mapped_column(String(20), nullable=False)
    fuente: Mapped[str] = mapped_column(String(10), nullable=False)

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=ESTADO_PENDIENTE
    )

    intentos: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_intentos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )

    # Contexto opcional del trabajo (forward-compatible). El resultado del scraping
    # se persiste en `consultas`, no aquí.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # repr del último error (diagnóstico). Solo poblado en reintentos/fallos.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Momento a partir del cual el trabajo es elegible (backoff exponencial).
    disponible_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Cuándo lo tomó un worker; sirve para detectar zombis (worker caído a mitad).
    tomado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # El worker filtra elegibles por aquí.
        Index("ix_cola_scraping_pendientes", "estado", "disponible_en"),
        # Idempotencia: no encolar dos veces la misma placa+fuente mientras hay un
        # trabajo vivo. La API inserta con ON CONFLICT DO NOTHING contra este índice.
        Index(
            "uq_cola_scraping_activa",
            "identificador",
            "fuente",
            unique=True,
            postgresql_where=text("estado IN ('pendiente', 'en_proceso')"),
        ),
    )
