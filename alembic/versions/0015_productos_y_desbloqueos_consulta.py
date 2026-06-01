"""microdesbloqueos v2: catalogo en BD (productos_consulta) + desbloqueos_consulta + costos_proveedor

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-31

Evoluciona el microdesbloqueo v1 (tabla `desbloqueos` + catalogo en codigo) a un modelo con
catalogo persistido y auditoria comercial:
- `productos_consulta`: catalogo (codigo, nombre, tokens, precio_referencial_usd, sensibilidad,
  activo). Se SIEMBRA idempotente (ON CONFLICT DO NOTHING por codigo).
- `desbloqueos_consulta`: reemplaza `desbloqueos` con campos de auditoria (precio ref., proveedor,
  costo estimado, cache usada). UK usuario+placa+producto.
- `costos_proveedor_consulta`: costo por proveedor externo (analisis de margen; hoy vacio).

La tabla `desbloqueos` (v1) se elimina: solo tenia datos de prueba. Migracion manual (10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Catalogo base (1 token = USD 0.05). Codigos estables en espanol. Sin apostrofes en
# las descripciones para mantener el INSERT simple.
_SEED = [
    ("vehiculo_basico", "Ficha basica", "Clase, servicio y fechas de matricula (marca/modelo/anio/color son gratis).", 3, "0.15", "baja", 10),
    ("vehiculo_tecnico", "Datos tecnicos", "Cilindraje, tipo de motor, transmision y combustible (segun disponibilidad).", 2, "0.10", "baja", 20),
    ("vehiculo_identificadores", "VIN, motor y chasis", "Identificadores ofuscados a origen (primeros caracteres + pais del WMI).", 3, "0.15", "media", 30),
    ("vehiculo_titular_validado", "Titular validado", "Validacion del titular (coincide/ofuscado), nunca el dato crudo. Requiere proveedor autorizado.", 5, "0.25", "alta", 40),
    ("vehiculo_multas", "Multas e infracciones", "Detalle con montos por fuente (ANT/AMT): pendientes, total a pagar y categorias.", 8, "0.40", "media", 50),
    ("reporte_compra_segura", "Reporte de compra segura", "Combo con descuento: ficha basica + tecnico + identificadores + multas.", 30, "1.50", "alta", 60),
    ("verificacion_marketplace", "Verificacion de la plataforma", "Sello Verificado por la plataforma para una publicacion premium del marketplace.", 80, "4.00", "alta", 70),
]


def upgrade() -> None:
    op.create_table(
        "productos_consulta",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.String(length=500), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("precio_referencial_usd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("sensibilidad", sa.String(length=16), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo", name="uq_productos_consulta_codigo"),
    )
    op.create_index("ix_productos_consulta_codigo", "productos_consulta", ["codigo"], unique=True)

    op.create_table(
        "desbloqueos_consulta",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("producto_codigo", sa.String(length=40), nullable=False),
        sa.Column("tokens_cobrados", sa.Integer(), nullable=False),
        sa.Column("precio_referencial_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("proveedor_usado", sa.String(length=80), nullable=True),
        sa.Column("costo_estimado_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("resultado_cache_id", sa.BigInteger(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "placa", "producto_codigo",
            name="uq_desbloqueo_consulta_usuario_placa_producto",
        ),
    )
    op.create_index("ix_desbloqueos_consulta_usuario_id", "desbloqueos_consulta", ["usuario_id"])
    op.create_index("ix_desbloqueos_consulta_placa", "desbloqueos_consulta", ["placa"])
    op.create_index("ix_desbloqueos_consulta_producto_codigo", "desbloqueos_consulta", ["producto_codigo"])

    op.create_table(
        "costos_proveedor_consulta",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("producto_codigo", sa.String(length=40), nullable=False),
        sa.Column("proveedor", sa.String(length=80), nullable=False),
        sa.Column("costo_estimado_usd", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("producto_codigo", "proveedor", name="uq_costo_proveedor_producto"),
    )
    op.create_index("ix_costos_proveedor_consulta_producto_codigo", "costos_proveedor_consulta", ["producto_codigo"])

    # Elimina la tabla v1 (solo datos de prueba).
    op.drop_table("desbloqueos")

    # Siembra del catalogo (idempotente: no duplica si el codigo ya existe).
    valores = ", ".join(
        "('{codigo}', '{nombre}', '{desc}', {tokens}, {precio}, '{sens}', {orden})".format(
            codigo=c, nombre=n, desc=d, tokens=t, precio=p, sens=s, orden=o
        )
        for (c, n, d, t, p, s, o) in _SEED
    )
    op.execute(
        "INSERT INTO productos_consulta "
        "(codigo, nombre, descripcion, tokens, precio_referencial_usd, sensibilidad, orden) "
        f"VALUES {valores} ON CONFLICT (codigo) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_index("ix_costos_proveedor_consulta_producto_codigo", table_name="costos_proveedor_consulta")
    op.drop_table("costos_proveedor_consulta")
    op.drop_index("ix_desbloqueos_consulta_producto_codigo", table_name="desbloqueos_consulta")
    op.drop_index("ix_desbloqueos_consulta_placa", table_name="desbloqueos_consulta")
    op.drop_index("ix_desbloqueos_consulta_usuario_id", table_name="desbloqueos_consulta")
    op.drop_table("desbloqueos_consulta")
    op.drop_index("ix_productos_consulta_codigo", table_name="productos_consulta")
    op.drop_table("productos_consulta")
    # Recrea la tabla v1 minima (por si se revierte).
    op.create_table(
        "desbloqueos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("producto", sa.String(length=40), nullable=False),
        sa.Column("tokens_cobrados", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "placa", "producto", name="uq_desbloqueo_usuario_placa_producto"),
    )
