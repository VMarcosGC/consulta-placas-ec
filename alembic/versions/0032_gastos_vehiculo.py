"""gastos_vehiculo: control de gastos del vehículo en el garage

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-28

El garage suma un registro de GASTOS: combustible, mantenimiento, seguro, matrícula,
peajes, multas, repuestos, otros. Cada fila es un desembolso puntual (monto + fecha +
kilometraje opcional + nota). El resumen (total, promedio mensual, desglose por tipo)
lo deriva el endpoint; no se guarda agregado.

`tipo` es String validado en Pydantic (catálogo cerrado es-EC), mismo criterio que la
ficha técnica y los servicios: la BD evoluciona sin migración de tipo.

Solo BD propia (§10.2). Migración manual y revisada a mano. No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gastos_vehiculo",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "vehiculo_id",
            sa.BigInteger(),
            sa.ForeignKey("vehiculos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("monto_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("kilometraje", sa.Integer(), nullable=True),
        sa.Column("nota", sa.String(length=300), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_gastos_vehiculo_vehiculo_fecha",
        "gastos_vehiculo",
        ["vehiculo_id", "fecha"],
    )


def downgrade() -> None:
    op.drop_index("ix_gastos_vehiculo_vehiculo_fecha", table_name="gastos_vehiculo")
    op.drop_table("gastos_vehiculo")
