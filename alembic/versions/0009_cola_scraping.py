"""cola de scraping para el worker híbrido (IP residencial)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cola_scraping",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("identificador", sa.String(length=20), nullable=False),
        sa.Column("fuente", sa.String(length=10), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default="pendiente",
            nullable=False,
        ),
        sa.Column("intentos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_intentos", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "disponible_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tomado_en", sa.DateTime(timezone=True), nullable=True),
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
    )
    # El worker filtra trabajos elegibles por (estado, disponible_en).
    op.create_index(
        "ix_cola_scraping_pendientes",
        "cola_scraping",
        ["estado", "disponible_en"],
    )
    # Idempotencia: índice único PARCIAL. No puede haber dos trabajos vivos
    # (pendiente/en_proceso) para el mismo identificador+fuente. La API encola
    # con INSERT ... ON CONFLICT DO NOTHING contra este índice.
    op.create_index(
        "uq_cola_scraping_activa",
        "cola_scraping",
        ["identificador", "fuente"],
        unique=True,
        postgresql_where=sa.text("estado IN ('pendiente', 'en_proceso')"),
    )


def downgrade() -> None:
    op.drop_index("uq_cola_scraping_activa", table_name="cola_scraping")
    op.drop_index("ix_cola_scraping_pendientes", table_name="cola_scraping")
    op.drop_table("cola_scraping")
