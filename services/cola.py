"""Encolado de trabajos de scraping para el worker híbrido.

La API (potencialmente en IP de datacenter) no scrapea AMT/FGE directamente: en un
cache miss inserta un trabajo `pendiente` en `cola_scraping` y responde `en_proceso`.
El worker pull-only (IP residencial) lo procesa y guarda el resultado en `consultas`.

Ver docs/arquitectura_hibrida.md. Este módulo solo inserta en la BD propia; no invoca
Playwright.
"""

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models import ColaScraping


def encolar_scraping(sesion: Session, identificador: str, fuente: str) -> None:
    """Encola un trabajo de scraping de forma idempotente.

    Si ya existe un trabajo vivo (pendiente/en_proceso) para el mismo
    identificador+fuente, el INSERT no hace nada (ON CONFLICT DO NOTHING contra el
    índice único parcial `uq_cola_scraping_activa`). Así el polling del cliente no
    duplica trabajos mientras el worker aún no termina.
    """
    stmt = (
        pg_insert(ColaScraping)
        .values(identificador=identificador, fuente=fuente)
        .on_conflict_do_nothing(
            index_elements=["identificador", "fuente"],
            index_where=text("estado IN ('pendiente', 'en_proceso')"),
        )
    )
    sesion.execute(stmt)
    sesion.commit()
