"""publicaciones del marketplace: internas (light/premium) y referenciadas

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-30

Tablas nuevas separadas del listado basado en `vehiculos.en_venta` (Fase 4 original):
- publicaciones_internas: las publica un usuario sobre su placa; plan light/premium,
  estado y verificación; vínculo opcional al vehículo del garage (ON DELETE SET NULL).
- publicaciones_referenciadas: anuncios raspados de portales externos (sin dueño).

Migración manual y revisada a mano (§10.2). Enums guardados como String (no enum nativo
de PG) para evolucionar sin migraciones de tipo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── publicaciones_internas ──────────────────────────────────────────────
    op.create_table(
        "publicaciones_internas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("vehiculo_id", sa.BigInteger(), nullable=True),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=True),
        sa.Column("descripcion", sa.String(length=2000), nullable=True),
        sa.Column("precio_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "plan", sa.String(length=16), server_default="light", nullable=False
        ),
        sa.Column(
            "estado", sa.String(length=16), server_default="activa", nullable=False
        ),
        sa.Column(
            "estado_verificacion",
            sa.String(length=16),
            server_default="no_verificado",
            nullable=False,
        ),
        sa.Column(
            "destacado", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_publicaciones_internas_usuario_id", "publicaciones_internas", ["usuario_id"]
    )
    op.create_index(
        "ix_publicaciones_internas_vehiculo_id", "publicaciones_internas", ["vehiculo_id"]
    )
    op.create_index(
        "ix_publicaciones_internas_placa", "publicaciones_internas", ["placa"]
    )

    # ── publicaciones_referenciadas ─────────────────────────────────────────
    op.create_table(
        "publicaciones_referenciadas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=True),
        sa.Column("marca", sa.String(length=80), nullable=True),
        sa.Column("modelo", sa.String(length=120), nullable=True),
        sa.Column("anio", sa.BigInteger(), nullable=True),
        sa.Column("precio_usd", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("fuente", sa.String(length=80), nullable=False),
        sa.Column("url_externa", sa.String(length=500), nullable=False),
        sa.Column("imagen_url", sa.String(length=500), nullable=True),
        sa.Column(
            "activa", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_publicaciones_referenciadas_placa", "publicaciones_referenciadas", ["placa"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publicaciones_referenciadas_placa", table_name="publicaciones_referenciadas"
    )
    op.drop_table("publicaciones_referenciadas")
    op.drop_index(
        "ix_publicaciones_internas_placa", table_name="publicaciones_internas"
    )
    op.drop_index(
        "ix_publicaciones_internas_vehiculo_id", table_name="publicaciones_internas"
    )
    op.drop_index(
        "ix_publicaciones_internas_usuario_id", table_name="publicaciones_internas"
    )
    op.drop_table("publicaciones_internas")
