"""Encolado y lectura de estado de trabajos de scraping (worker híbrido).

La API (potencialmente en IP de datacenter) no scrapea AMT/FGE directamente: en un
cache miss inserta un trabajo `pendiente` en `cola_scraping` y responde `en_proceso`.
El worker pull-only (IP residencial) lo procesa y guarda el resultado en `consultas`.

Ver docs/arquitectura_hibrida.md. Este módulo solo lee/escribe la BD propia; no invoca
Playwright.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.modules.consulta.models.cola_scraping import (
    ColaScraping,
    ESTADO_ERROR_FUENTE,
    MAX_INTENTOS_DEFAULT,
)


def encolar_scraping(
    sesion: Session,
    identificador: str,
    fuente: str,
    max_intentos: int = MAX_INTENTOS_DEFAULT,
) -> None:
    """Encola un trabajo de scraping de forma idempotente.

    Si ya existe un trabajo vivo (pendiente/en_proceso) para el mismo
    identificador+fuente, el INSERT no hace nada (ON CONFLICT DO NOTHING contra el
    índice único parcial `uq_cola_scraping_activa`). Así el polling del cliente no
    duplica trabajos mientras el worker aún no termina.

    Un trabajo `error_fuente` previo NO bloquea (no es activo): un reintento explícito
    inserta una fila nueva y el worker la vuelve a procesar.
    """
    stmt = (
        pg_insert(ColaScraping)
        .values(identificador=identificador, fuente=fuente, max_intentos=max_intentos)
        .on_conflict_do_nothing(
            index_elements=["identificador", "fuente"],
            index_where=text("estado IN ('pendiente', 'en_proceso')"),
        )
    )
    sesion.execute(stmt)
    sesion.commit()


def estado_trabajo_reciente(
    sesion: Session, identificador: str, fuente: str
) -> dict | None:
    """Devuelve `{estado, error, actualizado_en}` del trabajo más reciente, o None.

    La API lo usa en un cache miss para decidir si la fuente quedó caída
    (`error_fuente`) y debe informarlo al cliente en vez de re-encolar a ciegas.
    """
    fila = sesion.execute(
        select(
            ColaScraping.estado,
            ColaScraping.error,
            ColaScraping.actualizado_en,
        )
        .where(
            ColaScraping.identificador == identificador,
            ColaScraping.fuente == fuente,
        )
        .order_by(ColaScraping.creado_en.desc())
        .limit(1)
    ).first()

    if fila is None:
        return None
    return {"estado": fila.estado, "error": fila.error, "actualizado_en": fila.actualizado_en}


def fuente_en_error_reciente(
    sesion: Session,
    identificador: str,
    fuente: str,
    ventana_minutos: int,
) -> str | None:
    """Si el último trabajo terminó en `error_fuente` dentro de la ventana, devuelve su error.

    Devuelve el repr del error (str, puede ser "") para que la API responda
    `error_fuente`; devuelve None si no aplica (no hay trabajo, no es error, o ya
    venció la ventana de enfriamiento → conviene reintentar automáticamente).
    """
    reciente = estado_trabajo_reciente(sesion, identificador, fuente)
    if reciente is None or reciente["estado"] != ESTADO_ERROR_FUENTE:
        return None

    actualizado = reciente["actualizado_en"]
    if actualizado is not None:
        if actualizado.tzinfo is None:
            actualizado = actualizado.replace(tzinfo=timezone.utc)
        limite = datetime.now(timezone.utc) - timedelta(minutes=ventana_minutos)
        if actualizado < limite:
            return None  # enfriamiento vencido: dejar que se re-encole solo

    return reciente["error"] or ""
