"""servicios: columna `horario` (texto libre)

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-27

El directorio de servicios muestra el horario de atención de cada negocio. Es texto
libre ("Lun a Vie 8:00–18:00, Sáb 8:00–13:00"): cada taller lo escribe a su manera y
el frontend solo lo pinta. Columna nullable — los negocios ya cargados no lo tienen.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "servicios",
        sa.Column("horario", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("servicios", "horario")
