"""usuarios, vehiculos, duenos_historico, kilometraje_lecturas

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    op.create_table(
        "vehiculos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("placa", sa.String(length=10), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=True),
        sa.Column("marca", sa.String(length=100), nullable=True),
        sa.Column("modelo", sa.String(length=100), nullable=True),
        sa.Column("anio", sa.Integer(), nullable=True),
        sa.Column("color", sa.String(length=50), nullable=True),
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
        sa.Column("eliminado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "placa", name="uq_vehiculos_usuario_placa"
        ),
    )
    op.create_index("ix_vehiculos_usuario_id", "vehiculos", ["usuario_id"])
    op.create_index("ix_vehiculos_placa", "vehiculos", ["placa"])

    op.create_table(
        "duenos_historico",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("vehiculo_id", sa.BigInteger(), nullable=False),
        sa.Column("cedula_dueno", sa.String(length=10), nullable=False),
        sa.Column("nombre_dueno", sa.String(length=255), nullable=True),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date(), nullable=True),
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
        "ix_duenos_historico_vehiculo_id", "duenos_historico", ["vehiculo_id"]
    )

    op.create_table(
        "kilometraje_lecturas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("vehiculo_id", sa.BigInteger(), nullable=False),
        sa.Column("kilometros", sa.Integer(), nullable=False),
        sa.Column("fecha_lectura", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nota", sa.String(length=500), nullable=True),
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
        "ix_kilometraje_lecturas_vehiculo_id",
        "kilometraje_lecturas",
        ["vehiculo_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_kilometraje_lecturas_vehiculo_id", table_name="kilometraje_lecturas"
    )
    op.drop_table("kilometraje_lecturas")

    op.drop_index("ix_duenos_historico_vehiculo_id", table_name="duenos_historico")
    op.drop_table("duenos_historico")

    op.drop_index("ix_vehiculos_placa", table_name="vehiculos")
    op.drop_index("ix_vehiculos_usuario_id", table_name="vehiculos")
    op.drop_table("vehiculos")

    op.drop_index("ix_usuarios_email", table_name="usuarios")
    op.drop_table("usuarios")
