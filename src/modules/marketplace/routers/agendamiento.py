"""Agendamiento de citas para el directorio de servicios (migración 0034).

La plataforma ofrece agendamiento. Dos lados:
- **Cliente**: pide una cita en un servicio con `acepta_agendamiento=True`
  (`POST /servicios/{id}/citas`), la ve en `GET /citas/mias`, la cancela o acepta
  una reprogramación (`PATCH /citas/{id}`).
- **Negocio** (el usuario que aportó el servicio, o un admin): ve las solicitudes
  (`GET /citas/recibidas`) y responde (`POST /citas/{id}/responder`): confirmar,
  reprogramar, rechazar o marcar cumplida.

Solo BD propia (§10.2). Gratis (§1.0.3).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import es_email_admin, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    CitaServicio,
    EstadoCita,
    EstadoModeracion,
    Servicio,
)
from src.modules.marketplace.schemas import (
    CitaActualizar,
    CitaCrear,
    CitaSalida,
    RespuestaNegocio,
)

router = APIRouter(prefix="/marketplace", tags=["agendamiento"])


def _salida(c: CitaServicio) -> CitaSalida:
    return CitaSalida(
        id=c.id,
        servicio_id=c.servicio_id,
        servicio_nombre=getattr(c.servicio, "nombre", None),
        servicio_ciudad=getattr(c.servicio, "ciudad", None),
        nombre_contacto=c.nombre_contacto,
        telefono_contacto=c.telefono_contacto,
        vehiculo=c.vehiculo,
        motivo=c.motivo,
        fecha=c.fecha,
        franja=c.franja,
        nota=c.nota,
        estado=EstadoCita(c.estado),
        respuesta_negocio=c.respuesta_negocio,
        fecha_propuesta=c.fecha_propuesta,
        franja_propuesta=c.franja_propuesta,
        creado_en=c.creado_en,
    )


@router.post(
    "/servicios/{servicio_id}/citas",
    response_model=CitaSalida,
    status_code=status.HTTP_201_CREATED,
)
def pedir_cita(
    servicio_id: int,
    datos: CitaCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    servicio = sesion.execute(
        select(Servicio).where(
            and_(
                Servicio.id == servicio_id,
                Servicio.estado_moderacion == EstadoModeracion.APROBADA.value,
                Servicio.activo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if servicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado"
        )
    if not servicio.acepta_agendamiento:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Este negocio todavía no activó el agendamiento en línea.",
        )

    cita = CitaServicio(
        servicio_id=servicio.id,
        solicitante_usuario_id=usuario.id,
        nombre_contacto=datos.nombre_contacto.strip(),
        telefono_contacto=(datos.telefono_contacto or None),
        vehiculo=(datos.vehiculo or None),
        motivo=datos.motivo,
        fecha=datos.fecha,
        franja=datos.franja,
        nota=(datos.nota or None),
        estado=EstadoCita.SOLICITADA.value,
    )
    sesion.add(cita)
    sesion.commit()
    sesion.refresh(cita)
    cita.servicio = servicio
    return _salida(cita)


@router.get("/citas/mias", response_model=list[CitaSalida])
def mis_citas(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Citas que YO pedí, de la más reciente a la más antigua."""
    filas = (
        sesion.execute(
            select(CitaServicio)
            .options(selectinload(CitaServicio.servicio))
            .where(CitaServicio.solicitante_usuario_id == usuario.id)
            .order_by(CitaServicio.creado_en.desc())
        )
        .scalars()
        .all()
    )
    return [_salida(c) for c in filas]


@router.get("/citas/recibidas", response_model=list[CitaSalida])
def citas_recibidas(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Solicitudes a los servicios que YO aporté (o todas, si soy admin)."""
    consulta = (
        select(CitaServicio)
        .join(Servicio, CitaServicio.servicio_id == Servicio.id)
        .options(selectinload(CitaServicio.servicio))
        .order_by(CitaServicio.creado_en.desc())
    )
    if not es_email_admin(usuario.email):
        consulta = consulta.where(Servicio.aportado_por_usuario_id == usuario.id)
    filas = sesion.execute(consulta).scalars().all()
    return [_salida(c) for c in filas]


def _mi_cita(sesion: Session, cita_id: int, usuario: Usuario) -> CitaServicio:
    cita = sesion.execute(
        select(CitaServicio)
        .options(selectinload(CitaServicio.servicio))
        .where(
            and_(
                CitaServicio.id == cita_id,
                CitaServicio.solicitante_usuario_id == usuario.id,
            )
        )
    ).scalar_one_or_none()
    if cita is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cita no encontrada"
        )
    return cita


@router.patch("/citas/{cita_id}", response_model=CitaSalida)
def actualizar_cita(
    cita_id: int,
    datos: CitaActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El cliente cancela, acepta una reprogramación, o edita fecha/franja/nota
    mientras la cita siga `solicitada`."""
    cita = _mi_cita(sesion, cita_id, usuario)
    cambios = datos.model_dump(exclude_unset=True)

    if cambios.get("estado") == "cancelada":
        if cita.estado in (EstadoCita.RECHAZADA.value, EstadoCita.CANCELADA.value, EstadoCita.CUMPLIDA.value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Esta cita ya está cerrada.",
            )
        cita.estado = EstadoCita.CANCELADA.value
    elif cambios.get("estado") == "confirmada":
        if cita.estado != EstadoCita.REPROGRAMADA.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Solo se acepta una cita reprogramada por el negocio.",
            )
        if cita.fecha_propuesta:
            cita.fecha = cita.fecha_propuesta
        if cita.franja_propuesta:
            cita.franja = cita.franja_propuesta
        cita.fecha_propuesta = None
        cita.franja_propuesta = None
        cita.estado = EstadoCita.CONFIRMADA.value
    else:
        if cita.estado != EstadoCita.SOLICITADA.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Solo puedes editar una cita que todavía está pendiente de respuesta.",
            )
        if "fecha" in cambios:
            cita.fecha = cambios["fecha"]
        if "franja" in cambios:
            cita.franja = cambios["franja"]
        if "nota" in cambios:
            cita.nota = cambios["nota"] or None

    sesion.commit()
    sesion.refresh(cita)
    return _salida(cita)


@router.post("/citas/{cita_id}/responder", response_model=CitaSalida)
def responder_cita(
    cita_id: int,
    datos: RespuestaNegocio,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El negocio (o un admin) confirma / reprograma / rechaza / marca cumplida."""
    cita = sesion.execute(
        select(CitaServicio)
        .options(selectinload(CitaServicio.servicio))
        .where(CitaServicio.id == cita_id)
    ).scalar_one_or_none()
    if cita is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cita no encontrada"
        )
    dueno = cita.servicio and cita.servicio.aportado_por_usuario_id == usuario.id
    if not dueno and not es_email_admin(usuario.email):
        # 404 y no 403: no revelamos que la cita existe a quien no es el negocio.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cita no encontrada"
        )

    if datos.decision == "reprogramada":
        if datos.fecha_propuesta is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Para reprogramar hay que proponer una fecha.",
            )
        cita.fecha_propuesta = datos.fecha_propuesta
        cita.franja_propuesta = datos.franja_propuesta or cita.franja
        cita.estado = EstadoCita.REPROGRAMADA.value
    else:
        cita.estado = EstadoCita(datos.decision).value
        cita.fecha_propuesta = None
        cita.franja_propuesta = None

    if datos.respuesta is not None:
        cita.respuesta_negocio = datos.respuesta.strip() or None

    sesion.commit()
    sesion.refresh(cita)
    return _salida(cita)
