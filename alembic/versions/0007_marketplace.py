"""marketplace: en_venta, precio_venta_usd, url_externa en vehiculos

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Marketplace público. Un auto se lista solo si en_venta y precio_venta_usd>0.
    op.add_column(
        "vehiculos",
        sa.Column(
            "en_venta",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "vehiculos",
        sa.Column("precio_venta_usd", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "vehiculos",
        sa.Column("url_externa", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vehiculos", "url_externa")
    op.drop_column("vehiculos", "precio_venta_usd")
    op.drop_column("vehiculos", "en_venta")
