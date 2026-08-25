"""login con Google (sin contraseña) — columnas de identidad en `usuarios`

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-25

El público objetivo navega desde Android de gama baja y ya tiene sesión de Google en el
teléfono: pedirle que invente y recuerde una contraseña es la fricción más cara del
onboarding. Un usuario que entra con Google **nunca crea una contraseña**, y de ahí sale
todo lo que hace esta migración.

Cambios:

1. **`password_hash` pasa a NULL.** Una cuenta creada por Google no tiene contraseña.
   Rellenarla con un hash placeholder sería peor que dejarla vacía: convertiría "no
   puede entrar por contraseña" en "puede entrar quien adivine el placeholder".
   `/auth/login` trata el NULL como credencial inválida (401, mensaje genérico) para que
   no sea un 500 por una condición de negocio esperable.

2. **`proveedor_autenticacion`** String(16) NOT NULL default `'local'`, con CHECK
   `IN ('local','google')`. Guarda con qué proveedor se **creó** la cuenta: es para copy
   y métricas, **no** una exclusividad. Quién puede entrar por dónde lo dicen las
   columnas de hecho (`password_hash IS NOT NULL` / `id_google IS NOT NULL`), y una
   cuenta puede tener las dos: un usuario local que después vincula Google conserva su
   contraseña. Si esto fuera una bandera exclusiva, vincular se la apagaría en silencio.

3. **`id_google`** String(255) NULL con **índice ÚNICO** `ix_usuarios_id_google`. Guarda
   el claim `sub` del ID token — el identificador estable de la cuenta de Google, que no
   cambia aunque el usuario cambie su correo. El índice único es la barrera contra el
   secuestro: impide que dos cuentas de la plataforma cuelguen del mismo Google. Postgres
   permite múltiples NULL bajo un índice único, así que las cuentas locales conviven sin
   tocarse.

4. **`email_verificado`** Boolean NOT NULL default `false`. **Sin backfill, a propósito:**
   nunca verificamos el correo de los usuarios locales y afirmar lo contrario sería
   inventar un hecho. Solo pasa a `true` cuando Google lo afirma.

Las columnas NOT NULL entran con `server_default`, que rellena las filas existentes sin
un UPDATE aparte. Después del upgrade, ninguna cuenta preexistente cambia de significado:
todas quedan `proveedor_autenticacion = 'local'`, `id_google = NULL` y
`email_verificado = false`.

Migración manual y revisada a mano (§10.2). No se usó `--autogenerate`.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "usuarios",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.add_column(
        "usuarios",
        sa.Column(
            "proveedor_autenticacion",
            sa.String(length=16),
            server_default="local",
            nullable=False,
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column("id_google", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "email_verificado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.create_check_constraint(
        "ck_usuarios_proveedor_autenticacion",
        "usuarios",
        "proveedor_autenticacion IN ('local', 'google')",
    )
    # ÚNICO: dos cuentas de la plataforma no pueden colgar del mismo Google.
    op.create_index(
        "ix_usuarios_id_google", "usuarios", ["id_google"], unique=True
    )


def downgrade() -> None:
    # Volver `password_hash` a NOT NULL con usuarios de Google vivos falla con un error
    # de Postgres ilegible, y la "solución" tentadora —rellenar con un hash placeholder—
    # es exactamente lo que esta migración prohíbe. Que se detenga y lo diga.
    #
    # El chequeo va tras `is_offline_mode()` porque en modo `--sql` no hay conexión que
    # consultar: alembic solo emite el SQL, y la comprobación tiene que hacerla quien lo
    # aplique.
    if not context.is_offline_mode():
        pendientes = (
            op.get_bind()
            .execute(sa.text("SELECT count(*) FROM usuarios WHERE password_hash IS NULL"))
            .scalar_one()
        )
        if pendientes:
            raise RuntimeError(
                f"No se puede revertir la 0025: hay {pendientes} usuario(s) sin "
                "password_hash (cuentas creadas con Google). Volver la columna a NOT "
                "NULL fallaría. Decide qué hacer con esas cuentas —darles una "
                "contraseña real o eliminarlas— antes de bajar esta migración. NO las "
                "rellenes con un hash placeholder: eso convierte 'no puede entrar por "
                "contraseña' en 'puede entrar quien lo adivine'."
            )

    op.drop_index("ix_usuarios_id_google", table_name="usuarios")
    op.drop_constraint(
        "ck_usuarios_proveedor_autenticacion", "usuarios", type_="check"
    )
    op.drop_column("usuarios", "email_verificado")
    op.drop_column("usuarios", "id_google")
    op.drop_column("usuarios", "proveedor_autenticacion")
    op.alter_column(
        "usuarios",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
