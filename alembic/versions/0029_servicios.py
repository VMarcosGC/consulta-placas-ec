"""directorio de servicios automotrices (talleres, lavaderos, luces, accesorios…)

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-27

Un usuario propone un negocio (`POST /marketplace/servicios`); entra `pendiente` y un
admin lo aprueba/rechaza antes de que aparezca en el directorio público — mismo patrón
que `publicaciones_referenciadas`. El directorio demo del frontend
(`src/config/servicios.ts`) se mantiene como relleno hasta que haya negocios reales.

Tabla `servicios`:
- `categoria` String (catálogo cerrado validado en Pydantic, no en la BD, igual que la
  ficha técnica): mecanica | mecanica_certificada | centro_servicio | lavadero | luces |
  accesorios | otro.
- `provincia` del catálogo de `geografia.py`; `ciudad` texto libre.
- `telefono` E.164 sin `+` (para wa.me), opcional.
- `estado_moderacion` pendiente|aprobado|rechazado + `activo` (pausar sin re-moderar).
- `aportado_por_usuario_id` NULL si algún día se siembra por otra vía.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "servicios",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("categoria", sa.String(length=32), nullable=False),
        sa.Column("provincia", sa.String(length=80), nullable=False),
        sa.Column("ciudad", sa.String(length=80), nullable=False),
        sa.Column("descripcion", sa.String(length=1000), nullable=True),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column("whatsapp", sa.String(length=20), nullable=True),
        sa.Column("direccion", sa.String(length=200), nullable=True),
        sa.Column("url_externa", sa.String(length=500), nullable=True),
        sa.Column(
            "certificado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "estado_moderacion",
            sa.String(length=16),
            server_default=sa.text("'pendiente'"),
            nullable=False,
        ),
        sa.Column(
            "activo", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "aportado_por_usuario_id",
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
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_servicios_estado_moderacion", "servicios", ["estado_moderacion"])
    op.create_index("ix_servicios_provincia", "servicios", ["provincia"])
    op.create_index("ix_servicios_categoria", "servicios", ["categoria"])


def downgrade() -> None:
    op.drop_index("ix_servicios_categoria", table_name="servicios")
    op.drop_index("ix_servicios_provincia", table_name="servicios")
    op.drop_index("ix_servicios_estado_moderacion", table_name="servicios")
    op.drop_table("servicios")
