"""agendamiento de citas para el directorio de servicios

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-30

Propuesta de producto (Marcos): la plataforma ofrece agendamiento de citas para los
negocios del directorio de servicios. Dos lados:
- El negocio opta por recibir citas: `servicios.acepta_agendamiento`.
- El cliente pide una cita (fecha + franja + motivo + contacto); el negocio la
  confirma, reprograma o rechaza; el cliente la puede cancelar.

Tabla `citas_servicio`:
- `estado`: solicitada | confirmada | reprogramada | rechazada | cancelada | cumplida.
- `motivo` es catálogo cerrado validado en Pydantic (mantenimiento, revisión, …).
- `franja` gruesa (mañana/tarde/noche/todo el día), igual criterio que las presencias
  de los puntos de encuentro: alcanza para coordinar sin pedir hora exacta.
- `fecha_propuesta` / `franja_propuesta`: lo que el negocio ofrece al reprogramar.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "servicios",
        sa.Column(
            "acepta_agendamiento",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.create_table(
        "citas_servicio",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "servicio_id", sa.BigInteger(),
            sa.ForeignKey("servicios.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "solicitante_usuario_id", sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("nombre_contacto", sa.String(length=120), nullable=False),
        sa.Column("telefono_contacto", sa.String(length=20), nullable=True),
        sa.Column("vehiculo", sa.String(length=120), nullable=True),
        sa.Column("motivo", sa.String(length=20), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("franja", sa.String(length=16), nullable=False),
        sa.Column("nota", sa.String(length=400), nullable=True),
        sa.Column(
            "estado", sa.String(length=16),
            server_default=sa.text("'solicitada'"), nullable=False,
        ),
        sa.Column("respuesta_negocio", sa.String(length=400), nullable=True),
        sa.Column("fecha_propuesta", sa.Date(), nullable=True),
        sa.Column("franja_propuesta", sa.String(length=16), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_citas_servicio_servicio_estado", "citas_servicio", ["servicio_id", "estado"]
    )
    op.create_index(
        "ix_citas_servicio_solicitante", "citas_servicio", ["solicitante_usuario_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_citas_servicio_solicitante", table_name="citas_servicio")
    op.drop_index("ix_citas_servicio_servicio_estado", table_name="citas_servicio")
    op.drop_table("citas_servicio")
    op.drop_column("servicios", "acepta_agendamiento")
