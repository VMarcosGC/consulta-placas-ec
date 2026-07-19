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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual, admin_actual
from src.modules.auth.models import Usuario
from src.modules.tokens.service import debitar_tokens, SaldoInsuficiente
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.marketplace.models import (
    EstadoModeracion,
    EstadoPublicacion,
    EstadoVerificacion,
    FichaPublicacion,
    PlanPublicacion,
    PublicacionInterna,
    PublicacionReferenciada,
)
from src.modules.marketplace.schemas import (
    FeedMarketplaceSalida,
    FichaActualizar,
    FichaSalida,
    PublicacionDetalleSalida,
    PublicacionInternaActualizar,
    PublicacionInternaCrear,
    PublicacionInternaSalida,
    PublicacionReferenciadaSalida,
    VerificacionPublicacion,
)


router = APIRouter(prefix="/marketplace", tags=["marketplace"])

# Tokens que cuesta destacar una publicación como premium. Configurable.
TOKENS_PUBLICACION_PREMIUM = int(os.getenv("TOKENS_PUBLICACION_PREMIUM", "3"))
# Tokens que cuesta SOLICITAR la verificación "Verificado por la plataforma" (revisión
# humana + validaciones). Separado del premium: destacar (3) ≠ verificar (100).
# Alineado con el producto `verificacion_marketplace` del catálogo (1 token ≈ USD 0.04).
TOKENS_VERIFICACION_MARKETPLACE = int(os.getenv("TOKENS_VERIFICACION_MARKETPLACE", "100"))

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
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
            selectinload(PublicacionInterna.ficha),
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
        # Premium compra el "destacado"; la verificación es un paso aparte que el dueño
        # SOLICITA con tokens (POST .../solicitar-verificacion). Nace no_verificado.
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
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
                selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
                selectinload(PublicacionInterna.ficha),
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
        # Premium = destacado. La verificación NO se activa aquí: el dueño la solicita
        # aparte con tokens. Bajar a light quita el destacado (y el sello deja de aplicar).
        pub.destacado = datos.plan == PlanPublicacion.PREMIUM

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


@router.post(
    "/publicaciones/{publicacion_id}/solicitar-verificacion",
    response_model=PublicacionInternaSalida,
)
def solicitar_verificacion(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El dueño SOLICITA el sello "Verificado por la plataforma" para su publicación.

    - Solo el dueño (404 si no es suya).
    - Solo premium (422 si es light: primero hay que destacarla).
    - Si ya está `pendiente` o `verificado` → idempotente (no recobra).
    - Cobra `TOKENS_VERIFICACION_MARKETPLACE`; **402** si no alcanza. Deja la publicación
      en `pendiente` → entra a la cola admin (`/admin/verificaciones`).
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)
    if pub.plan != PlanPublicacion.PREMIUM.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Primero haz tu publicación premium; luego puedes solicitar la verificación.",
        )
    if pub.estado_verificacion in (
        EstadoVerificacion.PENDIENTE.value,
        EstadoVerificacion.VERIFICADO.value,
    ):
        return PublicacionInternaSalida.desde_modelo(pub)  # idempotente: ya en cola o sellada

    try:
        debitar_tokens(
            sesion,
            usuario,
            TOKENS_VERIFICACION_MARKETPLACE,
            motivo=f"verificacion_marketplace:{pub.id}",
        )
        pub.estado_verificacion = EstadoVerificacion.PENDIENTE.value
        sesion.commit()
    except SaldoInsuficiente as e:
        sesion.rollback()
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e))

    return PublicacionInternaSalida.desde_modelo(_mi_publicacion(sesion, pub.id, usuario))


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
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
            selectinload(PublicacionInterna.ficha),
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
            .where(
                and_(
                    PublicacionReferenciada.activa.is_(True),
                    PublicacionReferenciada.estado_moderacion
                    == EstadoModeracion.APROBADA.value,
                )
            )
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


# ──────────────── Verificación premium (admin) ────────────────


def _cargar_publicacion(sesion: Session, publicacion_id: int) -> PublicacionInterna | None:
    """Carga una publicación por id con vehículo+mantenimientos (eager, sin scope de dueño)."""
    return sesion.execute(
        select(PublicacionInterna)
        .where(PublicacionInterna.id == publicacion_id)
        .options(
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
            selectinload(PublicacionInterna.ficha),
        )
    ).scalar_one_or_none()


@router.get(
    "/publicaciones/pendientes-verificacion",
    response_model=list[PublicacionInternaSalida],
)
def listar_pendientes_verificacion(
    sesion: Session = Depends(obtener_sesion),
    _: Usuario = Depends(admin_actual),
):
    """Cola de publicaciones premium por verificar (las más antiguas primero). Solo admin."""
    pubs = (
        sesion.execute(
            select(PublicacionInterna)
            .where(
                and_(
                    PublicacionInterna.plan == PlanPublicacion.PREMIUM.value,
                    PublicacionInterna.estado_verificacion
                    == EstadoVerificacion.PENDIENTE.value,
                )
            )
            .options(
                selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
                selectinload(PublicacionInterna.ficha),
            )
            .order_by(PublicacionInterna.creado_en.asc())
        )
        .scalars()
        .all()
    )
    return [PublicacionInternaSalida.desde_modelo(p) for p in pubs]


@router.post(
    "/publicaciones/{publicacion_id}/verificar",
    response_model=PublicacionInternaSalida,
)
def verificar_publicacion(
    publicacion_id: int,
    decision: VerificacionPublicacion,
    sesion: Session = Depends(obtener_sesion),
    _: Usuario = Depends(admin_actual),
):
    """Marca una publicación premium como **verificada** o **rechazada**. Solo admin.

    - 404 si no existe.
    - 422 si la publicación no es premium (las light no aplican a verificación).
    - `verificado` sella la publicación y registra `verificado_en` (auditoría).
    - `rechazado` quita el sello y limpia `verificado_en`.
    """
    pub = _cargar_publicacion(sesion, publicacion_id)
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )
    if pub.plan != PlanPublicacion.PREMIUM.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solo las publicaciones premium se verifican.",
        )

    pub.estado_verificacion = decision.decision.value
    pub.verificado_en = (
        datetime.now(timezone.utc)
        if decision.decision == EstadoVerificacion.VERIFICADO
        else None
    )
    sesion.commit()

    return PublicacionInternaSalida.desde_modelo(_cargar_publicacion(sesion, publicacion_id))


# ──────────────── Ficha técnica: 3 bloques + extras (market de autos) ────────────────


@router.patch("/publicaciones/{publicacion_id}/ficha", response_model=FichaSalida)
def actualizar_ficha(
    publicacion_id: int,
    datos: FichaActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El vendedor registra/edita la ficha técnica de su publicación (upsert).

    - Solo el dueño (404 si no es suya). Gratis: la transparencia no se cobra.
    - Solo se tocan los bloques ENVIADOS: cada uno reemplaza completo al anterior,
      `null` lo borra, omitirlo lo deja intacto. `extras` reemplaza la lista.
    - Se puede editar en cualquier estado (activa/pausada/vendida): pausar para
      completar la ficha es un flujo válido.
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)

    ficha = pub.ficha
    if ficha is None:
        ficha = FichaPublicacion(publicacion_id=pub.id, extras=[])
        sesion.add(ficha)

    enviados = datos.model_fields_set
    for bloque in ("motor_suspension", "carroceria", "interiores"):
        if bloque in enviados:
            valor = getattr(datos, bloque)
            # exclude_none: en el JSONB solo persisten los campos llenos; un campo
            # ausente significa "no informado" (así se calcula la completitud).
            setattr(ficha, bloque, valor.model_dump(exclude_none=True) if valor else None)
    if "extras" in enviados:
        ficha.extras = [e.model_dump(exclude_none=True) for e in (datos.extras or [])]

    sesion.commit()
    sesion.refresh(ficha)
    return FichaSalida.desde_modelo(ficha)


# NOTA de orden: esta ruta con path param dinámico va AL FINAL del router. Si se
# declarara antes que las literales (`/publicaciones/mias`,
# `/publicaciones/pendientes-verificacion`), "mias" intentaría parsearse como int
# y la ruta literal quedaría inalcanzable (422). No mover hacia arriba.
@router.get("/publicaciones/{publicacion_id}", response_model=PublicacionDetalleSalida)
def detalle_publicacion(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
):
    """Detalle público de una publicación activa: datos del feed + ficha técnica.

    Anónimo (el comprador no necesita cuenta para revisar el auto). Solo `activa`;
    pausada/vendida/inexistente → 404 indistinto. Sin PII: la ficha no lleva datos
    del dueño y las características derivadas nunca incluyen VIN (§10.6).
    """
    pub = sesion.execute(
        select(PublicacionInterna)
        .where(
            and_(
                PublicacionInterna.id == publicacion_id,
                PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value,
            )
        )
        .options(
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
            selectinload(PublicacionInterna.ficha),
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )
    return PublicacionDetalleSalida.desde_modelo(pub)
