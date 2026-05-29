from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.consulta.models.consulta import Consulta


ESTADOS_CACHEABLES = {"consulta_realizada", "sin_resultados"}


def obtener_consulta_reciente(
    sesion: Session,
    placa: str,
    fuente: str,
    ttl_minutos: int,
) -> dict | None:
    """Devuelve la respuesta cacheada más reciente si está dentro del TTL.

    Solo considera respuestas con estado consultable (no errores, no stubs).
    Devuelve None si no hay caché vigente.
    """
    desde = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutos)

    stmt = (
        select(Consulta)
        .where(
            Consulta.placa == placa,
            Consulta.fuente == fuente,
            Consulta.estado.in_(ESTADOS_CACHEABLES),
            Consulta.creado_en >= desde,
        )
        .order_by(Consulta.creado_en.desc())
        .limit(1)
    )

    fila = sesion.execute(stmt).scalar_one_or_none()
    return fila.respuesta if fila else None


def guardar_consulta(
    sesion: Session,
    placa: str,
    fuente: str,
    respuesta: dict,
) -> None:
    """Persiste la respuesta de un servicio si su estado es cacheable.

    Errores y stubs no se guardan: la fuente puede volver y queremos reintentar.
    """
    estado = respuesta.get("estado", "")

    if estado not in ESTADOS_CACHEABLES:
        return

    registro = Consulta(
        placa=placa,
        fuente=fuente,
        estado=estado,
        respuesta=respuesta,
    )
    sesion.add(registro)
    sesion.commit()
