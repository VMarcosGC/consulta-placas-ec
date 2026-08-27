"""Publicaciones del marketplace: CRUD del usuario + feed público mixto (Pilar 4).

Dos entidades (ver models.py): `PublicacionInterna` (la publica un usuario sobre su
placa, plan light/premium) y `PublicacionReferenciada` (anuncios raspados de portales
externos). El feed público las mezcla en tres niveles: premium destacados arriba, luego
light, y referenciados al pie.

**Monetización suspendida (§1.0.3): TODO el flujo del market es gratis.** `premium` hoy
es solo "destacado" y elegible para el sello de verificación; no cuesta nada. Los costos
en tokens quedan como constantes en **0** (env-overridables) para reactivar el cobro sin
tocar la lógica: el débito sigue cableado y atómico, `debitar_tokens(0)` es un no-op.
Dónde y cuánto se cobra se decide cuando el producto esté operando con usuarios reales.
Solo toca la BD propia (nunca invoca scraping, §10.2).
"""

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, or_, cast, func, literal, union_all, Integer
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import (
    usuario_actual,
    usuario_actual_opcional,
    admin_actual,
)
from src.modules.auth.models import Usuario
from src.modules.tokens.service import debitar_tokens, SaldoInsuficiente
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.marketplace.models import (
    ContactoRevelado,
    EstadoModeracion,
    EstadoPublicacion,
    EstadoVerificacion,
    FichaPublicacion,
    FotoPublicacion,
    PlanPublicacion,
    PublicacionInterna,
    PublicacionReferenciada,
    Vendedor,
)
from src.modules.marketplace.routers.vendedor import obtener_o_crear_vendedor
from src.modules.marketplace import geografia
from src.modules.marketplace.schemas import (
    armar_whatsapp_url,
    Combustible,
    ContactoVendedorSalida,
    DistribucionGeograficaSalida,
    FeedMarketplaceSalida,
    FichaActualizar,
    FichaSalida,
    calcular_completitud_ficha,
    FirmaSubidaSalida,
    FotoRegistrar,
    FotoReordenar,
    FotoSalida,
    ItemBusqueda,
    ProvinciaDistribucionSalida,
    PublicacionDetalleSalida,
    PublicacionInternaActualizar,
    PublicacionInternaCrear,
    PublicacionInternaSalida,
    PublicacionReferenciadaSalida,
    RegionDistribucionSalida,
    ResultadoBusquedaSalida,
    SEMANAS_VIGENCIA_PUBLICACION,
    TipoCarroceria,
    Transmision,
    VerificacionPublicacion,
    semanas_desde_publicacion,
)
from src.modules.marketplace.services import cloudinary


router = APIRouter(prefix="/marketplace", tags=["marketplace"])

# Costo en tokens de destacar una publicación como premium.
# Monetización suspendida (§1.0.3) → 0. La constante y el débito quedan cableados: subir
# este valor (o el env var) reactiva el cobro sin más cambios.
TOKENS_PUBLICACION_PREMIUM = int(os.getenv("TOKENS_PUBLICACION_PREMIUM", "0"))
# Costo en tokens de SOLICITAR la verificación "Verificado por la plataforma" (revisión
# humana + validaciones). Monetización suspendida (§1.0.3) → 0. Mismo criterio que arriba.
TOKENS_VERIFICACION_MARKETPLACE = int(os.getenv("TOKENS_VERIFICACION_MARKETPLACE", "0"))

# Cuántos anuncios referenciados se traen al feed (para no inflar la respuesta).
LIMITE_REFERENCIADAS_FEED = 30

# Máximo de fotos por publicación (M2). Superarlo → 409.
MAX_FOTOS_POR_PUBLICACION = 12

# Completitud mínima de la ficha para ACTIVAR una publicación (M2.8). Un anuncio con la
# ficha casi vacía no aporta al comprador y ensucia el feed; el borrador deja armarlo con
# calma sin bloquear a nadie. Configurable por si el umbral resulta muy alto o muy bajo.
UMBRAL_FICHA_PUBLICACION = int(os.getenv("UMBRAL_FICHA_PUBLICACION", "30"))


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


def _completitud_ficha(pub: PublicacionInterna) -> int:
    """% de completitud de la ficha de la publicación (0 si todavía no tiene ficha)."""
    if pub.ficha is None:
        return 0
    return calcular_completitud_ficha(
        pub.ficha.motor_suspension, pub.ficha.carroceria, pub.ficha.interiores
    )


def _exigir_umbral_ficha(pub: PublicacionInterna) -> None:
    """422 si la ficha no llega al umbral para publicar (M2.8).

    Es validación de negocio, no de formato: el borrador existe justamente para que el
    vendedor complete antes de exponerse al comprador. Copy es-EC, accionable.
    """
    pct = _completitud_ficha(pub)
    if pct < UMBRAL_FICHA_PUBLICACION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Completa al menos el {UMBRAL_FICHA_PUBLICACION}% de la ficha para "
                f"publicar. Vas en {pct}%."
            ),
        )


def _aplicar_transicion_estado(
    pub: PublicacionInterna, nuevo: EstadoPublicacion
) -> None:
    """Valida y aplica un cambio de estado (M2.8). 422 si la transición no es legal.

    Máquina de estados explícita, porque los atajos costaban caro:
    - Desde `borrador` **solo** se sale a `activa`, y validando el umbral de ficha. Si se
      permitiera `borrador → pausada → activa`, el anuncio llegaba al feed **sin pasar por
      el umbral ni por el cobro** del premium.
    - A `borrador` no se vuelve nunca: para ocultar un anuncio está `pausada`.
    El resto de transiciones (activa/pausada/vendida entre sí) siguen siendo libres.
    """
    actual = pub.estado
    if nuevo == EstadoPublicacion.BORRADOR and actual != EstadoPublicacion.BORRADOR.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No puedes devolver un anuncio publicado a borrador. "
                "Si quieres ocultarlo, pásalo a pausada."
            ),
        )
    if actual == EstadoPublicacion.BORRADOR.value:
        if nuevo != EstadoPublicacion.ACTIVA:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Un borrador solo puede pasar a publicado. "
                    "Publícalo primero y después podrás pausarlo o marcarlo como vendido."
                ),
            )
        _exigir_umbral_ficha(pub)

    pub.estado = nuevo.value


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
            selectinload(PublicacionInterna.fotos),
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
    """Crea la publicación como **BORRADOR** (M2.8).

    El borrador solo lo ve su dueño: no sale en el feed ni por la URL pública (404). El
    vendedor arma la ficha y las fotos con calma y luego lo publica con
    `PATCH .../{id}` enviando `estado: activa`, que valida el umbral de ficha.

    Monetización suspendida (§1.0.3): premium no cuesta nada. El punto de cobro (la
    activación) queda cableado en `actualizar_publicacion` para cuando se reactive.
    """
    # Validar propiedad del vehículo vinculado (si se envió).
    if datos.vehiculo_id is not None:
        _vehiculo_del_usuario(sesion, datos.vehiculo_id, usuario)

    es_premium = datos.plan == PlanPublicacion.PREMIUM

    # Identidad comercial que vende (TASK-001). Se resuelve o se crea ANTES de armar la
    # publicación para que `vendedor_id` quede poblado desde la primera fila: si el alta
    # no lo enganchara, toda publicación nueva nacería con el vínculo en NULL y la
    # invariante se degradaría con cada anuncio. Va antes de agregar `pub` a la sesión
    # porque ante una carrera hace rollback (ver su precondición).
    vendedor = obtener_o_crear_vendedor(sesion, usuario)

    pub = PublicacionInterna(
        usuario_id=usuario.id,
        vendedor_id=vendedor.id,
        vehiculo_id=datos.vehiculo_id,
        placa=datos.placa,
        titulo=datos.titulo,
        descripcion=datos.descripcion,
        # Ciudad donde está el auto en venta: se toma TAL CUAL del cliente. Aunque haya
        # `vehiculo_id` vinculado, no se cae a `vehiculo.ciudad_registro`: eso es dónde se
        # matriculó, no dónde se vende. El prellenado del formulario (para que el vendedor
        # confirme) lo hace el frontend, que ya recibe `ciudad_registro` en VehiculoSalida.
        ciudad=datos.ciudad,
        # Recorrido declarado: igual que la ciudad, se toma TAL CUAL del cliente. Aunque
        # haya `vehiculo_id` vinculado, no se cae a la última lectura del garage: ese
        # dato es privado y opt-in por scope (§9), y además es el odómetro de un momento
        # cualquiera, no el que el vendedor publica. El prellenado (para que lo confirme)
        # lo hace el frontend con GET /vehiculos/{id}/kilometraje.
        kilometraje=datos.kilometraje,
        precio_usd=datos.precio_usd,
        plan=datos.plan.value,
        estado=EstadoPublicacion.BORRADOR.value,
        # Premium compra el "destacado"; la verificación es un paso aparte que el dueño
        # SOLICITA con tokens (POST .../solicitar-verificacion). Nace no_verificado.
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=es_premium,
    )
    sesion.add(pub)
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
                selectinload(PublicacionInterna.fotos),
            )
            .order_by(PublicacionInterna.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return [PublicacionInternaSalida.desde_modelo(p) for p in pubs]


@router.get(
    "/publicaciones/{publicacion_id}/mia", response_model=PublicacionDetalleSalida
)
def detalle_publicacion_propia(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Detalle de MI publicación en **cualquier estado** (incluido `borrador`).

    Existe porque el editor de ficha y el de fotos necesitan prellenar sus campos, y el
    detalle público solo sirve publicaciones `activa`. Sin este endpoint, un borrador
    —o una publicación pausada— no se podría terminar de completar: justo lo que M2.8
    necesita habilitar. 404 indistinto si no existe o no es del usuario.
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)
    return PublicacionDetalleSalida.desde_modelo(pub)


@router.patch("/publicaciones/{publicacion_id}", response_model=PublicacionInternaSalida)
def actualizar_publicacion(
    publicacion_id: int,
    datos: PublicacionInternaActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Edita precio/descripción/ciudad/kilometraje/estado, publica un borrador o asciende
    a premium.

    **Semántica de campos (M2.11):** para los campos opcionales del auto (`titulo`,
    `descripcion`, `ciudad`, `kilometraje`) se distingue *omitido* de *enviado en `null`*
    con `model_fields_set` — mismo patrón que `actualizar_ficha`. Omitir = no lo toques;
    `null` explícito = **bórralo** (el vendedor se equivocó al teclear). `precio_usd` no
    es opcional (`gt=0`), así que solo se reemplaza, nunca se vacía.

    **Transición `borrador → activa` (M2.8):** exige que la ficha llegue a
    `UMBRAL_FICHA_PUBLICACION` (422 si no). No se puede volver a `borrador` desde otro
    estado: gracias a eso el punto de cobro es exactamente-una-vez y re-activar tras una
    pausa nunca vuelve a debitar.

    Monetización suspendida (§1.0.3): subir a premium es gratis y solo activa el destacado;
    bajar a light lo quita. El débito (`TOKENS_PUBLICACION_PREMIUM`, hoy 0) y su rama 402
    quedan cableados en `_cobrar_premium` para cuando se reactive.
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)

    # Campos opcionales del auto: `null` explícito los vacía, omitirlos no los toca.
    enviados = datos.model_fields_set
    for campo in ("titulo", "descripcion", "ciudad", "kilometraje"):
        if campo in enviados:
            setattr(pub, campo, getattr(datos, campo))
    if datos.precio_usd is not None:
        pub.precio_usd = datos.precio_usd

    if datos.estado is not None:
        _aplicar_transicion_estado(pub, datos.estado)

    if datos.plan is not None:
        pub.plan = datos.plan.value
        # Premium = destacado. La verificación NO se activa aquí: el dueño la solicita
        # aparte con tokens. Bajar a light quita el destacado (y el sello deja de aplicar).
        pub.destacado = datos.plan == PlanPublicacion.PREMIUM

    # Cobro del premium: UN solo predicado sobre el estado RESULTANTE, no sobre flags de
    # lo que cambió. Se debita cuando el anuncio queda premium Y activa y todavía no se
    # había cobrado (`premium_cobrado_en`). Con eso:
    #   - un borrador premium no cuesta nada hasta publicarse,
    #   - pausar y reactivar no vuelve a cobrar,
    #   - `light → premium → activa` cobra UNA vez (antes cobraba dos).
    # Bajar a light no reembolsa, y volver a premium tampoco re-cobra (marca ya puesta).
    cobra_premium = (
        pub.plan == PlanPublicacion.PREMIUM.value
        and pub.estado == EstadoPublicacion.ACTIVA.value
        and pub.premium_cobrado_en is None
    )
    if cobra_premium:
        # Se marca ANTES de debitar: van en la misma transacción, así que si el saldo no
        # alcanza el rollback de `_cobrar_premium` también revierte la marca.
        pub.premium_cobrado_en = datetime.now(timezone.utc)
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
    "/publicaciones/{publicacion_id}/renovar",
    response_model=PublicacionInternaSalida,
)
def renovar_publicacion(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El dueño RENUEVA su anuncio: lo vuelve a poner al frente del feed y de la búsqueda.

    Efecto: `renovada_en = now()`. No toca `creado_en` ni cobra (§1.0.3).

    - Solo el dueño (404 indistinto si no existe o no es suya).
    - Solo si está `activa` (422 si borrador/pausada/vendida: renovar algo que nadie ve
      no tiene sentido; primero se reactiva). Esto es el "siempre que el vehículo aún
      esté activo" de la decisión de producto.
    - Solo si YA perdió vigencia (`>= SEMANAS_VIGENCIA_PUBLICACION` semanas sin renovar).
      422 si todavía está vigente: renovar no es un atajo para saltar la cola, es el
      remedio de un anuncio que quedó viejo.
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)

    if pub.estado != EstadoPublicacion.ACTIVA.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solo puedes renovar un anuncio activo. Reactívalo primero.",
        )

    referencia = pub.renovada_en or pub.creado_en
    if semanas_desde_publicacion(referencia) < SEMANAS_VIGENCIA_PUBLICACION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Tu anuncio sigue vigente. Podrás renovarlo cuando cumpla "
                f"{SEMANAS_VIGENCIA_PUBLICACION} semanas sin cambios."
            ),
        )

    pub.renovada_en = datetime.now(timezone.utc)
    sesion.commit()
    return PublicacionInternaSalida.desde_modelo(
        _mi_publicacion(sesion, pub.id, usuario)
    )


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
    - Deja la publicación en `pendiente` → entra a la cola admin (`/admin/verificaciones`).
    - Monetización suspendida (§1.0.3): gratis. El débito (`TOKENS_VERIFICACION_MARKETPLACE`,
      hoy 0) y su rama 402 quedan cableados para cuando se reactive.
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

    Dentro de cada nivel, los anuncios que perdieron vigencia (`vigente=False`: N
    semanas sin renovar) caen AL FINAL. El sort es estable, así que la recencia manda
    dentro de cada grupo. No se ocultan: siguen visibles, solo dejan de competir por
    la parte de arriba (decisión 2026-08-27, depuración de data vieja).
    """
    activas = (
        select(PublicacionInterna)
        .where(PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value)
        .options(
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
            selectinload(PublicacionInterna.ficha),
            selectinload(PublicacionInterna.fotos),
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
    # Rezagadas al final de su nivel (sort estable: no reordena dentro del grupo).
    premium.sort(key=lambda s: not s.vigente)
    estandar.sort(key=lambda s: not s.vigente)

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
    referenciadas_salida = [
        PublicacionReferenciadaSalida.model_validate(r) for r in referenciadas
    ]
    referenciadas_salida.sort(key=lambda s: not s.vigente)

    return FeedMarketplaceSalida(
        premium=premium,
        estandar=estandar,
        referenciadas=referenciadas_salida,
    )


@router.get("/distribucion", response_model=DistribucionGeograficaSalida)
def distribucion_geografica(sesion: Session = Depends(obtener_sesion)):
    """Conteo de publicaciones ACTIVAS por provincia y región (portada: "¿dónde
    están los autos?"). Anónimo, solo lectura, solo BD propia (§10.2).

    Cuenta internas `activa` + referencias `activa` + `aprobada`. Agrupa por
    `ciudad` en SQL y pliega ciudad → provincia/región en Python vía `geografia`.
    Una ciudad no reconocida cuenta en `total` pero no en ninguna provincia.
    """
    filas_internas = sesion.execute(
        select(PublicacionInterna.ciudad, func.count())
        .where(PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value)
        .group_by(PublicacionInterna.ciudad)
    ).all()
    filas_ref = sesion.execute(
        select(PublicacionReferenciada.ciudad, func.count())
        .where(
            and_(
                PublicacionReferenciada.activa.is_(True),
                PublicacionReferenciada.estado_moderacion
                == EstadoModeracion.APROBADA.value,
            )
        )
        .group_by(PublicacionReferenciada.ciudad)
    ).all()

    total = 0
    por_provincia: dict[str, int] = {}
    provincia_region: dict[str, str] = {}
    for ciudad, n in [*filas_internas, *filas_ref]:
        total += n
        canon = geografia.ciudad_canonica(ciudad)
        if canon is None:
            continue
        provincia, region = geografia.CIUDAD_A_PROVINCIA[canon]
        por_provincia[provincia] = por_provincia.get(provincia, 0) + n
        provincia_region[provincia] = region

    con_ubicacion = sum(por_provincia.values())

    regiones: list[RegionDistribucionSalida] = []
    for region in geografia.REGIONES:
        provincias = sorted(
            (
                ProvinciaDistribucionSalida(provincia=p, total=c)
                for p, c in por_provincia.items()
                if provincia_region[p] == region
            ),
            key=lambda x: (-x.total, x.provincia),
        )
        if provincias:
            regiones.append(
                RegionDistribucionSalida(
                    region=region,
                    total=sum(p.total for p in provincias),
                    provincias=provincias,
                )
            )
    regiones.sort(key=lambda r: -r.total)

    return DistribucionGeograficaSalida(
        total=total, con_ubicacion=con_ubicacion, regiones=regiones
    )


# ──────────────── Búsqueda del comprador (MC2 — lista plana + cursor) ────────────────
#
# Endpoint NUEVO, independiente del feed (que sigue alimentando la portada curada MC1).
# Devuelve una lista PLANA ordenada, filtrable y paginada por cursor KEYSET (no offset:
# el offset se degrada con el volumen y el reel de la app —MC3— necesita paginación
# estable). Público/anónimo: el comprador no necesita cuenta. Solo BD propia (§10.2).
#
# ORDEN de la lista (vigencia + monetización + recencia):
#     vigente DESC, destacado DESC, creado_en DESC, fuente_orden ASC (internas=0,
#     referenciadas=1), id DESC
# `vigente` es la clave NUEVA de más peso (2026-08-27): un anuncio con N semanas sin
# renovar (`coalesce(renovada_en, creado_en)` para internas, `creado_en` para
# referenciadas, contra `now() - N semanas`) cae por debajo de TODOS los vigentes,
# premium incluidos. Dentro de cada mitad el orden anterior se mantiene igual.
# Las referenciadas se tratan como destacado=False, así caen debajo de las premium pero
# se intercalan con las light por fecha.

# Máximo de resultados por página (tope duro para no inflar la respuesta ni el reel).
LIMITE_BUSQUEDA_MAX = 50
LIMITE_BUSQUEDA_DEFAULT = 20

# fuente_orden: identifica de qué tabla viene la fila (y desempata premium ↔ referenciada).
FUENTE_INTERNA = 0
FUENTE_REFERENCIADA = 1


def _codificar_cursor(
    vigente: bool, destacado: bool, creado_en: datetime, fuente: int, id_: int
) -> str:
    """Serializa la posición de la ÚLTIMA fila de la página a un token opaco (base64).

    Claves cortas para no inflar el token: v=vigente, d=destacado, c=creado_en ISO,
    f=fuente_orden, i=id. El ISO preserva microsegundos y offset, así el `==` del keyset
    casa exacto.
    """
    crudo = json.dumps(
        {"v": vigente, "d": destacado, "c": creado_en.isoformat(), "f": fuente, "i": id_},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(crudo.encode("utf-8")).decode("ascii")


def _decodificar_cursor(cursor: str) -> tuple[bool, bool, datetime, int, int]:
    """Decodifica el cursor opaco. Cursor corrupto/ilegible → ValueError (el endpoint
    lo traduce a 400: es un error de FORMATO, no de negocio).

    Cursores emitidos antes de la clave `vigente` (migración 0026) no traen `v`: se
    asumen `vigente=True` para no romper una paginación en curso — a lo sumo el
    usuario ve una vez más algún anuncio que ya cruzó el umbral entre páginas."""
    try:
        crudo = base64.urlsafe_b64decode(cursor.encode("ascii"))
        datos = json.loads(crudo)
        return (
            bool(datos.get("v", True)),
            bool(datos["d"]),
            datetime.fromisoformat(datos["c"]),
            int(datos["f"]),
            int(datos["i"]),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"Cursor inválido: {e}") from e


def _patron_ilike(termino: str) -> str:
    """Escapa los comodines LIKE del término del usuario para que `%`/`_` no actúen
    como comodines (se buscan literales). El escape char es `\\` (ver ilike(escape=...))."""
    seguro = termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{seguro}%"


@router.get("/buscar", response_model=ResultadoBusquedaSalida)
def buscar_publicaciones(
    sesion: Session = Depends(obtener_sesion),
    q: str | None = Query(default=None, max_length=80),
    tipo: TipoCarroceria | None = Query(default=None),
    combustible: Combustible | None = Query(default=None),
    transmision: Transmision | None = Query(default=None),
    precio_min: Decimal | None = Query(default=None, ge=0),
    precio_max: Decimal | None = Query(default=None, ge=0),
    anio_min: int | None = Query(default=None),
    anio_max: int | None = Query(default=None),
    provincia: str | None = Query(default=None),
    region: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limite: int = Query(default=LIMITE_BUSQUEDA_DEFAULT, ge=1, le=LIMITE_BUSQUEDA_MAX),
):
    """Búsqueda plana del comprador: filtros combinables + paginación por cursor keyset.

    Filtros (todos opcionales; valor fuera de catálogo → 422 con las opciones, gratis):
    - `q`: texto libre sobre título/marca/modelo (ILIKE; el plegado de acentos queda como
      deuda —las marcas comunes no llevan tilde—; NO se agrega la extensión `unaccent`).
    - `tipo`/`combustible`/`transmision`: catálogos de la ficha técnica.
    - `precio_min`/`precio_max`, `anio_min`/`anio_max`: rangos.
    - `provincia` / `region`: ubicación del auto en venta, derivada de `ciudad` vía
      `geografia.py`. Si se dan ambos, se intersecan. Una referencia con `ciudad` de
      texto libre que no casa exactamente con el catálogo NO entra por este filtro.

    Cursor opaco (base64); inválido → **400** (formato). `siguiente_cursor=null` cuando
    ya no hay más páginas. Anónimo (sin `Depends(usuario_actual)`). Solo BD propia (§10.2).
    """
    hay_filtro_ficha = tipo is not None or combustible is not None or transmision is not None

    # ── Filtro geográfico → conjunto de ciudades del catálogo a casar ────────────
    ciudades_geo: list[str] | None = None
    if region is not None:
        if region not in geografia.REGIONES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Región no válida. Opciones: {list(geografia.REGIONES)}.",
            )
        ciudades_geo = geografia.ciudades_de_region(region)
    if provincia is not None:
        if provincia not in geografia.PROVINCIAS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Provincia no válida. Opciones: {list(geografia.PROVINCIAS)}.",
            )
        de_provincia = geografia.ciudades_de_provincia(provincia)
        ciudades_geo = (
            de_provincia
            if ciudades_geo is None
            else [c for c in de_provincia if c in ciudades_geo]
        )

    # Corte de vigencia: un timestamp fijo para todo el request (no `now()` por fila),
    # así el keyset entre páginas es estable. Un anuncio con `renovada_en` / `creado_en`
    # ANTERIOR a este corte ya lleva N semanas sin renovar → `vigente=False`.
    umbral_vigencia = datetime.now(timezone.utc) - timedelta(
        weeks=SEMANAS_VIGENCIA_PUBLICACION
    )

    # ── Paso 1: KEYSET sobre una proyección liviana ──────────────────────────────
    # Se proyectan solo las columnas de ordenamiento/keyset + el (fuente, id) que
    # identifica la fila para hidratarla después. Los filtros se aplican DENTRO de cada
    # rama del UNION (antes de unir), así cada rama filtra por sus propias columnas.

    # Rama INTERNAS (solo activas). Se unen ficha/vehículo solo si un filtro los necesita.
    sel_internas = select(
        literal(FUENTE_INTERNA).label("fuente"),
        PublicacionInterna.id.label("id"),
        (PublicacionInterna.renovada_en >= umbral_vigencia).label("vigente"),
        PublicacionInterna.destacado.label("destacado"),
        PublicacionInterna.creado_en.label("creado_en"),
    ).where(PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value)

    # Join a vehículo (LEFT) si `q` o filtro de año lo requieren. Con LEFT + WHERE de año,
    # una interna SIN vehículo vinculado queda con anio NULL y NO pasa el filtro de año
    # (exclusión pedida). Para `q`, el título puede casar aunque no haya vehículo.
    if q is not None or anio_min is not None or anio_max is not None:
        sel_internas = sel_internas.join(
            Vehiculo, PublicacionInterna.vehiculo_id == Vehiculo.id, isouter=True
        )
    if anio_min is not None:
        sel_internas = sel_internas.where(Vehiculo.anio >= anio_min)
    if anio_max is not None:
        sel_internas = sel_internas.where(Vehiculo.anio <= anio_max)
    if q is not None:
        patron = _patron_ilike(q)
        sel_internas = sel_internas.where(
            or_(
                PublicacionInterna.titulo.ilike(patron, escape="\\"),
                Vehiculo.marca.ilike(patron, escape="\\"),
                Vehiculo.modelo.ilike(patron, escape="\\"),
            )
        )
    # Join a ficha (INNER) si hay filtro de ficha: una interna sin ficha no puede cumplir
    # un filtro de tipo/combustible/transmisión, así que se excluye del INNER join.
    if hay_filtro_ficha:
        sel_internas = sel_internas.join(
            FichaPublicacion, FichaPublicacion.publicacion_id == PublicacionInterna.id
        )
        if combustible is not None:
            sel_internas = sel_internas.where(
                FichaPublicacion.motor_suspension["combustible"].astext == combustible
            )
        if transmision is not None:
            sel_internas = sel_internas.where(
                FichaPublicacion.motor_suspension["transmision"].astext == transmision
            )
        if tipo is not None:
            sel_internas = sel_internas.where(
                FichaPublicacion.carroceria["tipo"].astext == tipo
            )
    if precio_min is not None:
        sel_internas = sel_internas.where(PublicacionInterna.precio_usd >= precio_min)
    if precio_max is not None:
        sel_internas = sel_internas.where(PublicacionInterna.precio_usd <= precio_max)
    if ciudades_geo is not None:
        sel_internas = sel_internas.where(PublicacionInterna.ciudad.in_(ciudades_geo))

    ramas = [sel_internas]

    # Rama REFERENCIADAS (solo activas + aprobadas). Se OMITE por completo si hay filtro
    # de ficha: una referencia no tiene ficha técnica, no puede cumplir esos filtros.
    if not hay_filtro_ficha:
        sel_ref = select(
            literal(FUENTE_REFERENCIADA).label("fuente"),
            PublicacionReferenciada.id.label("id"),
            (PublicacionReferenciada.creado_en >= umbral_vigencia).label("vigente"),
            literal(False).label("destacado"),
            PublicacionReferenciada.creado_en.label("creado_en"),
        ).where(
            and_(
                PublicacionReferenciada.activa.is_(True),
                PublicacionReferenciada.estado_moderacion == EstadoModeracion.APROBADA.value,
            )
        )
        if anio_min is not None:
            sel_ref = sel_ref.where(PublicacionReferenciada.anio >= anio_min)
        if anio_max is not None:
            sel_ref = sel_ref.where(PublicacionReferenciada.anio <= anio_max)
        if precio_min is not None:
            sel_ref = sel_ref.where(PublicacionReferenciada.precio_usd >= precio_min)
        if precio_max is not None:
            sel_ref = sel_ref.where(PublicacionReferenciada.precio_usd <= precio_max)
        if q is not None:
            patron = _patron_ilike(q)
            sel_ref = sel_ref.where(
                or_(
                    PublicacionReferenciada.marca.ilike(patron, escape="\\"),
                    PublicacionReferenciada.modelo.ilike(patron, escape="\\"),
                )
            )
        if ciudades_geo is not None:
            sel_ref = sel_ref.where(PublicacionReferenciada.ciudad.in_(ciudades_geo))
        ramas.append(sel_ref)

    u = (union_all(*ramas) if len(ramas) > 1 else ramas[0]).subquery("u")

    consulta = select(u.c.fuente, u.c.id, u.c.vigente, u.c.destacado, u.c.creado_en)

    # Keyset: filas ESTRICTAMENTE después del cursor en el orden
    # (vigente DESC, destacado DESC, creado_en DESC, fuente ASC, id DESC). `vigente` y
    # `destacado` son Boolean y ordenan DESC mientras `fuente` ordena ASC, así que NO
    # cabe un row-value único: se expande por niveles, cada nivel anclado en el/los
    # anterior(es) por igualdad.
    if cursor is not None:
        try:
            c_vig, c_dest, c_creado, c_fuente, c_id = _decodificar_cursor(cursor)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )
        consulta = consulta.where(
            or_(
                # Boolean: SQLAlchemy no permite `<` con un literal bool, así que se
                # compara como entero (false=0 < true=1) para el "viene después".
                cast(u.c.vigente, Integer) < (1 if c_vig else 0),
                and_(
                    u.c.vigente == c_vig,
                    cast(u.c.destacado, Integer) < (1 if c_dest else 0),
                ),
                and_(
                    u.c.vigente == c_vig,
                    u.c.destacado == c_dest,
                    u.c.creado_en < c_creado,
                ),
                and_(
                    u.c.vigente == c_vig,
                    u.c.destacado == c_dest,
                    u.c.creado_en == c_creado,
                    u.c.fuente > c_fuente,
                ),
                and_(
                    u.c.vigente == c_vig,
                    u.c.destacado == c_dest,
                    u.c.creado_en == c_creado,
                    u.c.fuente == c_fuente,
                    u.c.id < c_id,
                ),
            )
        )

    consulta = consulta.order_by(
        u.c.vigente.desc(),
        u.c.destacado.desc(),
        u.c.creado_en.desc(),
        u.c.fuente.asc(),
        u.c.id.desc(),
    ).limit(limite + 1)  # +1 detecta si hay página siguiente sin un COUNT aparte

    filas = sesion.execute(consulta).all()

    hay_mas = len(filas) > limite
    filas_pagina = filas[:limite]

    # ── Paso 2: HIDRATACIÓN en lote (sin N+1) + re-ensamble en el orden del paso 1 ──
    ids_internas = [f.id for f in filas_pagina if f.fuente == FUENTE_INTERNA]
    ids_ref = [f.id for f in filas_pagina if f.fuente == FUENTE_REFERENCIADA]

    mapa_internas: dict[int, PublicacionInterna] = {}
    if ids_internas:
        internas = (
            sesion.execute(
                select(PublicacionInterna)
                .where(PublicacionInterna.id.in_(ids_internas))
                .options(
                    selectinload(PublicacionInterna.vehiculo).selectinload(
                        Vehiculo.mantenimientos
                    ),
                    selectinload(PublicacionInterna.ficha),
                    selectinload(PublicacionInterna.fotos),
                )
            )
            .scalars()
            .all()
        )
        mapa_internas = {p.id: p for p in internas}

    mapa_ref: dict[int, PublicacionReferenciada] = {}
    if ids_ref:
        refs = (
            sesion.execute(
                select(PublicacionReferenciada).where(
                    PublicacionReferenciada.id.in_(ids_ref)
                )
            )
            .scalars()
            .all()
        )
        mapa_ref = {r.id: r for r in refs}

    items: list[ItemBusqueda] = []
    for f in filas_pagina:
        if f.fuente == FUENTE_INTERNA:
            pub = mapa_internas.get(f.id)
            if pub is None:
                continue  # desapareció entre el paso 1 y 2 (carrera improbable): se omite
            items.append(
                ItemBusqueda(
                    tipo_publicacion="interna",
                    interna=PublicacionInternaSalida.desde_modelo(pub),
                )
            )
        else:
            ref = mapa_ref.get(f.id)
            if ref is None:
                continue
            items.append(
                ItemBusqueda(
                    tipo_publicacion="referenciada",
                    referenciada=PublicacionReferenciadaSalida.model_validate(ref),
                )
            )

    siguiente_cursor = None
    if hay_mas and filas_pagina:
        ultima = filas_pagina[-1]
        siguiente_cursor = _codificar_cursor(
            bool(ultima.vigente),
            bool(ultima.destacado),
            ultima.creado_en,
            int(ultima.fuente),
            int(ultima.id),
        )

    return ResultadoBusquedaSalida(items=items, siguiente_cursor=siguiente_cursor)


# ──────────────── Verificación premium (admin) ────────────────


def _cargar_publicacion(sesion: Session, publicacion_id: int) -> PublicacionInterna | None:
    """Carga una publicación por id con vehículo+mantenimientos (eager, sin scope de dueño)."""
    return sesion.execute(
        select(PublicacionInterna)
        .where(PublicacionInterna.id == publicacion_id)
        .options(
            selectinload(PublicacionInterna.vehiculo).selectinload(Vehiculo.mantenimientos),
            selectinload(PublicacionInterna.ficha),
            selectinload(PublicacionInterna.fotos),
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
                selectinload(PublicacionInterna.fotos),
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


# ──────────────── Fotos de la publicación (M2 — market de autos) ────────────────
#
# El binario NO pasa por el backend: el navegador pide una firma, sube directo a
# Cloudinary y luego registra aquí la URL resultante. Todo el CRUD es del dueño
# (404 indistinto si no es suya) y gratis (la transparencia no se cobra).
#
# Orden de rutas dentro de `/publicaciones/{publicacion_id}/fotos`: las literales
# (`firma`, `orden`) van declaradas antes que la dinámica `{foto_id}`.


def _requiere_cloudinary() -> None:
    """503 si Cloudinary no está configurado (config faltante, no error de negocio)."""
    if not cloudinary.esta_configurado():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La subida de fotos no está disponible: falta configurar Cloudinary.",
        )


@router.post(
    "/publicaciones/{publicacion_id}/fotos/firma",
    response_model=FirmaSubidaSalida,
)
def firmar_subida_foto(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Firma una subida directa a Cloudinary para las fotos de esta publicación.

    - Solo el dueño (404 si no es suya).
    - 503 si Cloudinary no está configurado.
    - El `folder` queda atado a la publicación (`<base>/<id>`) y va firmado, para que
      el navegador no pueda subir a rutas arbitrarias.
    """
    _requiere_cloudinary()
    _mi_publicacion(sesion, publicacion_id, usuario)  # valida propiedad (404 si no)
    folder = cloudinary.carpeta_publicacion(publicacion_id)
    return FirmaSubidaSalida(**cloudinary.firmar_subida(folder))


@router.post(
    "/publicaciones/{publicacion_id}/fotos",
    response_model=FotoSalida,
    status_code=status.HTTP_201_CREATED,
)
def registrar_foto(
    publicacion_id: int,
    datos: FotoRegistrar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Registra una foto ya subida a Cloudinary (persiste solo la URL).

    - Solo el dueño (404 si no es suya).
    - 503 si Cloudinary no está configurado (no hay contra qué validar la URL).
    - 400 si la URL no es https ni de NUESTRO cloud de Cloudinary.
    - 409 si la publicación ya tiene el máximo de fotos (`MAX_FOTOS_POR_PUBLICACION`).
    - `orden` por defecto = al final de la galería.
    """
    _requiere_cloudinary()
    pub = _mi_publicacion(sesion, publicacion_id, usuario)

    if not cloudinary.url_es_de_nuestro_cloud(datos.url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La URL debe ser un enlace https de nuestro cloud de Cloudinary.",
        )

    if len(pub.fotos) >= MAX_FOTOS_POR_PUBLICACION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Máximo {MAX_FOTOS_POR_PUBLICACION} fotos por publicación.",
        )

    # `pub.fotos` viene ordenado por `orden` asc: el último marca el final.
    orden = datos.orden if datos.orden is not None else (
        pub.fotos[-1].orden + 1 if pub.fotos else 0
    )
    foto = FotoPublicacion(
        publicacion_id=pub.id,
        url=datos.url,
        bloque=datos.bloque,
        orden=orden,
    )
    sesion.add(foto)
    sesion.commit()
    sesion.refresh(foto)
    return FotoSalida.model_validate(foto)


@router.patch(
    "/publicaciones/{publicacion_id}/fotos/orden",
    response_model=list[FotoSalida],
)
def reordenar_fotos(
    publicacion_id: int,
    datos: FotoReordenar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Reordena la galería según la lista de `foto_id` recibida.

    - Solo el dueño (404 si no es suya).
    - 422 si la lista no coincide EXACTAMENTE con el conjunto de fotos de la
      publicación (falta alguna, sobra alguna o hay repetidas).
    - Reasigna `orden` = posición en la lista (0-based) y devuelve la galería ordenada.
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)

    ids_actuales = {f.id for f in pub.fotos}
    ids_pedidos = datos.orden
    if len(ids_pedidos) != len(set(ids_pedidos)) or set(ids_pedidos) != ids_actuales:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La lista de orden debe contener exactamente las fotos de la publicación.",
        )

    posicion = {foto_id: i for i, foto_id in enumerate(ids_pedidos)}
    for foto in pub.fotos:
        foto.orden = posicion[foto.id]
    sesion.commit()

    pub = _mi_publicacion(sesion, publicacion_id, usuario)  # recarga ordenada
    return [FotoSalida.model_validate(f) for f in pub.fotos]


@router.delete(
    "/publicaciones/{publicacion_id}/fotos/{foto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_foto(
    publicacion_id: int,
    foto_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Elimina una foto de la publicación (404 indistinto si no es tuya/no existe).

    Nota: no borra el binario en Cloudinary (queda a limpieza aparte); aquí solo se
    quita el registro de la URL.
    """
    pub = _mi_publicacion(sesion, publicacion_id, usuario)  # 404 si la pub no es suya
    foto = next((f for f in pub.fotos if f.id == foto_id), None)
    if foto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Foto no encontrada"
        )
    sesion.delete(foto)
    sesion.commit()
    return None


# ──────────────── Contacto con el vendedor (TASK-001) ────────────────
#
# Cierra el circuito del marketplace: el comprador pide el número y se va a WhatsApp.
# PÚBLICO (sin `usuario_actual`) y GRATIS (sin `debitar_tokens`): §1.0.3 dice que el
# contacto es libre. El teléfono no viaja en el feed ni en el detalle — solo aquí, bajo
# una acción explícita, que además es la barrera contra el scraping de números (§9).
#
# Va declarado ANTES de la dinámica `GET /publicaciones/{publicacion_id}` del final (§5).


def _vendedor_de(sesion: Session, pub: PublicacionInterna) -> Vendedor | None:
    """Resuelve el vendedor de una publicación interna por su vínculo explícito.

    **Una sola vía: `vendedor_id`.** La migración `0021` lo pobló en las publicaciones
    que ya existían y `crear_publicacion` lo puebla en las nuevas, así que no hace falta
    resolución alternativa.

    Deliberadamente NO se cae a `Vendedor.usuario_id == pub.usuario_id`. Ese atajo es
    equivalente solo mientras la relación cuenta↔vendedor sea 1:1: en la etapa 2, con la
    UK levantada, devolvería un vendedor **arbitrario** de la cuenta —en silencio y sin
    forma de notarlo— o reventaría con `MultipleResultsFound` en un 500. Un `vendedor_id`
    en NULL debe salir como 409 ("todavía no hay contacto"), que es honesto y visible.
    """
    if pub.vendedor_id is None:
        return None
    return sesion.execute(
        select(Vendedor).where(Vendedor.id == pub.vendedor_id)
    ).scalar_one_or_none()


@router.post(
    "/publicaciones/{publicacion_id}/contacto", response_model=ContactoVendedorSalida
)
def revelar_contacto(
    publicacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario | None = Depends(usuario_actual_opcional),
):
    """Devuelve el contacto del vendedor y registra la revelación (métrica anónima).

    - **404** si la publicación no existe o no es visible públicamente (borrador,
      pausada o vendida): indistinto, para no revelar qué ids existen.
    - **409** si el vendedor todavía no cargó un teléfono. Es "dato no disponible", no
      un fallo: se responde con copy que explica la alternativa, nunca un 500.
    - Registra un `ContactoRevelado` **anónimo**: ni IP, ni user-agent, ni usuario (§9).

    **Auth opcional** (`usuario_actual_opcional`, nunca 401): el endpoint sigue siendo
    público y sin token se comporta igual que antes. Si llega un Bearer válido y quien
    consulta **es el propio vendedor**, se le devuelve el contacto pero **no se registra
    la revelación**: `ContactoRevelado` mide *demanda de compradores*, y el vendedor
    mirando su propio anuncio no es demanda. Con un puñado de cuentas de prueba, el
    autoconsumo domina la métrica desde el primer día — es lo que ya pasó con los
    desbloqueos por tokens, todos del equipo, que por eso no dicen nada.

    Un token inválido o vencido no rompe nada: `usuario_actual_opcional` devuelve `None`
    y el flujo cae en la rama anónima.
    """
    pub = sesion.execute(
        select(PublicacionInterna).where(
            and_(
                PublicacionInterna.id == publicacion_id,
                PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value,
            )
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )

    vendedor = _vendedor_de(sesion, pub)
    if vendedor is None or not vendedor.telefono:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este anuncio todavía no tiene un número de contacto publicado. "
                "Puedes guardarlo en favoritos y volver a intentarlo más tarde."
            ),
        )

    # El dueño del anuncio no cuenta como demanda: se le entrega el contacto igual, pero
    # sin ensuciar la métrica. Se compara contra el vendedor RESUELTO (no contra
    # `pub.usuario_id`), que es quien de verdad recibe los mensajes; en la etapa 2 esos
    # dos dejan de coincidir.
    es_el_vendedor = usuario is not None and vendedor.usuario_id == usuario.id
    if not es_el_vendedor:
        sesion.add(ContactoRevelado(publicacion_interna_id=pub.id))
        sesion.commit()

    return ContactoVendedorSalida(
        telefono=vendedor.telefono,
        nombre_publico=vendedor.nombre_publico,
        whatsapp_url=armar_whatsapp_url(vendedor.telefono, pub.titulo or pub.placa),
    )


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
            selectinload(PublicacionInterna.fotos),
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )
    return PublicacionDetalleSalida.desde_modelo(pub)
