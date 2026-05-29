"""Punto de entrada de la API (monolito modular).

Solo orquesta: fija la política de event loop (Windows + Playwright), crea la app,
configura CORS y monta el router de cada módulo de `src/modules/`. Toda la lógica
de negocio vive en sus módulos respectivos.
"""
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.database import CORS_ORIGINS
from src.modules.auth.router import router as auth_router
from src.modules.tokens.router import router as tokens_router
from src.modules.consulta.routers.consulta import router as consulta_router
from src.modules.consulta.routers.ocr import router as ocr_router
from src.modules.vehiculos.routers.vehiculos import router as vehiculos_router
from src.modules.vehiculos.routers.duenos import router as duenos_router
from src.modules.vehiculos.routers.kilometraje import router as kilometraje_router
from src.modules.vehiculos.routers.mantenimientos import router as mantenimientos_router
from src.modules.vehiculos.routers.favoritos import router as favoritos_router
from src.modules.marketplace.routers.marketplace import router as marketplace_router
from src.modules.marketplace.routers.compartidos import router as compartidos_router

app = FastAPI(title="Consulta de Placas Ecuador")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Consulta pública (incluye / y /health) + OCR
app.include_router(consulta_router)
app.include_router(ocr_router)
# Identidad y billetera
app.include_router(auth_router)
app.include_router(tokens_router)
# Garage privado
app.include_router(vehiculos_router)
app.include_router(duenos_router)
app.include_router(kilometraje_router)
app.include_router(mantenimientos_router)
app.include_router(favoritos_router)
# Compra-venta
app.include_router(marketplace_router)
app.include_router(compartidos_router)
