"""kilometraje de la publicación interna (market de autos)

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-08

`publicaciones_referenciadas` ya tenía `kilometraje` desde la migración `0019`, pero las
publicaciones internas no: el comprador veía el recorrido de un auto copiado de OLX y no
el de uno publicado aquí. Después del precio, es el dato que más decide una visita.
Misma asimetría que cerró la ciudad en `0023`.

Columna nueva:
- `publicaciones_internas.kilometraje` BigInteger NULL — mismo nombre y mismo tipo que en
  `publicaciones_referenciadas`, para que la tarjeta del feed lea un solo campo y no
  necesite dos ramas. (`BigInteger` es holgado para un odómetro; se elige por paridad
  exacta con la hermana, no por rango. El rango real lo impone Pydantic: 0 … 2 000 000.)

**CAMPO PROPIO, no derivado del garage. SIN BACKFILL.** La columna nace en NULL para
todas las filas existentes y nada la rellena. Tres motivos, medidos contra los datos
reales de producción antes de escribir esto:

1. **El garage es privado y el kilometraje es opt-in explícito.** `SCOPE_PERMITIDO =
   {"kilometraje", "mantenimientos", "duenos_historico"}` en
   `src/modules/marketplace/schemas.py`: el dominio ya modela el kilometraje como algo
   que el dueño **elige** compartir, y solo a través del token de compra-venta con scope
   (§9, §10.6). Derivarlo hacia un anuncio público saltaría por encima de un opt-in que
   el modelo ya tiene construido.
2. **Semántica distinta.** La última lectura de `kilometraje_lecturas` es el odómetro en
   un momento cualquiera del historial privado; lo que se publica es el recorrido que el
   vendedor declara HOY para el anuncio. Son dos hechos, no dos vistas del mismo hecho.
3. **Empíricamente daría NULL para todos.** `kilometraje_lecturas`: 0 filas (0 vehículos).
   `mantenimientos.kilometraje_relacionado`: 0 filas. De las 3 publicaciones internas solo
   1 tiene `vehiculo_id`, y ese vehículo no tiene ni lecturas ni mantenimientos. Un
   backfill hoy no escribiría un solo valor.

Por la misma razón el backend **tampoco deriva el kilometraje en el alta**: sería el mismo
problema movido del backfill al runtime. Se acepta del cliente o queda en NULL. El
formulario lo **propone** con el último valor del garage para que el vendedor lo confirme
(trabajo del frontend), que es estrictamente mejor que una migración afirmando.

Nota de convivencia: `PublicacionInternaSalida` ya exponía un kilometraje distinto,
`ResumenMantenimientos.ultimo_kilometraje` (`max(kilometraje_relacionado)`, solo premium).
No se toca: aquel es "el odómetro en el último service", este es "el odómetro hoy, según
el vendedor". Conviven a propósito; el detalle está anotado en los schemas.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable y sin server_default: NULL significa "el vendedor no lo declaró", que es
    # distinto de 0 km. Publicar sin kilometraje sigue siendo válido — no entra al umbral
    # de activación ni a ninguna validación que bloquee el alta.
    op.add_column(
        "publicaciones_internas",
        sa.Column("kilometraje", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publicaciones_internas", "kilometraje")
