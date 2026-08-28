"""calificaciones de comprador a vendedor

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-27

Un comprador califica a un vendedor (1..5 estrellas + comentario opcional). Solo esa
dirección: el contacto es anónimo (`contactos_revelados` no guarda quién pidió el
número), así que el vendedor no puede identificar ni calificar a un comprador.

Tabla nueva `calificaciones`:
- UK `(autor_usuario_id, vendedor_id)` → una por comprador por vendedor; volver a
  calificar la ACTUALIZA, no acumula.
- `publicacion_interna_id` NULL = solo contexto (desde qué anuncio), no afecta unicidad;
  ON DELETE SET NULL para que borrar el anuncio no borre la calificación.
- CHECK `estrellas BETWEEN 1 AND 5`.
- Índices por `autor_usuario_id` y `vendedor_id` (el promedio se agrupa por vendedor).

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calificaciones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "autor_usuario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vendedor_id",
            sa.BigInteger(),
            sa.ForeignKey("vendedores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publicacion_interna_id",
            sa.BigInteger(),
            sa.ForeignKey("publicaciones_internas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("estrellas", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.String(length=1000), nullable=True),
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
        sa.UniqueConstraint(
            "autor_usuario_id", "vendedor_id", name="uq_calificaciones_autor_vendedor"
        ),
        sa.CheckConstraint(
            "estrellas BETWEEN 1 AND 5", name="ck_calificaciones_estrellas_rango"
        ),
    )
    op.create_index(
        "ix_calificaciones_autor_usuario_id", "calificaciones", ["autor_usuario_id"]
    )
    op.create_index(
        "ix_calificaciones_vendedor_id", "calificaciones", ["vendedor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_calificaciones_vendedor_id", table_name="calificaciones")
    op.drop_index("ix_calificaciones_autor_usuario_id", table_name="calificaciones")
    op.drop_table("calificaciones")
