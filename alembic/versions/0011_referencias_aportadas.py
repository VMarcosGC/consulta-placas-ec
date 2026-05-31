"""referencias del marketplace aportadas por el usuario (link externo + moderación)

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-30

Las publicaciones referenciadas dejan de ser "raspadas sin dueño": ahora las aporta un
usuario pegando un link (p. ej. Facebook Marketplace). Por eso se agrega:
- usuario_id: aportante (ON DELETE SET NULL; NULL si se sembrara por otra vía).
- estado_moderacion: entran como 'pendiente'; un admin las aprueba para el feed.
- url_externa pasa a ser ÚNICA (dedup: el mismo anuncio no entra dos veces).

Migración manual y revisada a mano (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publicaciones_referenciadas",
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "publicaciones_referenciadas",
        sa.Column(
            "estado_moderacion",
            sa.String(length=16),
            server_default="pendiente",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_publicaciones_referenciadas_usuario_id",
        "publicaciones_referenciadas",
        "usuarios",
        ["usuario_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_publicaciones_referenciadas_usuario_id",
        "publicaciones_referenciadas",
        ["usuario_id"],
    )
    op.create_index(
        "ix_publicaciones_referenciadas_estado_moderacion",
        "publicaciones_referenciadas",
        ["estado_moderacion"],
    )
    op.create_index(
        "ix_publicaciones_referenciadas_url_externa",
        "publicaciones_referenciadas",
        ["url_externa"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publicaciones_referenciadas_url_externa",
        table_name="publicaciones_referenciadas",
    )
    op.drop_index(
        "ix_publicaciones_referenciadas_estado_moderacion",
        table_name="publicaciones_referenciadas",
    )
    op.drop_index(
        "ix_publicaciones_referenciadas_usuario_id",
        table_name="publicaciones_referenciadas",
    )
    op.drop_constraint(
        "fk_publicaciones_referenciadas_usuario_id",
        "publicaciones_referenciadas",
        type_="foreignkey",
    )
    op.drop_column("publicaciones_referenciadas", "estado_moderacion")
    op.drop_column("publicaciones_referenciadas", "usuario_id")
