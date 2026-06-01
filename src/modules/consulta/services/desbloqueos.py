"""Lógica de microdesbloqueos v2: catálogo en BD + registro de desbloqueos.

Reglas (docs/producto/reglas_monetizacion_tokens.md):
- Idempotente: un producto ya desbloqueado para (usuario, placa) NO se recobra.
- Atómico: débito de tokens + filas de `desbloqueos_consulta` se commitean juntos.
- Saldo insuficiente → `SaldoInsuficiente` (el router la traduce a HTTP 402).
- Producto inactivo o inexistente → el router responde 422/400 (no se desbloquea).
- La disponibilidad del dato la decide el consolidador (qué productos tienen datos); el
  router solo cobra si el producto está disponible para esa placa.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.auth.models import Usuario
from src.modules.consulta.models.desbloqueos import DesbloqueoConsulta, ProductoConsulta
from src.modules.consulta.services.catalogo_productos import BUNDLE_INCLUYE, SEED_PRODUCTOS
from src.modules.tokens.service import debitar_tokens


def inicializar_catalogo(sesion: Session) -> int:
    """Siembra el catálogo base de forma IDEMPOTENTE (no duplica). Devuelve cuántos creó.

    Inserta solo los códigos que falten (la migración 0015 ya siembra; esto es la red de
    seguridad para entornos nuevos o si se agrega un producto al seed)."""
    existentes = set(sesion.execute(select(ProductoConsulta.codigo)).scalars().all())
    creados = 0
    for p in SEED_PRODUCTOS:
        if p["codigo"] in existentes:
            continue
        sesion.add(
            ProductoConsulta(
                codigo=p["codigo"],
                nombre=p["nombre"],
                descripcion=p["descripcion"],
                tokens=p["tokens"],
                precio_referencial_usd=Decimal(p["precio_referencial_usd"]),
                sensibilidad=p["sensibilidad"],
                orden=p["orden"],
            )
        )
        creados += 1
    if creados:
        sesion.commit()
    return creados


def catalogo_activo(sesion: Session) -> list[ProductoConsulta]:
    """Productos activos del catálogo, ordenados para presentación."""
    return list(
        sesion.execute(
            select(ProductoConsulta)
            .where(ProductoConsulta.activo.is_(True))
            .order_by(ProductoConsulta.orden.asc(), ProductoConsulta.id.asc())
        ).scalars().all()
    )


def obtener_producto(sesion: Session, codigo: str) -> ProductoConsulta | None:
    """Producto del catálogo por código (cualquier estado), o None si no existe."""
    return sesion.execute(
        select(ProductoConsulta).where(ProductoConsulta.codigo == codigo)
    ).scalar_one_or_none()


def productos_desbloqueados(sesion: Session, usuario_id: int, placa: str) -> set[str]:
    """Conjunto de códigos que el usuario ya desbloqueó para esa placa."""
    filas = sesion.execute(
        select(DesbloqueoConsulta.producto_codigo).where(
            DesbloqueoConsulta.usuario_id == usuario_id,
            DesbloqueoConsulta.placa == placa,
        )
    ).scalars().all()
    return set(filas)


def listar_desbloqueos(sesion: Session, usuario_id: int, placa: str) -> list[DesbloqueoConsulta]:
    """Desbloqueos del usuario para esa placa, del más reciente al más antiguo."""
    return list(
        sesion.execute(
            select(DesbloqueoConsulta)
            .where(
                DesbloqueoConsulta.usuario_id == usuario_id,
                DesbloqueoConsulta.placa == placa,
            )
            .order_by(DesbloqueoConsulta.creado_en.desc())
        ).scalars().all()
    )


def desbloquear(
    sesion: Session,
    usuario: Usuario,
    placa: str,
    producto: ProductoConsulta,
    *,
    resultado_cache_id: int | None = None,
    proveedor_usado: str | None = None,
    costo_estimado: Decimal | None = None,
) -> bool:
    """Desbloquea `producto` para (usuario, placa). True si cobró, False si ya estaba
    desbloqueado (idempotente, sin recobro).

    Cobra `producto.tokens` y registra una fila por el producto y por cada código incluido
    (bundle) que falte. Lanza `SaldoInsuficiente` si no alcanza (sin mutar nada). Commitea
    al final (débito + filas juntos)."""
    ya = productos_desbloqueados(sesion, usuario.id, placa)
    if producto.codigo in ya:
        return False

    debitar_tokens(
        sesion, usuario, producto.tokens, motivo=f"desbloqueo:{producto.codigo}:{placa}"
    )

    codigos = {producto.codigo} | set(BUNDLE_INCLUYE.get(producto.codigo, ()))
    for codigo in codigos:
        if codigo in ya:
            continue
        es_principal = codigo == producto.codigo
        sesion.add(
            DesbloqueoConsulta(
                usuario_id=usuario.id,
                placa=placa,
                producto_codigo=codigo,
                tokens_cobrados=producto.tokens if es_principal else 0,
                precio_referencial_usd=producto.precio_referencial_usd if es_principal else None,
                proveedor_usado=proveedor_usado if es_principal else None,
                costo_estimado_usd=costo_estimado if es_principal else None,
                resultado_cache_id=resultado_cache_id if es_principal else None,
            )
        )
    sesion.commit()
    return True
