"""referencias externas ricas (M2.8 — market de autos)

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-19

M2.8: el aportante puede copiar los detalles del anuncio original (Facebook Marketplace,
OLX…) para que la tarjeta de referencia sea útil sin salir del feed. Sigue siendo dato
**no verificado**: la etiqueta "Referencia externa · datos no verificados" se mantiene y
editar el contenido devuelve la referencia a moderación `pendiente`.

Columnas nuevas en `publicaciones_referenciadas` (todas opcionales, sin backfill):
- `descripcion` String(2000): el texto del anuncio original, pegado por el aportante.
- `ciudad` String(80): dónde está el auto (FB casi siempre lo indica).
- `kilometraje` BigInteger: coherente con el tipo usado en el resto del dominio.
- `fotos` JSONB NOT NULL default '[]': lista de URLs (máx. 5, validado en Pydantic —
  el shape lo exige la API, no la BD; mismo criterio que la ficha técnica).

También suma `publicaciones_internas.premium_cobrado_en` (DateTime nullable): marca
**cuándo** se debitó el premium de esa publicación. Hace el cobro idempotente **por dato**
y no por construcción: sin ella, caminos como `light → premium (borrador) → activa`
cobraban dos veces, y `borrador → pausada → activa` se saltaba el umbral sin cobrar.
Se rellena sola al primer cobro; las publicaciones premium ya existentes quedan en NULL y
no se re-cobran porque solo se cobra al pasar a activa (ya lo están).

NOTA sobre `EstadoPublicacion.BORRADOR` (también de M2.8): NO necesita migración.
`publicaciones_internas.estado` es `String(16)`, no un ENUM de Postgres, así que sumar
un valor al enum de Python no altera el esquema. Las filas existentes siguen en `activa`
y no se retro-validan.

Migración manual y revisada a mano (§10.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publicaciones_referenciadas",
        sa.Column("descripcion", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "publicaciones_referenciadas",
        sa.Column("ciudad", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "publicaciones_referenciadas",
        sa.Column("kilometraje", sa.BigInteger(), nullable=True),
    )
    # NOT NULL con server_default: las filas existentes quedan con lista vacía sin
    # necesidad de un UPDATE de backfill.
    op.add_column(
        "publicaciones_referenciadas",
        sa.Column(
            "fotos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


    # Marca de cobro del premium (idempotencia del débito, M2.8).
    op.add_column(
        "publicaciones_internas",
        sa.Column("premium_cobrado_en", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publicaciones_internas", "premium_cobrado_en")
    op.drop_column("publicaciones_referenciadas", "fotos")
    op.drop_column("publicaciones_referenciadas", "kilometraje")
    op.drop_column("publicaciones_referenciadas", "ciudad")
    op.drop_column("publicaciones_referenciadas", "descripcion")
