"""ampliar imagen_url de referencias a 2048 (URLs de CDN firmadas son largas)

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-30

Las URLs de imagen de Facebook (fbcdn) y otros CDN traen parámetros firmados y superan
los 500 caracteres. Se amplía la columna a 2048. Migración manual (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "publicaciones_referenciadas",
        "imagen_url",
        existing_type=sa.String(length=500),
        type_=sa.String(length=2048),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "publicaciones_referenciadas",
        "imagen_url",
        existing_type=sa.String(length=2048),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
