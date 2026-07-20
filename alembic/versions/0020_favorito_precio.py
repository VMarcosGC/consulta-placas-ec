"""precio de referencia del favorito (MC1 — carril comprador)

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-20

MC1 del carril comprador: la sección "Tus favoritos" de la portada del market muestra
un badge cuando un auto guardado **bajó de precio**. Para eso el favorito necesita
recordar a qué precio estaba el anuncio cuando el usuario lo guardó; la comparación
contra el precio actual la hace el frontend con los datos que ya trae del feed.

Columna nueva en `vehiculos_favoritos`:
- `precio_al_guardar` Numeric(12, 2) **nullable**: mismo tipo que
  `vehiculos.precio_venta_usd` y `publicaciones_internas.precio_usd`, para que la
  comparación sea exacta y sin conversiones.

**Nullable a propósito** (sin backfill): los favoritos ya existentes se guardaron
antes de que hubiera precio de referencia, y una placa favorita puede no tener ninguna
publicación asociada (el favorito es por PLACA, no FK — §10.4). En ambos casos queda
NULL y la tarjeta simplemente no muestra badge. Un 0 fingido implicaría "bajó de
precio" y sería peor que no saber.

Migración manual y revisada a mano (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vehiculos_favoritos",
        sa.Column(
            "precio_al_guardar",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("vehiculos_favoritos", "precio_al_guardar")
