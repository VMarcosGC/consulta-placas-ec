"""ciudad de la publicación interna (market de autos)

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-08

`publicaciones_referenciadas` ya tenía `ciudad` desde la migración `0019`, pero las
publicaciones internas no: un comprador en Quito podía ver dónde está un auto copiado de
OLX y no uno publicado en la plataforma. En un market de autos la ciudad es lo que decide
si vale la pena abrir el anuncio.

Columna nueva:
- `publicaciones_internas.ciudad` String(80) NULL — mismo nombre y mismo tipo que en
  `publicaciones_referenciadas`, para que la tarjeta del feed lea un solo campo y no
  necesite dos ramas. (Ojo: `vehiculos.ciudad_registro` es String(100) y es otra cosa;
  ver abajo.)

La **lista de ciudades permitidas vive en el código** (`CiudadPublicacion`, un `Literal`
de `src/modules/marketplace/schemas.py`), no en una tabla de catálogo — mismo criterio que
los catálogos de la ficha técnica (`Combustible`, `Transmision`, …): cambia rara vez, la
decide quien despliega, no hay nada que auditar y el `Literal` da el 422 gratis. La BD solo
guarda el texto; el shape lo exige la API.

**SIN BACKFILL, y es deliberado.** La columna nace en NULL para todas las filas
existentes. Tres motivos, medidos contra los datos reales de producción antes de escribir
esto:

1. **`vehiculos.ciudad_registro` es dónde se MATRICULÓ el auto, no dónde está en venta.**
   Son dos cosas distintas: un auto matriculado en Quito puede estar vendiéndose en Manta.
   Derivar una de la otra es una inferencia disfrazada de dato.
2. **Cubriría 1 de 3 filas.** De las 3 publicaciones internas solo 1 tiene `vehiculo_id`, y
   ese vehículo es el único de los 3 del garage con `ciudad_registro` (`'QUITO'`). Las 3
   referencias tienen `ciudad` en NULL, así que tampoco hay de dónde tomarla.
3. **El vendedor va a elegir la ciudad en el formulario**, con el valor del garage
   prellenado por el frontend para que él lo confirme. Un humano confirmando es
   estrictamente mejor que una migración afirmando.

Por la misma razón el backend **tampoco deriva la ciudad en el alta**: sería el mismo
problema, movido del backfill al runtime. `ciudad` se acepta del cliente o queda en NULL.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable y sin server_default: NULL significa "el vendedor todavía no la indicó",
    # que es distinto de cualquier ciudad concreta que pudiéramos inventar.
    op.add_column(
        "publicaciones_internas",
        sa.Column("ciudad", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publicaciones_internas", "ciudad")
