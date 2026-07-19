"""ficha técnica de la publicación: 3 bloques + extras (market de autos)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-18

Arranque del market de autos (paso 2 del proyecto): `fichas_publicacion`, 1:1 con
`publicaciones_internas` (UK sobre publicacion_id, ON DELETE CASCADE). Bloques
`motor_suspension`, `carroceria` e `interiores` como JSONB nullable (NULL = el
vendedor aún no llena ese bloque) + `extras` JSONB lista (default []).

El shape de cada bloque NO lo exige la BD: lo validan los schemas Pydantic
(`BloqueMotorSuspension`, `BloqueCarroceria`, `BloqueInteriores` con extra="forbid"
en src/modules/marketplace/schemas.py). Así la ficha evoluciona sin migraciones.

Migración manual y revisada a mano (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fichas_publicacion",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("publicacion_id", sa.BigInteger(), nullable=False),
        sa.Column("motor_suspension", JSONB(), nullable=True),
        sa.Column("carroceria", JSONB(), nullable=True),
        sa.Column("interiores", JSONB(), nullable=True),
        sa.Column(
            "extras", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
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
        sa.ForeignKeyConstraint(
            ["publicacion_id"], ["publicaciones_internas.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publicacion_id", name="uq_fichas_publicacion_publicacion_id"),
    )
    op.create_index(
        "ix_fichas_publicacion_publicacion_id", "fichas_publicacion", ["publicacion_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fichas_publicacion_publicacion_id", table_name="fichas_publicacion"
    )
    op.drop_table("fichas_publicacion")
