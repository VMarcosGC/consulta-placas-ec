"""Publicaciones del marketplace: CRUD del usuario + feed público mixto (Pilar 4).

Dos entidades (ver models.py): `PublicacionInterna` (la publica un usuario sobre su
placa, plan light/premium) y `PublicacionReferenciada` (anuncios raspados de portales
externos). El feed público las mezcla en tres niveles: premium destacados arriba, luego
light, y referenciados al pie.

Cobro: publicar/ascender a **premium** debita `TOKENS_PUBLICACION_PREMIUM` tokens. Si el
saldo no alcanza → **402 Payment Required** (excepción acordada al contrato 422 de §10.2,
por ser un flujo de pago, igual que el desbloqueo de perfil). Solo toca la BD propia
(nunca invoca scraping, §10.2).
"""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import Usuario
from src.modules.tokens.service import debitar_tokens, SaldoInsuficiente
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.marketplace.models import (
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
    PublicacionReferenciada,
)
from src.modules.marketplace.schemas import (
    FeedMarketplaceSalida,
    PublicacionInternaActualizar,
    PublicacionInternaCrear,
    PublicacionInternaSalida,
    PublicacionReferenciadaSalida,
)


router = APIRouter(prefix="/marketplace", tags=["marketplace"])

# Tokens que cuesta una publicación premium (destacada + verificable). Configurable.
TOKENS_PUBLICACION_PREMIUM = int(os.getenv("TOKENS_PUBLICACION_PREMIUM", "3"))

# Cuántos anuncios referenciados se traen al feed (para no inflar la respuesta).
LIMITE_REFERENCIADAS_FEED = 30


def _cobrar_premium(sesion: Session, usuario: Usuario, placa: str) -> None:
    """Debita el costo premium y commitea; traduce saldo insuficiente a 402."""
    try:
        debitar_tokens(
            sesion,
            usuario,
            TOKENS_PUBLICACION_PREMIUM,
            motivo=f"publicacion_premium:{placa}",
        )
        sesion.commit()
    except SaldoInsuficiente as e:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)
        )


def _vehiculo_del_usuario(sesion: Session, vehiculo_id: int, usuario: Usuario) -> Vehiculo:
    """Resuelve un vehículo del usuario o lanza 404 (no distingue ajeno de inexistente)."""
    veh = sesion.execute(
        select(Vehiculo).where(
            and_(
                Vehiculo.id == vehiculo_id,
                Vehiculo.usuario_id == usuario.id,
                Vehiculo.eliminado_en.is_(None),
            )
        )
    ).scalar_one_or_none()
    if veh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no encontrado en tu garage",
        )
    return veh


def _mi_publicacion(sesion: Session, publicacion_id: int, usuario: Usuario) -> PublicacionInterna:
    """Resuelve una publicación del usuario (con vehículo+mantenimientos) o 404."""
    pub = sesion.execute(
        select(PublicacionInterna)
        .where(
            and_(
                PublicacionInterna.id == publicacion_id,
                PublicacionInterna.usuario_id == usuario.id,
            )
        )
        .options(
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos)
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )
    return pub


@router.post(
    "/publicaciones",
    response_model=PublicacionInternaSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_publicacion(
    datos: PublicacionInternaCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Publica un vehículo. Plan premium se cobra con tokens (402 si no alcanza).

    Premium queda `destacado` y con verificación `pendiente` (la verificación real
    "Verificado por la plataforma" es un paso administrativo aparte, fuera de alcance).
    """
    # Validar propiedad del vehículo vinculado (si se envió).
    if datos.vehiculo_id is not None:
        _vehiculo_del_usuario(sesion, datos.vehiculo_id, usuario)

    es_premium = datos.plan == PlanPublicacion.PREMIUM

    pub = PublicacionInterna(
        usuario_id=usuario.id,
        vehiculo_id=datos.vehiculo_id,
        placa=datos.placa,
        titulo=datos.titulo,
        descripcion=datos.descripcion,
        precio_usd=datos.precio_usd,
        plan=datos.plan.value,
        estado=EstadoPublicacion.ACTIVA.value,
        estado_verificacion=(
            EstadoVerificacion.PENDIENTE.value
            if es_premium
            else EstadoVerificacion.NO_VERIFICADO.value
        ),
        destacado=es_premium,
    )
    sesion.add(pub)
    sesion.flush()  # asigna id sin cerrar la transacción (el cobro va junto)

    if es_premium:
        _cobrar_premium(sesion, usuario, datos.placa)
    else:
        sesion.commit()

    # Recargar con vehículo+mantenimientos para derivar la salida premium.
    return PublicacionInternaSalida.desde_modelo(_mi_publicacion(sesion, pub.id, usuario))


@router.get("/publicaciones/mias", response_model=list[PublicacionInternaSalida])
def listar_mis_publicaciones(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Publicaciones del usuario (cualquier estado), de la más reciente a la más antigua."""
    pubs = (
        sesion.execute(
            select(PublicacionInterna)
            .where(PublicacionInterna.usuario_id == usuario.id)
            .options(
                selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos)
            )
            .order_by(PublicacionInterna.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return [PublicacionInternaSalida.desde_modelo(p) for p in pubs]


@router.patch("/publicaciones/{publicacion_id}", response_model=PublicacionInternaSalida)
def actualizar_publicacion(
    publicacion_id: int,
    datos: PublicacionInternaActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Edita precio/descripción/estado o asciende a premium (cobra tokens).

    Bajar de premium a light no reembolsa y quita el destacado. Subir a premium cobra
    `TOKENS_PUBLICACION_PREMIUM` (402 si no alcanza).
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)

    if datos.titulo is not None:
        pub.titulo = datos.titulo
    if datos.descripcion is not None:
        pub.descripcion = datos.descripcion
    if datos.precio_usd is not None:
        pub.precio_usd = datos.precio_usd
    if datos.estado is not None:
        pub.estado = datos.estado.value

    asciende_a_premium = (
        datos.plan == PlanPublicacion.PREMIUM
        and pub.plan != PlanPublicacion.PREMIUM.value
    )
    if datos.plan is not None:
        pub.plan = datos.plan.value
        if datos.plan == PlanPublicacion.PREMIUM:
            pub.destacado = True
            if pub.estado_verificacion == EstadoVerificacion.NO_VERIFICADO.value:
                pub.estado_verificacion = EstadoVerificacion.PENDIENTE.value
        else:  # baja a light
            pub.destacado = False

    if asciende_a_premium:
        _cobrar_premium(sesion, usuario, pub.placa)
    else:
        sesion.commit()

    return PublicacionInternaSalida.desde_modelo(_mi_publicacion(sesion, pub.id, usuario))


@router.delete("/publicaciones/{publicacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_publicacion(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    pub = _mi_publicacion(sesion, publicacion_id, usuario)
    sesion.delete(pub)
    sesion.commit()
    return None


@router.get("/feed", response_model=FeedMarketplaceSalida)
def feed_marketplace(sesion: Session = Depends(obtener_sesion)):
    """Feed público mixto: premium destacados arriba, luego light, y referenciados al pie.

    Solo lista publicaciones internas `activa`. Eager-load del vehículo+mantenimientos
    (selectinload) para derivar los argumentos premium sin N+1.
    """
    activas = (
        select(PublicacionInterna)
        .where(PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value)
        .options(
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos)
        )
        .order_by(PublicacionInterna.creado_en.desc())
    )
    internas = sesion.execute(activas).scalars().all()

    premium = [
        PublicacionInternaSalida.desde_modelo(p)
        for p in internas
        if p.plan == PlanPublicacion.PREMIUM.value
    ]
    estandar = [
        PublicacionInternaSalida.desde_modelo(p)
        for p in internas
        if p.plan != PlanPublicacion.PREMIUM.value
    ]

    referenciadas = (
        sesion.execute(
            select(PublicacionReferenciada)
            .where(PublicacionReferenciada.activa.is_(True))
            .order_by(PublicacionReferenciada.creado_en.desc())
            .limit(LIMITE_REFERENCIADAS_FEED)
        )
        .scalars()
        .all()
    )

    return FeedMarketplaceSalida(
        premium=premium,
        estandar=estandar,
        referenciadas=[PublicacionReferenciadaSalida.model_validate(r) for r in referenciadas],
    )
