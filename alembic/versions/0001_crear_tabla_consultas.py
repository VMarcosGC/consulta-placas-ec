"""crear tabla consultas

Revision ID: 0001
Revises:
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consultas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("fuente", sa.String(length=10), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("respuesta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consultas_placa_fuente_creado",
        "consultas",
        ["placa", "fuente", "creado_en"],
    )


def downgrade() -> None:
    op.drop_index("ix_consultas_placa_fuente_creado", table_name="consultas")
    op.drop_table("consultas")
