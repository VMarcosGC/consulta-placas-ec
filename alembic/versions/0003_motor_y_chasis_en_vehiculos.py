"""agregar numero_motor y numero_chasis a vehiculos

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vehiculos",
        sa.Column("numero_motor", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "vehiculos",
        sa.Column("numero_chasis", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vehiculos", "numero_chasis")
    op.drop_column("vehiculos", "numero_motor")
