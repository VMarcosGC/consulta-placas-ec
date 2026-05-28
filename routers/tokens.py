"""Endpoints de la billetera de tokens del usuario autenticado.

Solo lectura: consultar el saldo y el historial de transacciones. El saldo no se
altera desde aquí — los créditos/débitos los origina una función de pago (fase
posterior) que llamará a la operación de dominio correspondiente y auditará cada
movimiento en `transacciones_tokens`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import obtener_sesion
from models import Usuario, TransaccionToken
from schemas.auth import SaldoTokens, TransaccionTokenSalida
from auth.dependencies import usuario_actual


router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("/saldo", response_model=SaldoTokens)
def consultar_saldo(usuario: Usuario = Depends(usuario_actual)):
    return SaldoTokens(saldo_tokens=usuario.saldo_tokens)


@router.get("/transacciones", response_model=list[TransaccionTokenSalida])
def listar_transacciones(
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
):
    """Historial de movimientos de la billetera, del más reciente al más antiguo."""
    transacciones = (
        sesion.execute(
            select(TransaccionToken)
            .where(TransaccionToken.usuario_id == usuario.id)
            .order_by(TransaccionToken.fecha.desc())
        )
        .scalars()
        .all()
    )
    return transacciones
