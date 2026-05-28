"""favoritos de vehiculos por usuario

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehiculos_favoritos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("nota", sa.String(length=255), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "placa", name="uq_favoritos_usuario_placa"
        ),
    )
    op.create_index(
        "ix_vehiculos_favoritos_usuario_id", "vehiculos_favoritos", ["usuario_id"]
    )
    op.create_index(
        "ix_vehiculos_favoritos_placa", "vehiculos_favoritos", ["placa"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehiculos_favoritos_placa", table_name="vehiculos_favoritos"
    )
    op.drop_index(
        "ix_vehiculos_favoritos_usuario_id", table_name="vehiculos_favoritos"
    )
    op.drop_table("vehiculos_favoritos")
