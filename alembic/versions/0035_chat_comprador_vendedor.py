"""chat interno comprador↔vendedor + barrera de contacto

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-02

Marcos: "termina la parte del chat entre el comprador y vendedor en la web sin dar
paso a WhatsApp si antes no se cumplió algún requisito de seguridad relacionado con
verificación".

Dos tablas:
- `conversaciones`: un hilo por (publicación, comprador). Guarda contadores de no
  leídos por lado y `contacto_habilitado_en` — el sello de que el vendedor ya
  respondió (o compartió su número a mano). Mientras sea NULL, el endpoint
  `POST /publicaciones/{id}/contacto` responde 422 y NO entrega el teléfono.
- `mensajes`: texto plano, `rol_autor` desnormalizado (comprador|vendedor).

`vendedor_usuario_id` se copia del `Vendedor` de la publicación al crear el hilo,
para listar la bandeja del vendedor sin joins.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversaciones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "publicacion_interna_id", sa.BigInteger(),
            sa.ForeignKey("publicaciones_internas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "comprador_usuario_id", sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "vendedor_usuario_id", sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "estado", sa.String(length=16),
            server_default=sa.text("'abierta'"), nullable=False,
        ),
        sa.Column("contacto_habilitado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_mensaje_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "no_leidos_comprador", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "no_leidos_vendedor", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "publicacion_interna_id", "comprador_usuario_id",
            name="uq_conversacion_publicacion_comprador",
        ),
    )
    op.create_index(
        "ix_conversaciones_publicacion", "conversaciones", ["publicacion_interna_id"]
    )
    op.create_index(
        "ix_conversaciones_comprador", "conversaciones", ["comprador_usuario_id"]
    )
    op.create_index(
        "ix_conversaciones_vendedor", "conversaciones", ["vendedor_usuario_id"]
    )
    op.create_index(
        "ix_conversaciones_ultimo_mensaje", "conversaciones", ["ultimo_mensaje_en"]
    )

    op.create_table(
        "mensajes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversacion_id", sa.BigInteger(),
            sa.ForeignKey("conversaciones.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "autor_usuario_id", sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("rol_autor", sa.String(length=12), nullable=False),
        sa.Column("cuerpo", sa.String(length=2000), nullable=False),
        sa.Column("leido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_mensajes_conversacion", "mensajes", ["conversacion_id"]
    )
    op.create_index("ix_mensajes_creado_en", "mensajes", ["creado_en"])


def downgrade() -> None:
    op.drop_index("ix_mensajes_creado_en", table_name="mensajes")
    op.drop_index("ix_mensajes_conversacion", table_name="mensajes")
    op.drop_table("mensajes")
    op.drop_index("ix_conversaciones_ultimo_mensaje", table_name="conversaciones")
    op.drop_index("ix_conversaciones_vendedor", table_name="conversaciones")
    op.drop_index("ix_conversaciones_comprador", table_name="conversaciones")
    op.drop_index("ix_conversaciones_publicacion", table_name="conversaciones")
    op.drop_table("conversaciones")
