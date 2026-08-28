"""Calificaciones de un COMPRADOR a un VENDEDOR (1..5 estrellas + comentario).

Solo esa dirección: el contacto es anónimo (`ContactoRevelado` no guarda quién pidió el
número), así que un vendedor no puede identificar ni calificar a un comprador. Cuando
exista un flujo de contacto que identifique al comprador se agrega la inversa.

Una calificación por (comprador, vendedor): volver a calificar la ACTUALIZA (upsert),
no acumula. Nadie califica su propio perfil de vendedor. Solo BD propia (§10.2).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual, usuario_actual_opcional
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import Calificacion, Vendedor
from src.modules.marketplace.schemas import (
    CalificacionCrear,
    CalificacionSalida,
    CalificacionesVendedorSalida,
    ResumenCalificaciones,
)

router = APIRouter(prefix="/marketplace/vendedores", tags=["marketplace"])

# Cuántos comentarios se devuelven en el listado público (los más recientes).
MAX_COMENTARIOS = 20


def _autor_nombre(u: Usuario | None) -> str:
    """Primer nombre del autor, o 'Un comprador'. Nunca el email ni el id (§9)."""
    nombre = (getattr(u, "nombre", None) or "").strip()
    return nombre.split(" ")[0] if nombre else "Un comprador"


def resumen_calificaciones(sesion: Session, vendedor_id: int) -> ResumenCalificaciones:
    """Promedio (1 decimal) y conteo. Promedio `None` si no hay ninguna — línea base:
    sin calificaciones NO se muestra una nota baja, simplemente no hay nota."""
    prom, total = sesion.execute(
        select(func.avg(Calificacion.estrellas), func.count()).where(
            Calificacion.vendedor_id == vendedor_id
        )
    ).one()
    return ResumenCalificaciones(
        promedio=round(float(prom), 1) if prom is not None else None,
        total=int(total or 0),
    )


def _vendedor(sesion: Session, vendedor_id: int) -> Vendedor:
    v = sesion.execute(
        select(Vendedor).where(Vendedor.id == vendedor_id)
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vendedor no encontrado"
        )
    return v


@router.post("/{vendedor_id}/calificar", response_model=CalificacionesVendedorSalida)
def calificar_vendedor(
    vendedor_id: int,
    datos: CalificacionCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Deja (o actualiza) tu calificación a este vendedor. Requiere sesión.

    - 404 si el vendedor no existe.
    - 422 si es tu propio perfil de vendedor (no te calificas a ti mismo).
    - Idempotente por (autor, vendedor): re-calificar reemplaza estrellas y comentario.
    """
    vendedor = _vendedor(sesion, vendedor_id)
    if vendedor.usuario_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No puedes calificar tu propio perfil de vendedor.",
        )

    existente = sesion.execute(
        select(Calificacion).where(
            Calificacion.autor_usuario_id == usuario.id,
            Calificacion.vendedor_id == vendedor_id,
        )
    ).scalar_one_or_none()

    if existente is None:
        sesion.add(
            Calificacion(
                autor_usuario_id=usuario.id,
                vendedor_id=vendedor_id,
                publicacion_interna_id=datos.publicacion_id,
                estrellas=datos.estrellas,
                comentario=datos.comentario,
            )
        )
    else:
        existente.estrellas = datos.estrellas
        existente.comentario = datos.comentario
        if datos.publicacion_id is not None:
            existente.publicacion_interna_id = datos.publicacion_id
    sesion.commit()

    return _listado(sesion, vendedor_id, usuario)


@router.get("/{vendedor_id}/calificaciones", response_model=CalificacionesVendedorSalida)
def calificaciones_vendedor(
    vendedor_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario | None = Depends(usuario_actual_opcional),
):
    """Resumen + últimos comentarios. Público. Si hay sesión, `mia` trae tu propia
    calificación (para prellenar el formulario)."""
    _vendedor(sesion, vendedor_id)
    return _listado(sesion, vendedor_id, usuario)


def _listado(
    sesion: Session, vendedor_id: int, usuario: Usuario | None
) -> CalificacionesVendedorSalida:
    filas = sesion.execute(
        select(Calificacion, Usuario)
        .join(Usuario, Usuario.id == Calificacion.autor_usuario_id)
        .where(Calificacion.vendedor_id == vendedor_id)
        .order_by(Calificacion.creado_en.desc())
        .limit(MAX_COMENTARIOS)
    ).all()

    items = [
        CalificacionSalida(
            estrellas=c.estrellas,
            comentario=c.comentario,
            autor=_autor_nombre(u),
            creado_en=c.creado_en,
        )
        for c, u in filas
    ]

    mia: CalificacionSalida | None = None
    if usuario is not None:
        propia = next(
            (c for c, _ in filas if c.autor_usuario_id == usuario.id), None
        )
        if propia is None:
            propia = sesion.execute(
                select(Calificacion).where(
                    Calificacion.autor_usuario_id == usuario.id,
                    Calificacion.vendedor_id == vendedor_id,
                )
            ).scalar_one_or_none()
        if propia is not None:
            mia = CalificacionSalida(
                estrellas=propia.estrellas,
                comentario=propia.comentario,
                autor=_autor_nombre(usuario),
                creado_en=propia.creado_en,
            )

    return CalificacionesVendedorSalida(
        resumen=resumen_calificaciones(sesion, vendedor_id),
        items=items,
        mia=mia,
    )
