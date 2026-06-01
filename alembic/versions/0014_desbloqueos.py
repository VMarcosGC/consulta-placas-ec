"""desbloqueos: microdesbloqueos de productos de consulta por tokens

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-31

Tabla `desbloqueos`: registra qué producto del catálogo (código en español) desbloqueó
un usuario para una placa, y cuántos tokens costó. UK (usuario_id, placa, producto) para
no cobrar dos veces. NO guarda el contenido del dato sensible.

Migración manual y revisada a mano (§10.2). El catálogo de productos/precios vive en
código (services/catalogo_productos.py), no en BD.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "desbloqueos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("producto", sa.String(length=40), nullable=False),
        sa.Column("tokens_cobrados", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "placa", "producto", name="uq_desbloqueo_usuario_placa_producto"
        ),
    )
    op.create_index("ix_desbloqueos_usuario_id", "desbloqueos", ["usuario_id"])
    op.create_index("ix_desbloqueos_placa", "desbloqueos", ["placa"])


def downgrade() -> None:
    op.drop_index("ix_desbloqueos_placa", table_name="desbloqueos")
    op.drop_index("ix_desbloqueos_usuario_id", table_name="desbloqueos")
    op.drop_table("desbloqueos")
