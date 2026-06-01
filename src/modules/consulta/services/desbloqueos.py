"""Lógica de microdesbloqueos: qué productos tiene un usuario para una placa y cómo
desbloquear uno nuevo cobrando tokens.

Reglas (docs/producto/reglas_monetizacion_tokens.md):
- Idempotente: un producto ya desbloqueado para (usuario, placa) NO se recobra.
- Atómico: débito + filas de `desbloqueos` se commitean juntos (el caller no commitea).
- Saldo insuficiente → `SaldoInsuficiente` (el router la traduce a HTTP 402).
- La **disponibilidad** del dato la valida el router (necesita los datos consolidados);
  este servicio no cobra a ciegas: el router solo llama a `desbloquear_producto` si hay dato.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.auth.models import Usuario
from src.modules.consulta.models.desbloqueo import Desbloqueo
from src.modules.consulta.services.catalogo_productos import CATALOGO_PRODUCTOS, ProductoConsulta
from src.modules.tokens.service import debitar_tokens


def productos_desbloqueados(sesion: Session, usuario_id: int, placa: str) -> set[str]:
    """Conjunto de códigos de producto que el usuario ya desbloqueó para esa placa."""
    filas = sesion.execute(
        select(Desbloqueo.producto).where(
            Desbloqueo.usuario_id == usuario_id,
            Desbloqueo.placa == placa,
        )
    ).scalars().all()
    return set(filas)


def desbloquear_producto(
    sesion: Session, usuario: Usuario, placa: str, producto: ProductoConsulta
) -> bool:
    """Desbloquea `producto` para (usuario, placa). Devuelve True si cobró, False si ya
    estaba desbloqueado (idempotente, sin recobro).

    Cobra los tokens del producto y persiste una fila por el producto y por cada código
    `incluye` (bundle) que no estuviera ya desbloqueado. Lanza `SaldoInsuficiente` si no
    alcanza el saldo (sin mutar nada). Commitea al final (débito + filas juntos).
    """
    ya = productos_desbloqueados(sesion, usuario.id, placa)
    if producto.codigo in ya:
        return False

    # Cobra una sola vez el precio del producto (el caller ya validó disponibilidad).
    debitar_tokens(
        sesion, usuario, producto.tokens, motivo=f"desbloqueo:{producto.codigo}:{placa}"
    )

    # Persiste el producto comprado + los incluidos (bundle) que falten. El precio se
    # imputa al producto comprado; los incluidos quedan con tokens_cobrados=0 (vienen "gratis").
    codigos = {producto.codigo} | set(producto.incluye)
    for codigo in codigos:
        if codigo in ya:
            continue
        sesion.add(
            Desbloqueo(
                usuario_id=usuario.id,
                placa=placa,
                producto=codigo,
                tokens_cobrados=producto.tokens if codigo == producto.codigo else 0,
            )
        )
    sesion.commit()
    return True


def estado_catalogo(desbloqueados: set[str], disponibles: set[str]) -> list[dict]:
    """Arma la lista de productos con su estado para el frontend.

    `desbloqueados`: códigos ya comprados por el usuario para la placa.
    `disponibles`: códigos cuyos datos SÍ se obtuvieron para esa placa (cobrables).
    """
    items = []
    for p in CATALOGO_PRODUCTOS.values():
        items.append(
            {
                "codigo": p.codigo,
                "nombre": p.nombre,
                "tokens": p.tokens,
                "sensibilidad": p.sensibilidad.value,
                "descripcion": p.descripcion,
                "desbloqueado": p.codigo in desbloqueados,
                "disponible": p.codigo in disponibles,
            }
        )
    return items
