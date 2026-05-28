"""perfil de vehiculo ampliado y billetera de tokens

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ampliación del perfil del vehículo (campos públicos, nullable).
    op.add_column(
        "vehiculos",
        sa.Column("transmision", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "vehiculos",
        sa.Column("tipo_motor", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "vehiculos",
        sa.Column("ciudad_registro", sa.String(length=100), nullable=True),
    )

    # Billetera: saldo de tokens en usuarios. server_default=5 da saldo inicial
    # a los usuarios ya existentes y a los nuevos. CHECK garantiza no-negativo.
    op.add_column(
        "usuarios",
        sa.Column(
            "saldo_tokens",
            sa.Integer(),
            server_default="5",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_usuarios_saldo_tokens_no_negativo",
        "usuarios",
        "saldo_tokens >= 0",
    )

    # Auditoría de transacciones de tokens (inmutable).
    op.create_table(
        "transacciones_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("monto", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(length=255), nullable=False),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transacciones_tokens_usuario_id",
        "transacciones_tokens",
        ["usuario_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transacciones_tokens_usuario_id", table_name="transacciones_tokens"
    )
    op.drop_table("transacciones_tokens")

    op.drop_constraint(
        "ck_usuarios_saldo_tokens_no_negativo", "usuarios", type_="check"
    )
    op.drop_column("usuarios", "saldo_tokens")

    op.drop_column("vehiculos", "ciudad_registro")
    op.drop_column("vehiculos", "tipo_motor")
    op.drop_column("vehiculos", "transmision")
