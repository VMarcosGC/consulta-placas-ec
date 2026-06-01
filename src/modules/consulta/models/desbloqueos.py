"""Modelos del microdesbloqueo por tokens (v2): catálogo en BD + registro de desbloqueos.

- `ProductoConsulta` (`productos_consulta`): catálogo de productos desbloqueables. Fuente
  de verdad de precios/estado; `codigo` es la clave estable (en español).
- `DesbloqueoConsulta` (`desbloqueos_consulta`): un producto desbloqueado por un usuario
  para una placa. UK usuario+placa+producto → idempotencia (no se recobra). Guarda la
  auditoría comercial (tokens, precio ref., proveedor y costo estimado, cache usada).
- `CostoProveedorConsulta` (`costos_proveedor_consulta`): costo estimado del dato según el
  proveedor externo autorizado (para análisis de margen). Hoy vacío (sin proveedores).

Reemplaza al modelo `Desbloqueo` (v1, tabla `desbloqueos`). Ver
docs/producto/modelo_tokens_microdesbloqueos.md.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Numeric, Boolean, DateTime, BigInteger, ForeignKey,
    UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ProductoConsulta(Base):
    """Catálogo de productos desbloqueables (precios en tokens + USD referencial)."""

    __tablename__ = "productos_consulta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_referencial_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    sensibilidad: Mapped[str] = mapped_column(String(16), nullable=False, default="baja")
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DesbloqueoConsulta(Base):
    """Registro de un producto desbloqueado por un usuario para una placa."""

    __tablename__ = "desbloqueos_consulta"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id", "placa", "producto_codigo",
            name="uq_desbloqueo_consulta_usuario_placa_producto",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    placa: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    producto_codigo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tokens_cobrados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    precio_referencial_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    proveedor_usado: Mapped[str | None] = mapped_column(String(80), nullable=True)
    costo_estimado_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    # Referencia blanda a la fila de caché usada (`consultas.id`); sin FK para no acoplar
    # el ciclo de vida de la caché (TTL/limpieza) al historial de desbloqueos.
    resultado_cache_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CostoProveedorConsulta(Base):
    """Costo estimado de obtener un producto vía un proveedor externo autorizado.

    Para análisis de margen (precio_referencial_usd vs costo_estimado_usd). Hoy vacío:
    no hay proveedores de pago integrados todavía.
    """

    __tablename__ = "costos_proveedor_consulta"
    __table_args__ = (
        UniqueConstraint("producto_codigo", "proveedor", name="uq_costo_proveedor_producto"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    producto_codigo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    proveedor: Mapped[str] = mapped_column(String(80), nullable=False)
    costo_estimado_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
