"""Referencias del marketplace aportadas por el usuario (Pilar 4).

En vez de raspar portales (FB exige login y bloquea bots — decisión 2026-05-30), el
usuario **pega el link** de un anuncio externo (Facebook Marketplace, OLX, PatioTuerca,
Mercado Libre…) y completa marca/modelo/precio a mano. Eso puebla `publicaciones_referenciadas`
de forma barata y siempre devuelve el tráfico al anuncio original.

Flujo de moderación (requiere aprobación):
- El aportante crea la referencia → entra `pendiente` (no aparece en el feed todavía).
- Un admin (`admin_actual`, lista `ADMIN_EMAILS`) la aprueba o rechaza.
- Editar el contenido de una ya aprobada la devuelve a `pendiente` (anti bait-and-switch).

Es gratis (no cuesta tokens): da volumen al feed. Solo toca la BD propia (§10.2).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    EstadoModeracion,
    PublicacionReferenciada,
)
from src.modules.marketplace.schemas import (
    FirmaSubidaSalida,
    ModeracionReferencia,
    PublicacionReferenciadaActualizar,
    PublicacionReferenciadaCrear,
    PublicacionReferenciadaSalida,
)
from src.modules.marketplace.services import cloudinary


router = APIRouter(prefix="/marketplace/referencias", tags=["marketplace"])

# Campos cuyo cambio invalida una aprobación previa (el anuncio "ya no es el mismo").
# M2.8 suma los campos ricos: si el aportante reescribe la descripción o cambia las fotos
# después de aprobada, vuelve a moderación — es exactamente el bait-and-switch que esto evita.
_CAMPOS_CONTENIDO = (
    "marca",
    "modelo",
    "anio",
    "precio_usd",
    "imagen_url",
    "placa",
    "descripcion",
    "ciudad",
    "kilometraje",
    "fotos",
)


def _mi_referencia(
    sesion: Session, referencia_id: int, usuario: Usuario
) -> PublicacionReferenciada:
    """Resuelve una referencia del usuario o lanza 404 (no distingue ajena de inexistente)."""
    ref = sesion.execute(
        select(PublicacionReferenciada).where(
            and_(
                PublicacionReferenciada.id == referencia_id,
                PublicacionReferenciada.usuario_id == usuario.id,
            )
        )
    ).scalar_one_or_none()
    if ref is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Referencia no encontrada"
        )
    return ref


@router.post(
    "", response_model=PublicacionReferenciadaSalida, status_code=status.HTTP_201_CREATED
)
def crear_referencia(
    datos: PublicacionReferenciadaCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Aporta una referencia externa. Entra `pendiente` hasta que un admin la apruebe.

    `fuente` se deriva del dominio del link (no se confía en el cliente). Si el mismo
    `url_externa` ya existe → 409 (dedup por índice único).
    """
    ref = PublicacionReferenciada(
        usuario_id=usuario.id,
        url_externa=datos.url_externa,
        fuente=datos.fuente_derivada(),
        marca=datos.marca,
        modelo=datos.modelo,
        anio=datos.anio,
        precio_usd=datos.precio_usd,
        imagen_url=datos.imagen_url,
        placa=datos.placa,
        # Campos ricos (M2.8): opcionales, para copiar el detalle del anuncio original.
        descripcion=datos.descripcion,
        ciudad=datos.ciudad,
        kilometraje=datos.kilometraje,
        fotos=datos.fotos,
        estado_moderacion=EstadoModeracion.PENDIENTE.value,
        activa=True,
    )
    sesion.add(ref)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese anuncio ya está referenciado.",
        )
    sesion.refresh(ref)
    return PublicacionReferenciadaSalida.model_validate(ref)


@router.post("/firma-foto", response_model=FirmaSubidaSalida)
def firmar_subida_foto_referencia(
    usuario: Usuario = Depends(usuario_actual),
):
    """Firma para subir a Cloudinary una foto de referencia (M2.8).

    El binario NO pasa por el backend: el navegador sube directo con esta firma y luego
    manda la URL en el alta/edición de la referencia. Como el formulario sube ANTES de
    crear la referencia (todavía no hay id), la carpeta se agrupa por usuario.

    503 si Cloudinary no está configurado (config faltante, no error de negocio).
    """
    if not cloudinary.esta_configurado():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La subida de fotos no está disponible por ahora.",
        )
    return FirmaSubidaSalida(
        **cloudinary.firmar_subida(cloudinary.carpeta_referencia_nueva(usuario.id))
    )


@router.get("/mias", response_model=list[PublicacionReferenciadaSalida])
def listar_mis_referencias(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Referencias que aportó el usuario (cualquier estado), de la más reciente a la más antigua."""
    refs = (
        sesion.execute(
            select(PublicacionReferenciada)
            .where(PublicacionReferenciada.usuario_id == usuario.id)
            .order_by(PublicacionReferenciada.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return [PublicacionReferenciadaSalida.model_validate(r) for r in refs]


@router.patch("/{referencia_id}", response_model=PublicacionReferenciadaSalida)
def actualizar_referencia(
    referencia_id: int,
    datos: PublicacionReferenciadaActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Edita los datos de una referencia propia. Cambiar el contenido la regresa a
    `pendiente` (vuelve a requerir aprobación). `activa` permite pausarla sin re-moderar."""
    ref = _mi_referencia(sesion, referencia_id, usuario)

    cambios = datos.model_dump(exclude_unset=True)
    contenido_cambio = False
    for campo in _CAMPOS_CONTENIDO:
        if campo in cambios:
            valor = cambios[campo]
            # `fotos` es NOT NULL en BD: un `fotos: null` explícito significa "quitar
            # todas", no "guardar NULL" (que reventaría en un IntegrityError → 500).
            if campo == "fotos" and valor is None:
                valor = []
            setattr(ref, campo, valor)
            contenido_cambio = True
    if "activa" in cambios:
        ref.activa = cambios["activa"]

    if contenido_cambio and ref.estado_moderacion == EstadoModeracion.APROBADA.value:
        ref.estado_moderacion = EstadoModeracion.PENDIENTE.value

    sesion.commit()
    sesion.refresh(ref)
    return PublicacionReferenciadaSalida.model_validate(ref)


@router.delete("/{referencia_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_referencia(
    referencia_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    ref = _mi_referencia(sesion, referencia_id, usuario)
    sesion.delete(ref)
    sesion.commit()
    return None


# ──────────────────────────── Moderación (admin) ────────────────────────────


@router.get("/pendientes", response_model=list[PublicacionReferenciadaSalida])
def listar_pendientes(
    sesion: Session = Depends(obtener_sesion),
    _: Usuario = Depends(admin_actual),
):
    """Cola de referencias por moderar (las más antiguas primero). Solo admin."""
    refs = (
        sesion.execute(
            select(PublicacionReferenciada)
            .where(
                PublicacionReferenciada.estado_moderacion
                == EstadoModeracion.PENDIENTE.value
            )
            .order_by(PublicacionReferenciada.creado_en.asc())
        )
        .scalars()
        .all()
    )
    return [PublicacionReferenciadaSalida.model_validate(r) for r in refs]


@router.post("/{referencia_id}/moderar", response_model=PublicacionReferenciadaSalida)
def moderar_referencia(
    referencia_id: int,
    decision: ModeracionReferencia,
    sesion: Session = Depends(obtener_sesion),
    _: Usuario = Depends(admin_actual),
):
    """Aprueba o rechaza una referencia. Solo admin. 404 si no existe."""
    ref = sesion.get(PublicacionReferenciada, referencia_id)
    if ref is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Referencia no encontrada"
        )
    ref.estado_moderacion = decision.decision.value
    sesion.commit()
    sesion.refresh(ref)
    return PublicacionReferenciadaSalida.model_validate(ref)


# NOTA de orden: esta ruta con path param dinámico va AL FINAL del router. Si se
# declarara antes que las literales GET (`/mias`, `/pendientes`), "mias" intentaría
# parsearse como int y esas rutas quedarían inalcanzables (422). No mover hacia arriba.
@router.get("/{referencia_id}", response_model=PublicacionReferenciadaSalida)
def detalle_referencia(
    referencia_id: int,
    sesion: Session = Depends(obtener_sesion),
):
    """Detalle público de una referencia externa (M2.9).

    Anónimo: alimenta la página local `/marketplace/referencias/{id}`, donde el visitante
    ve fotos y detalle ANTES de decidir salir al portal de origen.

    Solo sirve las **aprobadas y activas**: una referencia `pendiente` o `rechazada` no
    puede filtrarse por URL directa (mismo criterio que el feed). 404 indistinto, para no
    revelar si el id existe pero está sin moderar.
    """
    ref = sesion.execute(
        select(PublicacionReferenciada).where(
            and_(
                PublicacionReferenciada.id == referencia_id,
                PublicacionReferenciada.estado_moderacion
                == EstadoModeracion.APROBADA.value,
                PublicacionReferenciada.activa.is_(True),
            )
        )
    ).scalar_one_or_none()
    if ref is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Referencia no encontrada"
        )
    return PublicacionReferenciadaSalida.model_validate(ref)
