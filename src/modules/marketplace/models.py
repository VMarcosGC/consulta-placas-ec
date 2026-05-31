import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String, DateTime, BigInteger, Boolean, Numeric, ForeignKey, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


# ── Enumeraciones del marketplace interno ───────────────────────────────────
# Se guardan como String en la BD (no enum nativo de PG) para evolucionar sin
# migraciones de tipo; la validación de valores vive en los schemas Pydantic.

class PlanPublicacion(str, enum.Enum):
    """Nivel de una publicación interna."""

    LIGHT = "light"      # gratis: aparece en el feed, sin destacar
    PREMIUM = "premium"  # pagado con tokens: destacado + detalles + verificable


class EstadoPublicacion(str, enum.Enum):
    """Ciclo de vida de una publicación interna."""

    ACTIVA = "activa"
    PAUSADA = "pausada"
    VENDIDA = "vendida"


class EstadoVerificacion(str, enum.Enum):
    """Estado de verificación 'Verificado por la plataforma' (solo premium)."""

    NO_VERIFICADO = "no_verificado"
    PENDIENTE = "pendiente"
    VERIFICADO = "verificado"


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


class PublicacionInterna(Base):
    """Publicación de venta creada por un usuario de la plataforma (Pilar 4).

    A diferencia de las referenciadas (raspadas de portales externos), estas las
    publica un usuario sobre una placa suya. El `plan` define el nivel:
    - `light` (gratis): aparece en el feed sin destacar.
    - `premium` (pagado con tokens): `destacado=True`, muestra mantenimientos/consumos
      derivados del garage del usuario y puede llevar la etiqueta
      "Verificado por la plataforma" (`estado_verificacion=verificado`).

    Se relaciona con el Usuario (dueño de la publicación) y con la Placa. El vínculo
    a `vehiculo_id` es OPCIONAL: cuando el usuario tiene esa placa registrada en su
    garage, permite derivar los detalles premium (mantenimientos). Si la borra, el
    FK queda en NULL pero la publicación sobrevive (la placa basta como identidad).
    """

    __tablename__ = "publicaciones_internas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehiculo_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    placa: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    titulo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    precio_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    plan: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=PlanPublicacion.LIGHT.value,
        default=PlanPublicacion.LIGHT.value,
    )
    estado: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=EstadoPublicacion.ACTIVA.value,
        default=EstadoPublicacion.ACTIVA.value,
    )
    estado_verificacion: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=EstadoVerificacion.NO_VERIFICADO.value,
        default=EstadoVerificacion.NO_VERIFICADO.value,
    )
    destacado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
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

    # Vínculo opcional al vehículo del garage (one-directional: no toca el modelo
    # Vehiculo). El router usa selectinload sobre `vehiculo.mantenimientos` para
    # derivar los detalles premium sin N+1.
    vehiculo: Mapped["Vehiculo | None"] = relationship("Vehiculo")  # noqa: F821


class PublicacionReferenciada(Base):
    """Anuncio de venta RASPADO de un portal externo (referencia, no interno).

    No pertenece a ningún usuario ni se verifica: da volumen al feed y siempre
    enlaza a su anuncio de origen (`url_externa`). La placa puede ser desconocida.
    """

    __tablename__ = "publicaciones_referenciadas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    placa: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    marca: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    anio: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    precio_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    fuente: Mapped[str] = mapped_column(String(80), nullable=False)
    url_externa: Mapped[str] = mapped_column(String(500), nullable=False)
    imagen_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
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
