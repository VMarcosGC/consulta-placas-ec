"""Servicio transaccional de la billetera de tokens (Fase 3 — débito real).

Reglas de negocio 10.3:
- El saldo nunca puede ser negativo (>= 0).
- Toda alteración del saldo genera un registro obligatorio en `transacciones_tokens`.

Este servicio NO hace commit: el caller controla la transacción para que el débito
y la operación que lo motiva (ej. crear un enlace de compra-venta) se persistan de
forma atómica. Si algo falla después del débito, el rollback del caller revierte ambos.
"""

from sqlalchemy.orm import Session

from models import Usuario, TransaccionToken


class SaldoInsuficiente(Exception):
    """El usuario no tiene tokens suficientes para la operación.

    El endpoint la traduce a HTTP 422 (validación de negocio, igual que el
    kilometraje no monotónico), no a un 500.
    """

    def __init__(self, saldo: int, requerido: int):
        self.saldo = saldo
        self.requerido = requerido
        super().__init__(
            f"Saldo insuficiente: tienes {saldo} token(s) y la operación "
            f"requiere {requerido}"
        )


def debitar_tokens(sesion: Session, usuario: Usuario, monto: int, motivo: str) -> None:
    """Resta `monto` tokens al usuario y registra la auditoría, sin commitear.

    - `monto <= 0` → no-op: operación gratuita, no genera transacción.
    - Saldo insuficiente → lanza `SaldoInsuficiente` sin mutar nada.
    - Caso normal → decrementa el saldo y agrega una `TransaccionToken` negativa.

    El caller DEBE hacer `sesion.commit()` para persistir débito + auditoría juntos.
    """
    if monto <= 0:
        return

    if usuario.saldo_tokens < monto:
        raise SaldoInsuficiente(usuario.saldo_tokens, monto)

    usuario.saldo_tokens -= monto
    sesion.add(
        TransaccionToken(usuario_id=usuario.id, monto=-monto, motivo=motivo)
    )
