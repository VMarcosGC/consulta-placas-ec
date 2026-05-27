"""Launcher de la API.

Razón de existir: Playwright lanza Chromium como subprocess. En Windows, asyncio
solo soporta subprocess con WindowsProactorEventLoopPolicy.

Problema 1: Si se corre `uvicorn main:app --reload`, el worker subprocess no hereda
la política configurada en main.py.

Problema 2 (uvicorn 0.32+): incluso lanzando programáticamente, uvicorn corre
`asyncio_setup()` que en Windows fuerza WindowsSelectorEventLoopPolicy ANTES de
crear el loop.

Solución:
1. Fijar WindowsProactorEventLoopPolicy.
2. Monkey-patchear `uvicorn.loops.asyncio.asyncio_setup` a no-op.
3. Arrancar uvicorn sin --reload por default.

Variables de entorno soportadas (útiles en hosting tipo Render/Fly):
  HOST              — host a bindear. Default `127.0.0.1` en local, `0.0.0.0` en prod.
  PORT              — puerto. Default `8000`. Render asigna este valor en runtime.
  UVICORN_RELOAD    — `1` para reload en dev (no usar con Playwright).
"""

import os
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    import uvicorn.loops.asyncio as _uv_asyncio_loop

    def _asyncio_setup_noop(use_subprocess: bool = False) -> None:
        return None

    _uv_asyncio_loop.asyncio_setup = _asyncio_setup_noop

import uvicorn


def _diagnostico_loop() -> None:
    politica = type(asyncio.get_event_loop_policy()).__name__
    print(f"[run.py] Event loop policy activa: {politica}")
    if sys.platform == "win32" and "Proactor" not in politica:
        print(
            "[run.py] ADVERTENCIA: en Windows se necesita WindowsProactorEventLoopPolicy "
            "para que Playwright lance Chromium. Las consultas a fuentes externas van a fallar."
        )


if __name__ == "__main__":
    _diagnostico_loop()
    host = os.getenv("HOST", "127.0.0.1")
    puerto = int(os.getenv("PORT", "8000"))
    reload = os.getenv("UVICORN_RELOAD") == "1"
    print(f"[run.py] Iniciando uvicorn en {host}:{puerto} (reload={reload})")
    uvicorn.run(
        "main:app",
        host=host,
        port=puerto,
        reload=reload,
        log_level="info",
    )
