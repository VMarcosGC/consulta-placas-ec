"""Caché de respuestas de fuentes en Postgres, con TTL de doble velocidad.

La caché guarda **una fila JSONB por (placa, fuente)** en `consultas`. El TTL no es
único: depende de la naturaleza del dato de cada fuente.

- **Transaccional** (cambia seguido): multas/citaciones ANT, infracciones AMT, denuncias
  FGE, valores de matrícula. TTL corto (12h) para no servir pendientes obsoletos.
- **Estático** (casi nunca cambia): características del vehículo (marca, modelo, año,
  chasis, motor). TTL largo (90 días).

AS-IS: hoy cada fuente devuelve un solo blob. ANT mezcla estático (características) y
transaccional (citaciones) en el mismo blob, así que se rige por el TTL transaccional
(gana la frescura). `TTL_ESTATICO_MINUTOS` queda **reservado y cableado** para el TO-BE:
cuando el perfil del vehículo se cachee como entrada propia (clientes reales), se le
asigna el TTL largo sin tocar esta lógica. Ver docs/bitacora.md.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database import CACHE_TTL_MINUTOS
from src.modules.consulta.models.consulta import Consulta


ESTADOS_CACHEABLES = {"consulta_realizada", "sin_resultados"}

# TTL por naturaleza del dato (minutos). Overridables por env var.
TTL_TRANSACCIONAL_MINUTOS = int(os.getenv("CACHE_TTL_TRANSACCIONAL_MINUTOS", str(12 * 60)))
TTL_ESTATICO_MINUTOS = int(os.getenv("CACHE_TTL_ESTATICO_MINUTOS", str(90 * 24 * 60)))

# Naturaleza del dato por fuente. Hoy todas las fuentes cacheadas son transaccionales
# (o mixtas que se rigen por la frescura del componente transaccional).
TTL_POR_FUENTE = {
    "ANT": TTL_TRANSACCIONAL_MINUTOS,  # mixto: características (estático) + citaciones (transaccional) → gana frescura
    "AMT": TTL_TRANSACCIONAL_MINUTOS,
    "FGE": TTL_TRANSACCIONAL_MINUTOS,
}


def ttl_para_fuente(fuente: str) -> int:
    """TTL en minutos para una fuente. Fallback a CACHE_TTL_MINUTOS si es desconocida."""
    return TTL_POR_FUENTE.get(fuente, CACHE_TTL_MINUTOS)


def obtener_consulta_reciente(
    sesion: Session,
    placa: str,
    fuente: str,
    ttl_minutos: int | None = None,
) -> dict | None:
    """Devuelve la respuesta cacheada más reciente si está dentro del TTL.

    Si `ttl_minutos` es None se deriva de la fuente (`ttl_para_fuente`). Solo considera
    respuestas con estado consultable (no errores, no stubs). None si no hay caché vigente.
    """
    if ttl_minutos is None:
        ttl_minutos = ttl_para_fuente(fuente)
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
    if fila is None:
        return None
    # `consultado_en` viaja junto a la respuesta para que el consumidor pueda decir
    # "consultado el …" (M2.6: sección "Datos oficiales" del anuncio). Se agrega sobre una
    # COPIA: mutar `fila.respuesta` marcaría el objeto ORM como sucio y lo haría persistir.
    return {**fila.respuesta, "consultado_en": fila.creado_en.isoformat()}


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
