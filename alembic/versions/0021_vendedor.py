"""capa Vendedor entre la cuenta y sus publicaciones (TASK-001)

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-04

Etapa 1 del marketplace (AGENTS §1.0.4): se inserta una capa `vendedores` entre
`usuarios` y sus publicaciones. Hoy la relación es 1:1 con la cuenta (lo impone la UK
sobre `usuario_id`) y el único `tipo` usado es `particular`; la etapa 2 (patios) solo
tendrá que levantar esa UK y empezar a usar `patio` — un cambio aditivo.

Se hace AHORA porque en producción hay 2 publicaciones internas y 3 referenciadas: el
backfill es trivial. Hacerlo cuando existan patios implicaría migrar cuatro tablas con
datos reales.

Qué crea:
- Tabla `vendedores` (UK `usuario_id`, FK ON DELETE CASCADE). `telefono` **nullable**:
  el vendedor lo carga cuando quiere; sin teléfono el endpoint de contacto responde 409,
  nunca 500. `nombre_publico` nullable igual que `usuarios.nombre` (NULL = no informado;
  no se inventa un valor).
- Columna `vendedor_id` en `publicaciones_internas` y `publicaciones_referenciadas`
  (nullable, FK ON DELETE SET NULL). **`usuario_id` se conserva en ambas**: en las
  internas es la cuenta dueña del registro (permisos) y en las referenciadas documenta al
  **aportante**, que no siempre es el vendedor. No se borra ninguna columna.

**Por qué `publicaciones_referenciadas.vendedor_id` queda NULL y NO se backfillea.**
La columna se crea, pero nada la puebla — ni esta migración ni el alta de referencias.
No es un olvido: en una referencia externa, `usuario_id` es el **aportante**, la persona
que copió un anuncio ajeno de Facebook o Mercado Libre. El vendedor real es un tercero
que no tiene cuenta aquí y del que no sabemos nada. Derivar un `Vendedor` desde el
aportante publicaría su nombre y su teléfono como si fuera quien vende ese auto, que es
falso y además expone PII de alguien que solo aportó un enlace. La columna queda lista
para la etapa 2, cuando exista una vía legítima de asociar un vendedor a una referencia.

Backfill (SQL plano, para que corra igual en modo `--sql` offline):
- Un `Vendedor` por cada usuario con publicaciones **internas**, con `nombre_publico` y
  `telefono` en **NULL**. Los aportantes de referencias no entran: no son vendedores, y
  crearles un perfil sería afirmar que venden algo.
- **Por qué `nombre_publico` queda NULL y no se copia de `usuarios.nombre`:** la regla
  vigente prohíbe tener teléfono publicado sin un `nombre_publico` elegido a mano
  (compuerta M5, se valida en el PATCH). Un backfill no debe dejar el estado en una
  configuración que la regla vigente prohíbe: copiar el nombre de la cuenta crearía filas
  con un nombre que su dueño nunca eligió, y al cargar el teléfono ese nombre heredado
  pasaría sin opt-in. Con NULL, el primer PATCH que publique un número obliga a elegirlo.
- `vendedor_id` poblado **solo** en `publicaciones_internas`.
- `ON CONFLICT DO NOTHING` + `WHERE vendedor_id IS NULL`: la migración es reentrante.
- Pre-flight verificado contra la BD real (2026-08-04): 0 publicaciones con `usuario_id`
  huérfano, así que el UPDATE no deja filas sin vendedor. Aun así el UPDATE es un JOIN,
  no un NOT NULL: un huérfano dejaría la fila en NULL, no rompería.
- El `telefono` NULL del backfill es intencional: nadie queda contactable sin haberlo
  pedido. Al cargarlo por `PATCH /marketplace/vendedor/mi-perfil` se exige además un
  `nombre_publico` explícito (compuerta M5).

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendedores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "tipo", sa.String(length=16), server_default="particular", nullable=False
        ),
        sa.Column("nombre_publico", sa.String(length=120), nullable=True),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column(
            "telefono_verificado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
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
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # UK = 1:1 cuenta ↔ vendedor en la etapa 1. Su índice implícito cubre las
        # búsquedas por usuario, así que no se crea un índice aparte.
        sa.UniqueConstraint("usuario_id", name="uq_vendedores_usuario_id"),
    )

    op.add_column(
        "publicaciones_internas",
        sa.Column("vendedor_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_publicaciones_internas_vendedor_id",
        "publicaciones_internas",
        "vendedores",
        ["vendedor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_publicaciones_internas_vendedor_id",
        "publicaciones_internas",
        ["vendedor_id"],
    )

    op.add_column(
        "publicaciones_referenciadas",
        sa.Column("vendedor_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_publicaciones_referenciadas_vendedor_id",
        "publicaciones_referenciadas",
        "vendedores",
        ["vendedor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_publicaciones_referenciadas_vendedor_id",
        "publicaciones_referenciadas",
        ["vendedor_id"],
    )

    # ── Backfill ──────────────────────────────────────────────────────────────
    # 1) Un vendedor `particular` por cada usuario con publicaciones INTERNAS. Los
    #    aportantes de referencias quedan fuera a propósito (ver docstring): aportar el
    #    enlace de un anuncio ajeno no te convierte en el vendedor de ese auto.
    #
    #    `nombre_publico` y `telefono` quedan NULL: nadie queda contactable ni con un
    #    nombre publicado que no eligió. El backfill no puede dejar filas en un estado
    #    que la regla de opt-in (compuerta M5) prohíbe crear por la API.
    op.execute(
        """
        INSERT INTO vendedores (usuario_id, tipo, telefono_verificado)
        SELECT u.id, 'particular', false
        FROM usuarios u
        WHERE u.id IN (SELECT usuario_id FROM publicaciones_internas)
        ON CONFLICT (usuario_id) DO NOTHING
        """
    )
    # 2) Enganchar las publicaciones internas existentes a su vendedor. De aquí en
    #    adelante el vínculo lo pone `crear_publicacion`, no un backfill.
    op.execute(
        """
        UPDATE publicaciones_internas p
        SET vendedor_id = v.id
        FROM vendedores v
        WHERE v.usuario_id = p.usuario_id
          AND p.vendedor_id IS NULL
        """
    )
    # `publicaciones_referenciadas.vendedor_id` NO se puebla: queda NULL a propósito.


def downgrade() -> None:
    # Simétrico: se sueltan primero las referencias y al final la tabla. El backfill no
    # necesita deshacerse porque las columnas que escribió desaparecen con este drop.
    op.drop_index(
        "ix_publicaciones_referenciadas_vendedor_id",
        table_name="publicaciones_referenciadas",
    )
    op.drop_constraint(
        "fk_publicaciones_referenciadas_vendedor_id",
        "publicaciones_referenciadas",
        type_="foreignkey",
    )
    op.drop_column("publicaciones_referenciadas", "vendedor_id")

    op.drop_index(
        "ix_publicaciones_internas_vendedor_id", table_name="publicaciones_internas"
    )
    op.drop_constraint(
        "fk_publicaciones_internas_vendedor_id",
        "publicaciones_internas",
        type_="foreignkey",
    )
    op.drop_column("publicaciones_internas", "vendedor_id")

    op.drop_table("vendedores")
