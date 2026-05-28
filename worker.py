"""Worker híbrido de scraping (pull-only).

Procesa la cola `cola_scraping` desde una máquina con IP residencial ecuatoriana,
ejecuta los servicios de `services/` (que AMT/FGE bloquean desde IPs de datacenter)
y guarda los resultados en la caché `consultas`. La API en Render lee de ahí.

Diseño completo: docs/arquitectura_hibrida.md.

Características:
- Toma trabajos con SELECT ... FOR UPDATE SKIP LOCKED → varios workers concurrentes
  sin pisarse, sin broker externo.
- Reintentos con backoff exponencial; al agotar `max_intentos` → estado `fallido`.
- Rescate de zombis: trabajos `en_proceso` huérfanos (worker caído) vuelven a la cola.
- Apagado limpio: termina el trabajo en curso y cierra antes de salir.
- Manejo exhaustivo de excepciones: ningún trabajo defectuoso tumba el loop.

Uso:
    python worker.py

Variables de entorno (además de DATABASE_URL, compartida con la API):
    WORKER_POLL_SEGUNDOS          intervalo de sondeo cuando la cola está vacía (default 5)
    WORKER_BACKOFF_BASE_SEGUNDOS  base del backoff exponencial (default 30)
    WORKER_TIMEOUT_ZOMBI_SEGUNDOS antigüedad para considerar zombi un en_proceso (default 300)
"""

import os
import sys
import signal
import asyncio
import logging
from datetime import datetime, timedelta, timezone

# Playwright lanza Chromium como subprocess: en Windows requiere Proactor (ver run.py).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from sqlalchemy import select, update, text

from database import SessionLocal
from models import ColaScraping
from models.cola_scraping import (
    ESTADO_PENDIENTE,
    ESTADO_EN_PROCESO,
    ESTADO_COMPLETADO,
    ESTADO_FALLIDO,
)
from services.cache import guardar_consulta, ESTADOS_CACHEABLES
from services.ant import consultar_ant
from services.amt import consultar_amt
from services.fiscalia import consultar_fiscalia
from services.sri import consultar_sri


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
logger = logging.getLogger("worker")

POLL_SEGUNDOS = int(os.getenv("WORKER_POLL_SEGUNDOS", "5"))
BACKOFF_BASE_SEGUNDOS = int(os.getenv("WORKER_BACKOFF_BASE_SEGUNDOS", "30"))
TIMEOUT_ZOMBI_SEGUNDOS = int(os.getenv("WORKER_TIMEOUT_ZOMBI_SEGUNDOS", "300"))

# fuente (código corto del contrato) → función de scraping.
CONSULTORES = {
    "ANT": consultar_ant,
    "AMT": consultar_amt,
    "FGE": consultar_fiscalia,
    "SRI": consultar_sri,
}

# Señal de apagado limpio; se setea con SIGINT/SIGTERM.
_detener = asyncio.Event()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def rescatar_zombis() -> int:
    """Devuelve a `pendiente` los trabajos `en_proceso` cuyo worker murió a mitad.

    Un trabajo se considera huérfano si lleva en_proceso más que el timeout. Su
    `intentos` ya fue incrementado al tomarse, así que no entra en bucle infinito.
    """
    limite = _ahora() - timedelta(seconds=TIMEOUT_ZOMBI_SEGUNDOS)
    with SessionLocal() as sesion:
        try:
            resultado = sesion.execute(
                update(ColaScraping)
                .where(
                    ColaScraping.estado == ESTADO_EN_PROCESO,
                    ColaScraping.tomado_en < limite,
                )
                .values(estado=ESTADO_PENDIENTE, tomado_en=None)
            )
            sesion.commit()
            return resultado.rowcount or 0
        except Exception as e:
            sesion.rollback()
            logger.warning("Rescate de zombis falló: %r", e)
            return 0


def tomar_trabajo() -> dict | None:
    """Reclama el siguiente trabajo elegible de forma atómica.

    En una sola transacción: SELECT ... FOR UPDATE SKIP LOCKED, márcalo en_proceso e
    incrementa intentos. Al commitear se libera el lock y, como ya no está pendiente,
    ningún otro worker lo vuelve a tomar.

    Devuelve un dict plano (desligado de la sesión) con los datos del trabajo, o None.
    """
    with SessionLocal() as sesion:
        try:
            trabajo = sesion.execute(
                select(ColaScraping)
                .where(
                    ColaScraping.estado == ESTADO_PENDIENTE,
                    ColaScraping.disponible_en <= _ahora(),
                )
                .order_by(ColaScraping.disponible_en)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()

            if trabajo is None:
                return None

            trabajo.estado = ESTADO_EN_PROCESO
            trabajo.tomado_en = _ahora()
            trabajo.intentos += 1
            datos = {
                "id": trabajo.id,
                "identificador": trabajo.identificador,
                "fuente": trabajo.fuente,
                "intentos": trabajo.intentos,
                "max_intentos": trabajo.max_intentos,
            }
            sesion.commit()
            return datos
        except Exception as e:
            sesion.rollback()
            logger.warning("No se pudo tomar trabajo: %r", e)
            return None


def marcar_completado(trabajo_id: int) -> None:
    _actualizar_estado(trabajo_id, estado=ESTADO_COMPLETADO, error=None, disponible_en=None)


def reprogramar_o_fallar(trabajo: dict, error: str) -> None:
    """Tras un fallo: reprograma con backoff si quedan intentos; si no, marca fallido."""
    if trabajo["intentos"] >= trabajo["max_intentos"]:
        logger.warning(
            "Trabajo %s (%s/%s) agotó reintentos → fallido",
            trabajo["id"], trabajo["fuente"], trabajo["identificador"],
        )
        _actualizar_estado(trabajo["id"], estado=ESTADO_FALLIDO, error=error, disponible_en=None)
        return

    espera = BACKOFF_BASE_SEGUNDOS * (2 ** (trabajo["intentos"] - 1))
    proximo = _ahora() + timedelta(seconds=espera)
    logger.info(
        "Trabajo %s (%s/%s) reprogramado en %ss (intento %s/%s)",
        trabajo["id"], trabajo["fuente"], trabajo["identificador"],
        espera, trabajo["intentos"], trabajo["max_intentos"],
    )
    _actualizar_estado(
        trabajo["id"], estado=ESTADO_PENDIENTE, error=error, disponible_en=proximo
    )


def _actualizar_estado(
    trabajo_id: int, estado: str, error: str | None, disponible_en: datetime | None
) -> None:
    valores = {"estado": estado, "error": error, "tomado_en": None}
    if disponible_en is not None:
        valores["disponible_en"] = disponible_en
    with SessionLocal() as sesion:
        try:
            sesion.execute(
                update(ColaScraping).where(ColaScraping.id == trabajo_id).values(**valores)
            )
            sesion.commit()
        except Exception as e:
            sesion.rollback()
            logger.error("No se pudo actualizar estado de trabajo %s: %r", trabajo_id, e)


def guardar_resultado(identificador: str, fuente: str, respuesta: dict) -> None:
    """Persiste el resultado en la caché `consultas` (reusa la regla de cacheabilidad)."""
    with SessionLocal() as sesion:
        try:
            guardar_consulta(sesion, identificador, fuente, respuesta)
        except Exception as e:
            sesion.rollback()
            logger.warning(
                "No se pudo cachear %s/%s: %r", fuente, identificador, e
            )


async def procesar(trabajo: dict) -> None:
    """Ejecuta el scraping de un trabajo ya reclamado y resuelve su estado final."""
    fuente = trabajo["fuente"]
    identificador = trabajo["identificador"]
    consultar = CONSULTORES.get(fuente)

    if consultar is None:
        reprogramar_o_fallar(trabajo, error=f"Fuente desconocida: {fuente!r}")
        return

    logger.info("Procesando %s/%s (intento %s)", fuente, identificador, trabajo["intentos"])

    # El servicio ya captura todo y devuelve {estado: error}; este try es defensa extra.
    try:
        respuesta = await consultar(identificador)
    except Exception as e:
        reprogramar_o_fallar(trabajo, error=repr(e))
        return

    estado_respuesta = (respuesta or {}).get("estado")
    if estado_respuesta in ESTADOS_CACHEABLES:
        guardar_resultado(identificador, fuente, respuesta)
        marcar_completado(trabajo["id"])
        logger.info("Completado %s/%s → %s", fuente, identificador, estado_respuesta)
    else:
        # error, bloqueado_captcha, pendiente_integracion: reintentable / no cacheable.
        reprogramar_o_fallar(
            trabajo, error=(respuesta or {}).get("error") or f"estado={estado_respuesta}"
        )


async def loop_principal() -> None:
    logger.info(
        "Worker iniciado · poll=%ss · backoff_base=%ss · timeout_zombi=%ss",
        POLL_SEGUNDOS, BACKOFF_BASE_SEGUNDOS, TIMEOUT_ZOMBI_SEGUNDOS,
    )
    while not _detener.is_set():
        try:
            rescatados = rescatar_zombis()
            if rescatados:
                logger.info("Rescatados %s trabajos zombi", rescatados)

            trabajo = tomar_trabajo()
            if trabajo is None:
                # Cola vacía: dormir el intervalo, pero despertar si llega el apagado.
                try:
                    await asyncio.wait_for(_detener.wait(), timeout=POLL_SEGUNDOS)
                except asyncio.TimeoutError:
                    pass
                continue

            await procesar(trabajo)
        except Exception as e:
            # Blindaje final: nada debe romper el loop.
            logger.exception("Error inesperado en el loop: %r", e)
            await asyncio.sleep(POLL_SEGUNDOS)

    logger.info("Worker detenido limpiamente")


def _instalar_senales(loop: asyncio.AbstractEventLoop) -> None:
    def _pedir_detener():
        logger.info("Señal de apagado recibida; terminando el trabajo en curso...")
        _detener.set()

    for nombre in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, nombre, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _pedir_detener)
        except NotImplementedError:
            # Windows no soporta add_signal_handler para SIGTERM; SIGINT llega como
            # KeyboardInterrupt y se maneja en main().
            pass


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _instalar_senales(loop)
    try:
        loop.run_until_complete(loop_principal())
    except KeyboardInterrupt:
        logger.info("Interrupción de teclado; saliendo")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
