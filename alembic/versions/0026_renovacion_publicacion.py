"""renovación de la publicación interna (antigüedad + depuración de data vieja)

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-27

El feed y la búsqueda mostraban los anuncios por `creado_en` sin más: un auto
publicado hace tres meses seguía compitiendo de igual a igual con uno de ayer, y
nada empujaba al vendedor a bajarlo o confirmar que sigue a la venta. Decisión de
producto (Marcos, 2026-08-27): a las N semanas sin renovar (hoy 3, env-overridable
`PUBLICACION_SEMANAS_VIGENCIA`), el anuncio pierde vigencia → cae al final del feed
y de `/buscar`, y el dueño ve el botón "Renovar" mientras siga `activa`. Renovar
vuelve a ponerlo al frente. Empuja a depurar sin borrar nada.

Columna nueva:
- `publicaciones_internas.renovada_en` TIMESTAMPTZ NOT NULL, server_default `now()`.
  Es "la última vez que el anuncio se puso al frente" = fecha de publicación, o de
  la última renovación. La antigüedad del anuncio se mide como `now() - renovada_en`.

Por qué una columna PROPIA y no reutilizar `actualizado_en`: `actualizado_en` se
bumpea con CUALQUIER edición (`onupdate=func.now()`), incluido un cambio de precio.
Si la antigüedad dependiera de eso, tocar el precio "renovaría" el anuncio de
rebote y la depuración no serviría de nada. `renovada_en` SOLO cambia por el
endpoint explícito `POST /marketplace/publicaciones/{id}/renovar`.

Backfill: las filas existentes toman `renovada_en = creado_en` (su antigüedad real
arranca desde que se publicaron, no desde esta migración). Es una sola pasada y
`creado_en` es NOT NULL en todas, así que no quedan nulos.

Índice `ix_publicaciones_internas_renovada_en`: la búsqueda ordena y filtra por el
predicado de vigencia (`coalesce(renovada_en, creado_en) >= umbral`), y el feed lo
lee para partir vigentes/rezagadas.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Se agrega nullable para poder backfillear sin un default que mienta.
    op.add_column(
        "publicaciones_internas",
        sa.Column("renovada_en", sa.DateTime(timezone=True), nullable=True),
    )
    # 2) Backfill: la antigüedad de un anuncio viejo arranca cuando se publicó.
    op.execute(
        "UPDATE publicaciones_internas "
        "SET renovada_en = creado_en "
        "WHERE renovada_en IS NULL"
    )
    # 3) Ya sin nulos: NOT NULL + default para inserciones futuras (una publicación
    #    nueva nace "recién renovada", igual que su creado_en).
    op.alter_column(
        "publicaciones_internas",
        "renovada_en",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    op.create_index(
        "ix_publicaciones_internas_renovada_en",
        "publicaciones_internas",
        ["renovada_en"],
    )


def downgrade() -> None:
    op.drop_index("ix_publicaciones_internas_renovada_en", table_name="publicaciones_internas")
    op.drop_column("publicaciones_internas", "renovada_en")
