"""verificado_en en publicaciones_internas (auditoría de verificación premium)

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-31

Agrega la columna `verificado_en` (timestamp, nullable) para registrar cuándo un
admin marcó una publicación premium como verificada. El estado en sí vive en
`estado_verificacion` (String): se le suma el valor 'rechazado', que NO requiere
migración por ser una columna String (la validación de valores está en Pydantic).

Migración manual y revisada a mano (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publicaciones_internas",
        sa.Column("verificado_en", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publicaciones_internas", "verificado_en")
