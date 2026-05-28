"""mantenimientos de vehiculos

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mantenimientos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("vehiculo_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.String(length=100), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("kilometraje_relacionado", sa.Integer(), nullable=False),
        sa.Column("taller", sa.String(length=255), nullable=True),
        sa.Column("costo", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"], ["vehiculos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mantenimientos_vehiculo_id", "mantenimientos", ["vehiculo_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_mantenimientos_vehiculo_id", table_name="mantenimientos")
    op.drop_table("mantenimientos")
