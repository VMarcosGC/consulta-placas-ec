"""enlaces de compra-venta (token temporal de solo lectura)

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enlaces_compartidos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("vehiculo_id", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fecha_expiracion", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"], ["vehiculos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_enlaces_compartidos_vehiculo_id", "enlaces_compartidos", ["vehiculo_id"]
    )
    # token es la credencial de acceso: índice único (UK). Coincide con
    # `unique=True, index=True` del modelo (un solo índice único).
    op.create_index(
        "ix_enlaces_compartidos_token", "enlaces_compartidos", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(
        "ix_enlaces_compartidos_token", table_name="enlaces_compartidos"
    )
    op.drop_index(
        "ix_enlaces_compartidos_vehiculo_id", table_name="enlaces_compartidos"
    )
    op.drop_table("enlaces_compartidos")
