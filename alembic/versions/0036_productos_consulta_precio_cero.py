"""productos_consulta: todos los precios a 0 (monetización suspendida)

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-03

AGENTS.md §1.0.3 dejó anotada esta deuda: la tabla `productos_consulta` (catálogo de
microdesbloqueos de la consulta por placa) seguía con valores de token > 0 en BD,
dormida y sin UI que la alcanzara, "se pone en 0 (migración) cuando se retome el tema
de la consulta por placa y de dónde colocar costos".

Se retoma ahora (sección aislada `/verificar`, ver
`docs/producto/consulta_datos_fases.md`). Mientras dure la monetización suspendida el
gate real es **login**, no tokens: `debitar_tokens(0)` es un no-op y las ramas 402
quedan cableadas pero inalcanzables.

`downgrade` restaura el seed canónico de `services/catalogo_productos.py` (1 token ≈
USD 0.04) por si se reactiva el cobro.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (codigo, tokens) del seed canónico — para el downgrade.
_PRECIOS_CANONICOS = [
    ("consulta_publica_base", 0),
    ("identificadores_tecnicos", 3),
    ("titular_validado", 5),
    ("alertas_legales", 8),
    ("multas_con_montos", 10),
    ("valores_matricula_sri", 12),
    ("reporte_compra_segura", 40),
    ("verificacion_marketplace", 100),
]


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE productos_consulta "
            "SET tokens = 0, precio_referencial_usd = 0"
        )
    )


def downgrade() -> None:
    for codigo, tokens in _PRECIOS_CANONICOS:
        op.execute(
            sa.text(
                "UPDATE productos_consulta "
                "SET tokens = :t, precio_referencial_usd = :p "
                "WHERE codigo = :c"
            ).bindparams(t=tokens, p=round(tokens * 0.04, 2), c=codigo)
        )
