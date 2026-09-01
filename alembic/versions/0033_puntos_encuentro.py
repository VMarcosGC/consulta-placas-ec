"""puntos de encuentro seguros + presencias de vehículos

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-30

Propuesta de producto (Marcos): puntos físicos, curados por la plataforma, donde
comprador y vendedor se encuentran para negociar cara a cara — empieza en Quito.
Un vendedor "anuncia" que va a llevar UNA de sus publicaciones a un punto en una
fecha/franja; el comprador ve, por punto, qué autos van a estar ahí. Deja lugar para
sumar seguridad privada o policial más adelante (`tiene_seguridad`, hoy en `false`
en todos: es un campo, no una promesa).

Tablas:
- `puntos_encuentro`: catálogo administrado (admin crea/edita; `POST/PATCH
  /marketplace/puntos-encuentro`). Se siembran 6 puntos de Quito (centros comerciales
  y terminales — alta afluencia y cámaras, NO una alianza oficial declarada).
- `presencias_punto`: quién anuncia qué auto en qué punto y cuándo. FK viva a
  `publicaciones_internas` (ON DELETE CASCADE): si se borra el anuncio, desaparece
  la presencia — no se guarda una foto aparte de marca/modelo/precio, se lee de la
  publicación al servir el detalle del punto (mismo criterio que el sello de
  mecánica: un solo lugar de verdad). UK evita el anuncio duplicado del mismo auto,
  mismo punto, mismo día.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PUNTOS_SEED = [
    dict(
        nombre="CC El Recreo — parqueadero norte",
        ciudad="Quito", sector="Sur",
        direccion="Av. Pedro Vicente Maldonado y Los Libertadores",
        referencia="Parqueadero exterior, junto al acceso norte del centro comercial",
        horario="Todos los días, horario del centro comercial (aprox. 09:00–21:00)",
        orden=1,
    ),
    dict(
        nombre="Quicentro Sur — parqueadero exterior",
        ciudad="Quito", sector="Sur",
        direccion="Av. Morán Valverde y Av. Rumichaca Ñan",
        referencia="Zona de parqueo exterior, frente al ingreso principal",
        horario="Todos los días, horario del centro comercial (aprox. 09:00–21:00)",
        orden=2,
    ),
    dict(
        nombre="CCI (Centro Comercial Iñaquito) — parqueadero",
        ciudad="Quito", sector="Norte",
        direccion="Av. Amazonas y Av. Naciones Unidas",
        referencia="Parqueadero exterior del centro comercial",
        horario="Todos los días, horario del centro comercial (aprox. 10:00–20:00)",
        orden=3,
    ),
    dict(
        nombre="Parque La Carolina — costado Av. Amazonas",
        ciudad="Quito", sector="Centro-Norte",
        direccion="Av. Amazonas y Av. Naciones Unidas (frente al parque)",
        referencia="Acera y parqueo público junto al parque, zona de alto tránsito peatonal",
        horario="Diurno, se sugiere antes de las 19:00",
        orden=4,
    ),
    dict(
        nombre="Terminal Terrestre Carcelén — parqueadero público",
        ciudad="Quito", sector="Norte",
        direccion="Av. Eloy Alfaro y Av. Diego de Vásquez",
        referencia="Parqueadero público del terminal",
        horario="Horario de atención del terminal",
        orden=5,
    ),
    dict(
        nombre="San Luis Shopping — parqueadero",
        ciudad="Quito", sector="Valle de los Chillos",
        direccion="Av. Ilaló, Sangolquí",
        referencia="Parqueadero exterior del centro comercial",
        horario="Todos los días, horario del centro comercial (aprox. 09:00–21:00)",
        orden=6,
    ),
]

_NOTA_SEGURIDAD = (
    "Punto sugerido por su afluencia y cámaras del sector — no es un convenio con "
    "seguridad privada ni con la Policía todavía. Revisa el vehículo y los "
    "documentos en persona antes de pagar; evita transferencias antes de ver el "
    "auto. Si puedes, coordina la cita en horario diurno y avisa a alguien de "
    "confianza a dónde vas."
)


def upgrade() -> None:
    op.create_table(
        "puntos_encuentro",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("ciudad", sa.String(length=80), nullable=False, server_default="Quito"),
        sa.Column("sector", sa.String(length=120), nullable=True),
        sa.Column("direccion", sa.String(length=200), nullable=False),
        sa.Column("referencia", sa.String(length=300), nullable=True),
        sa.Column("latitud", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitud", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("horario", sa.String(length=120), nullable=True),
        sa.Column(
            "tiene_seguridad", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("orden", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_puntos_encuentro_activo", "puntos_encuentro", ["activo"])

    op.create_table(
        "presencias_punto",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "punto_id", sa.BigInteger(),
            sa.ForeignKey("puntos_encuentro.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publicacion_interna_id", sa.BigInteger(),
            sa.ForeignKey("publicaciones_internas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id", sa.BigInteger(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("franja", sa.String(length=16), nullable=False),
        sa.Column(
            "estado", sa.String(length=16), server_default="anunciada", nullable=False
        ),
        sa.Column("nota", sa.String(length=300), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "punto_id", "publicacion_interna_id", "fecha",
            name="uq_presencia_punto_publicacion_fecha",
        ),
    )
    op.create_index("ix_presencias_punto_punto_id", "presencias_punto", ["punto_id"])
    op.create_index("ix_presencias_punto_usuario_id", "presencias_punto", ["usuario_id"])
    op.create_index(
        "ix_presencias_punto_publicacion_id", "presencias_punto", ["publicacion_interna_id"]
    )

    puntos_tabla = sa.table(
        "puntos_encuentro",
        sa.column("nombre", sa.String),
        sa.column("ciudad", sa.String),
        sa.column("sector", sa.String),
        sa.column("direccion", sa.String),
        sa.column("referencia", sa.String),
        sa.column("horario", sa.String),
        sa.column("notas", sa.String),
        sa.column("orden", sa.Integer),
    )
    op.bulk_insert(
        puntos_tabla,
        [{**p, "notas": _NOTA_SEGURIDAD} for p in _PUNTOS_SEED],
    )


def downgrade() -> None:
    op.drop_index("ix_presencias_punto_publicacion_id", table_name="presencias_punto")
    op.drop_index("ix_presencias_punto_usuario_id", table_name="presencias_punto")
    op.drop_index("ix_presencias_punto_punto_id", table_name="presencias_punto")
    op.drop_table("presencias_punto")
    op.drop_index("ix_puntos_encuentro_activo", table_name="puntos_encuentro")
    op.drop_table("puntos_encuentro")
