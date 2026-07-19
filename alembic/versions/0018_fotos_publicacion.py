"""fotos de la publicación (M2 — market de autos)

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-19

M2 del market de autos: `fotos_publicacion`, N:1 con `publicaciones_internas`
(ON DELETE CASCADE, índice sobre publicacion_id). El binario no se aloja aquí: el
navegador sube directo a Cloudinary con una firma que genera el backend, y esta
tabla guarda solo la `url` de entrega.

- `url` String(2048): las URLs de CDN (transformaciones + versiones firmadas) superan
  los 500 con facilidad (mismo criterio que publicaciones_referenciadas.imagen_url).
- `bloque` String(20) nullable: catálogo motor_suspension|carroceria|interiores|general
  validado por Pydantic, NO por la BD (mismo criterio que la ficha).
- `orden` Integer default 0: posición en la galería; la primera es la portada del feed.

Migración manual y revisada a mano (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fotos_publicacion",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("publicacion_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("bloque", sa.String(length=20), nullable=True),
        sa.Column(
            "orden", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["publicacion_id"], ["publicaciones_internas.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fotos_publicacion_publicacion_id", "fotos_publicacion", ["publicacion_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fotos_publicacion_publicacion_id", table_name="fotos_publicacion"
    )
    op.drop_table("fotos_publicacion")
