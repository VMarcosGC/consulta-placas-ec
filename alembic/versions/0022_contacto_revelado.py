"""registro anónimo de contactos revelados (TASK-001)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-04

Cada vez que un comprador pide el contacto de una publicación se guarda una fila aquí.
Es una **métrica de producto** ("cuántos compradores pidieron el número de este
anuncio"), no un registro de vigilancia (§9):

- No hay `usuario_id`, ni IP, ni user-agent. El contacto es público y gratuito
  (§1.0.3), así que no hay sesión que registrar y no se quiere una.
- La única PII posible sería la del comprador, y deliberadamente no se recoge.

`CheckConstraint`: exactamente uno de los dos FK presente. Una fila sin publicación
sería huérfana y una con las dos, ambigua. Hoy solo el endpoint de publicaciones
internas escribe aquí; la columna de referenciadas queda lista para cuando la
referencia también tenga vendedor con teléfono.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contactos_revelados",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("publicacion_interna_id", sa.BigInteger(), nullable=True),
        sa.Column("publicacion_referenciada_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["publicacion_interna_id"],
            ["publicaciones_internas.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["publicacion_referenciada_id"],
            ["publicaciones_referenciadas.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(publicacion_interna_id IS NOT NULL)::int "
            "+ (publicacion_referenciada_id IS NOT NULL)::int = 1",
            name="ck_contactos_revelados_exactamente_una_publicacion",
        ),
    )
    op.create_index(
        "ix_contactos_revelados_publicacion_interna_id",
        "contactos_revelados",
        ["publicacion_interna_id"],
    )
    op.create_index(
        "ix_contactos_revelados_publicacion_referenciada_id",
        "contactos_revelados",
        ["publicacion_referenciada_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contactos_revelados_publicacion_referenciada_id",
        table_name="contactos_revelados",
    )
    op.drop_index(
        "ix_contactos_revelados_publicacion_interna_id",
        table_name="contactos_revelados",
    )
    op.drop_table("contactos_revelados")
