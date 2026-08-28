"""publicaciones_internas: columna `vendido_en`

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-28

Marcar un anuncio como `vendida` ya existía (máquina de estados en
`routers/publicaciones.py::_aplicar_transicion_estado`). Faltaba la FECHA de la venta
para poder armar el "resumen de autos vendidos" en `mis-publicaciones` ("Vendido el
12 de agosto"). `actualizado_en` no sirve: cambia con cualquier edición.

`vendido_en` lo pone el endpoint al entrar a `vendida` y lo limpia al salir de ese
estado (volver a publicar). Columna nullable — NULL = no está vendida.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publicaciones_internas",
        sa.Column("vendido_en", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: las que ya están 'vendida' toman `actualizado_en` como mejor
    # aproximación disponible a la fecha de venta.
    op.execute(
        "UPDATE publicaciones_internas "
        "SET vendido_en = actualizado_en "
        "WHERE estado = 'vendida' AND vendido_en IS NULL"
    )


def downgrade() -> None:
    op.drop_column("publicaciones_internas", "vendido_en")
