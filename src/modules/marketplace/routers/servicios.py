"""Directorio de servicios automotrices (talleres, lavaderos, luces, accesorios…).

Un usuario propone un negocio; entra `pendiente` y un admin lo aprueba antes de que
salga en el directorio público — mismo patrón que `PublicacionReferenciada`. El
frontend mezcla lo aprobado con su lista demo hasta que haya volumen real.

Solo BD propia (§10.2). Gratis (§1.0.3).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace import geografia
from src.modules.marketplace.models import EstadoModeracion, Servicio
from src.modules.marketplace.schemas import (
    CategoriaServicio,
    ModeracionServicio,
    ServicioCrear,
    ServicioSalida,
)

router = APIRouter(prefix="/marketplace/servicios", tags=["marketplace"])

MAX_LISTA = 200


@router.post("", response_model=ServicioSalida, status_code=status.HTTP_201_CREATED)
def crear_servicio(
    datos: ServicioCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Propone un negocio para el directorio. Entra `pendiente`. Requiere sesión."""
    s = Servicio(
        nombre=datos.nombre.strip(),
        categoria=datos.categoria,
        provincia=datos.provincia,
        ciudad=datos.ciudad.strip(),
        descripcion=(datos.descripcion or None),
        telefono=(datos.telefono or None),
        whatsapp=(datos.whatsapp or None),
        direccion=(datos.direccion or None),
        horario=(datos.horario or None),
        url_externa=(datos.url_externa or None),
        acepta_agendamiento=datos.acepta_agendamiento,
        aportado_por_usuario_id=usuario.id,
    )
    sesion.add(s)
    sesion.commit()
    sesion.refresh(s)
    return ServicioSalida.model_validate(s)


@router.get("", response_model=list[ServicioSalida])
def listar_servicios(
    sesion: Session = Depends(obtener_sesion),
    categoria: CategoriaServicio | None = None,
    provincia: str | None = None,
):
    """Directorio PÚBLICO: solo aprobados y activos. Filtros opcionales."""
    condiciones = [
        Servicio.estado_moderacion == EstadoModeracion.APROBADA.value,
        Servicio.activo.is_(True),
    ]
    if categoria is not None:
        condiciones.append(Servicio.categoria == categoria)
    if provincia is not None:
        if provincia not in geografia.PROVINCIAS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Provincia no válida. Opciones: {list(geografia.PROVINCIAS)}.",
            )
        condiciones.append(Servicio.provincia == provincia)

    filas = (
        sesion.execute(
            select(Servicio)
            .where(and_(*condiciones))
            .order_by(Servicio.certificado.desc(), Servicio.creado_en.desc())
            .limit(MAX_LISTA)
        )
        .scalars()
        .all()
    )
    return [ServicioSalida.model_validate(s) for s in filas]


@router.get("/pendientes", response_model=list[ServicioSalida])
def servicios_pendientes(
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(admin_actual),
):
    """Cola de moderación. Solo admin."""
    filas = (
        sesion.execute(
            select(Servicio)
            .where(Servicio.estado_moderacion == EstadoModeracion.PENDIENTE.value)
            .order_by(Servicio.creado_en.asc())
        )
        .scalars()
        .all()
    )
    return [ServicioSalida.model_validate(s) for s in filas]


@router.post("/{servicio_id}/moderar", response_model=ServicioSalida)
def moderar_servicio(
    servicio_id: int,
    datos: ModeracionServicio,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(admin_actual),
):
    """Aprueba o rechaza un servicio; opcionalmente lo marca `certificado`. Solo admin."""
    s = sesion.execute(
        select(Servicio).where(Servicio.id == servicio_id)
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado"
        )
    s.estado_moderacion = datos.decision.value
    if datos.certificado is not None:
        s.certificado = datos.certificado
    sesion.commit()
    sesion.refresh(s)
    return ServicioSalida.model_validate(s)
