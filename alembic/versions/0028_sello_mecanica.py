"""sello "revisado por mecánica" + códigos de certificación

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-27

Una mecánica revisa el auto y le da al vendedor un CÓDIGO de un solo uso; el vendedor
lo canjea en su publicación y aparece el sello "revisado por {mecánica}".

Para que el sello NO se desvalorice: los códigos los crea un admin (la plataforma decide
qué mecánicas los reciben), se canjean una vez, expiran, y el sello guarda el nombre y
la fecha (específico y rastreable, no un "verificado" genérico).

- Tabla `codigos_certificacion` (codigo único, mecanica_nombre/ciudad, emitido_por,
  expira_en, usado_en, usado_publicacion_id).
- `publicaciones_internas`: `mecanica_nombre`, `mecanica_ciudad`,
  `certificado_mecanica_en` (los tres NULL = sin sello).

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "codigos_certificacion",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.String(length=24), nullable=False),
        sa.Column("mecanica_nombre", sa.String(length=120), nullable=False),
        sa.Column("mecanica_ciudad", sa.String(length=80), nullable=False),
        sa.Column(
            "emitido_por_usuario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "usado_publicacion_id",
            sa.BigInteger(),
            sa.ForeignKey("publicaciones_internas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("codigo", name="uq_codigos_certificacion_codigo"),
    )
    op.create_index(
        "ix_codigos_certificacion_codigo", "codigos_certificacion", ["codigo"]
    )

    op.add_column(
        "publicaciones_internas",
        sa.Column("mecanica_nombre", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "publicaciones_internas",
        sa.Column("mecanica_ciudad", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "publicaciones_internas",
        sa.Column("certificado_mecanica_en", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publicaciones_internas", "certificado_mecanica_en")
    op.drop_column("publicaciones_internas", "mecanica_ciudad")
    op.drop_column("publicaciones_internas", "mecanica_nombre")
    op.drop_index(
        "ix_codigos_certificacion_codigo", table_name="codigos_certificacion"
    )
    op.drop_table("codigos_certificacion")
