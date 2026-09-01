"""Puntos de encuentro seguros para negociar en persona (migración 0033).

Un catálogo de lugares curados por un admin (hoy: 6 en Quito). Un vendedor anuncia
que va a llevar UNA de sus publicaciones a un punto en una fecha/franja
(`POST /puntos-encuentro/{id}/presencias`); cualquiera puede ver, por punto, qué
autos van a estar ahí (`GET /puntos-encuentro/{id}`) — es la "matriz visual" que
pidió Marcos: en vez de coordinar por chat quién va a qué lugar, el punto mismo
lista los autos anunciados.

Solo BD propia (§10.2). Gratis (§1.0.3). El catálogo de puntos lo administra un
admin; anunciar presencia es del vendedor dueño de la publicación.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    EstadoPresencia,
    EstadoPublicacion,
    PresenciaPunto,
    PublicacionInterna,
    PuntoEncuentro,
)
from src.modules.marketplace.schemas import (
    MiPresenciaSalida,
    PresenciaActualizar,
    PresenciaCrear,
    PresenciaSalida,
    PuntoEncuentroActualizar,
    PuntoEncuentroCrear,
    PuntoEncuentroDetalleSalida,
    PuntoEncuentroSalida,
    PuntoResumenSalida,
    VehiculoEnPresencia,
)

router = APIRouter(prefix="/marketplace", tags=["puntos-encuentro"])


def _vehiculo_resumen(pub: PublicacionInterna) -> VehiculoEnPresencia:
    veh = pub.vehiculo
    return VehiculoEnPresencia(
        publicacion_id=pub.id,
        placa=pub.placa,
        titulo=pub.titulo,
        marca=getattr(veh, "marca", None),
        modelo=getattr(veh, "modelo", None),
        anio=getattr(veh, "anio", None),
        precio_usd=pub.precio_usd,
        foto_portada=(pub.fotos[0].url if pub.fotos else None),
    )


def _conteos_activos(sesion: Session, punto_ids: list[int]) -> dict[int, int]:
    if not punto_ids:
        return {}
    filas = sesion.execute(
        select(PresenciaPunto.punto_id, func.count())
        .where(
            PresenciaPunto.punto_id.in_(punto_ids),
            PresenciaPunto.estado == EstadoPresencia.ANUNCIADA.value,
            PresenciaPunto.fecha >= date.today(),
        )
        .group_by(PresenciaPunto.punto_id)
    ).all()
    return {pid: n for pid, n in filas}


@router.get("/puntos-encuentro", response_model=list[PuntoEncuentroSalida])
def listar_puntos_encuentro(sesion: Session = Depends(obtener_sesion)):
    """Catálogo público de puntos activos, ordenado como lo definió el admin."""
    puntos = (
        sesion.execute(
            select(PuntoEncuentro)
            .where(PuntoEncuentro.activo.is_(True))
            .order_by(PuntoEncuentro.orden.asc(), PuntoEncuentro.nombre.asc())
        )
        .scalars()
        .all()
    )
    conteos = _conteos_activos(sesion, [p.id for p in puntos])
    return [
        PuntoEncuentroSalida.model_validate(p, from_attributes=True).model_copy(
            update={"presencias_activas": conteos.get(p.id, 0)}
        )
        for p in puntos
    ]


@router.post(
    "/puntos-encuentro",
    response_model=PuntoEncuentroSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_punto_encuentro(
    datos: PuntoEncuentroCrear,
    sesion: Session = Depends(obtener_sesion),
    _: Usuario = Depends(admin_actual),
):
    """Da de alta un punto de encuentro. Solo admin."""
    # `activo=True` explícito: un punto nuevo siempre nace visible (para
    # desactivarlo está el PATCH); no depende del `default=` del modelo, que el
    # ORM recién aplica al hacer flush.
    punto = PuntoEncuentro(**datos.model_dump(), activo=True)
    sesion.add(punto)
    sesion.commit()
    sesion.refresh(punto)
    return PuntoEncuentroSalida.model_validate(punto, from_attributes=True)


@router.patch("/puntos-encuentro/{punto_id}", response_model=PuntoEncuentroSalida)
def actualizar_punto_encuentro(
    punto_id: int,
    datos: PuntoEncuentroActualizar,
    sesion: Session = Depends(obtener_sesion),
    _: Usuario = Depends(admin_actual),
):
    """Edita un punto (o lo desactiva con `activo: false`). Solo admin."""
    punto = sesion.get(PuntoEncuentro, punto_id)
    if punto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Punto no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(punto, campo, valor)
    sesion.commit()
    sesion.refresh(punto)
    return PuntoEncuentroSalida.model_validate(punto, from_attributes=True)


@router.get(
    "/puntos-encuentro/{punto_id}", response_model=PuntoEncuentroDetalleSalida
)
def detalle_punto_encuentro(
    punto_id: int,
    sesion: Session = Depends(obtener_sesion),
):
    """Detalle público: datos del punto + la matriz de autos anunciados (vigentes,
    de anuncios que siguen `activa`, de hoy en adelante)."""
    punto = sesion.get(PuntoEncuentro, punto_id)
    if punto is None or not punto.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Punto no encontrado")

    filas = (
        sesion.execute(
            select(PresenciaPunto)
            .options(
                selectinload(PresenciaPunto.publicacion).selectinload(
                    PublicacionInterna.fotos
                ),
                selectinload(PresenciaPunto.publicacion).selectinload(
                    PublicacionInterna.vehiculo
                ),
            )
            .join(PublicacionInterna, PresenciaPunto.publicacion_interna_id == PublicacionInterna.id)
            .where(
                and_(
                    PresenciaPunto.punto_id == punto_id,
                    PresenciaPunto.estado == EstadoPresencia.ANUNCIADA.value,
                    PresenciaPunto.fecha >= date.today(),
                    PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value,
                )
            )
            .order_by(PresenciaPunto.fecha.asc(), PresenciaPunto.id.asc())
        )
        .scalars()
        .all()
    )

    presencias = [
        PresenciaSalida(
            id=f.id,
            punto_id=f.punto_id,
            fecha=f.fecha,
            franja=f.franja,
            estado=EstadoPresencia(f.estado),
            nota=f.nota,
            creado_en=f.creado_en,
            vehiculo=_vehiculo_resumen(f.publicacion),
        )
        for f in filas
    ]
    base = PuntoEncuentroSalida.model_validate(punto, from_attributes=True).model_copy(
        update={"presencias_activas": len(presencias)}
    )
    return PuntoEncuentroDetalleSalida(**base.model_dump(), presencias=presencias)


@router.post(
    "/puntos-encuentro/{punto_id}/presencias",
    response_model=PresenciaSalida,
    status_code=status.HTTP_201_CREATED,
)
def anunciar_presencia(
    punto_id: int,
    datos: PresenciaCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El dueño de una publicación anuncia que la va a llevar a este punto."""
    punto = sesion.get(PuntoEncuentro, punto_id)
    if punto is None or not punto.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Punto no encontrado")

    pub = sesion.execute(
        select(PublicacionInterna).where(
            and_(
                PublicacionInterna.id == datos.publicacion_id,
                PublicacionInterna.usuario_id == usuario.id,
            )
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )
    if pub.estado != EstadoPublicacion.ACTIVA.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solo puedes anunciar un auto con la publicación activa (no borrador, pausada ni vendida).",
        )

    presencia = PresenciaPunto(
        punto_id=punto_id,
        publicacion_interna_id=pub.id,
        usuario_id=usuario.id,
        fecha=datos.fecha,
        franja=datos.franja.value,
        nota=datos.nota,
        # Explícito (no fiado al `default=` del modelo): ese default lo aplica el
        # ORM recién al hacer flush, así que leerlo ANTES de eso (p. ej. al armar
        # la respuesta sin pasar por un commit real, como en los tests) da `None`.
        estado=EstadoPresencia.ANUNCIADA.value,
    )
    sesion.add(presencia)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya anunciaste este auto en este punto para esa fecha.",
        )
    sesion.refresh(presencia)
    return PresenciaSalida(
        id=presencia.id,
        punto_id=presencia.punto_id,
        fecha=presencia.fecha,
        franja=datos.franja,
        estado=EstadoPresencia(presencia.estado),
        nota=presencia.nota,
        creado_en=presencia.creado_en,
        vehiculo=_vehiculo_resumen(pub),
    )


def _mi_presencia(sesion: Session, presencia_id: int, usuario: Usuario) -> PresenciaPunto:
    presencia = sesion.execute(
        select(PresenciaPunto).where(
            and_(
                PresenciaPunto.id == presencia_id,
                PresenciaPunto.usuario_id == usuario.id,
            )
        )
    ).scalar_one_or_none()
    if presencia is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Presencia no encontrada"
        )
    return presencia


@router.get("/presencias/mias", response_model=list[MiPresenciaSalida])
def mis_presencias(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Mis anuncios en puntos de encuentro, en cualquier estado, más reciente primero."""
    filas = (
        sesion.execute(
            select(PresenciaPunto)
            .options(
                selectinload(PresenciaPunto.punto),
                selectinload(PresenciaPunto.publicacion).selectinload(
                    PublicacionInterna.fotos
                ),
                selectinload(PresenciaPunto.publicacion).selectinload(
                    PublicacionInterna.vehiculo
                ),
            )
            .where(PresenciaPunto.usuario_id == usuario.id)
            .order_by(PresenciaPunto.fecha.desc(), PresenciaPunto.id.desc())
        )
        .scalars()
        .all()
    )
    return [
        MiPresenciaSalida(
            id=f.id,
            punto=PuntoResumenSalida.model_validate(f.punto, from_attributes=True),
            fecha=f.fecha,
            franja=f.franja,
            estado=EstadoPresencia(f.estado),
            nota=f.nota,
            creado_en=f.creado_en,
            vehiculo=_vehiculo_resumen(f.publicacion),
        )
        for f in filas
    ]


@router.patch("/presencias/{presencia_id}", response_model=MiPresenciaSalida)
def actualizar_presencia(
    presencia_id: int,
    datos: PresenciaActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El dueño reprograma (fecha/franja/nota) o cierra (`estado`) su presencia."""
    presencia = _mi_presencia(sesion, presencia_id, usuario)
    cambios = datos.model_dump(exclude_unset=True)
    if "estado" in cambios:
        presencia.estado = cambios.pop("estado").value
    for campo, valor in cambios.items():
        setattr(presencia, campo, valor)
    sesion.commit()
    sesion.refresh(presencia)
    presencia = sesion.execute(
        select(PresenciaPunto)
        .options(
            selectinload(PresenciaPunto.punto),
            selectinload(PresenciaPunto.publicacion).selectinload(PublicacionInterna.fotos),
            selectinload(PresenciaPunto.publicacion).selectinload(PublicacionInterna.vehiculo),
        )
        .where(PresenciaPunto.id == presencia_id)
    ).scalar_one()
    return MiPresenciaSalida(
        id=presencia.id,
        punto=PuntoResumenSalida.model_validate(presencia.punto, from_attributes=True),
        fecha=presencia.fecha,
        franja=presencia.franja,
        estado=EstadoPresencia(presencia.estado),
        nota=presencia.nota,
        creado_en=presencia.creado_en,
        vehiculo=_vehiculo_resumen(presencia.publicacion),
    )


@router.delete("/presencias/{presencia_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_presencia(
    presencia_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    presencia = _mi_presencia(sesion, presencia_id, usuario)
    sesion.delete(presencia)
    sesion.commit()
    return None
