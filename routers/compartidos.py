"""Enlaces de compra-venta (Fase 4).

- `POST /vehiculos/{vehiculo_id}/compartir`: el dueño genera un enlace temporal
  de solo lectura (requiere JWT y propiedad del vehículo).
- `GET /compartido/{token}`: endpoint público. El portador del token ve el auto
  con `VehiculoSalidaCompartida` (VIN/motor/chasis ofuscados). Token inexistente
  o expirado → 404 (no se distingue de "no es tuyo", para no filtrar existencia).

Solo toca la BD propia; nunca invoca scraping.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import obtener_sesion
from models import Vehiculo, EnlaceCompartido
from schemas.enlace_compartido import EnlaceCompartidoCrear, EnlaceCompartidoSalida
from schemas.vehiculo import VehiculoSalidaCompartida
from auth.dependencies import vehiculo_propio
from services.tokens import debitar_tokens, SaldoInsuficiente


router = APIRouter(tags=["compartir"])

# Costo en tokens de generar un enlace de compra-venta.
# MVP: 0 (gratis) para no poner fricción a la captación de usuarios; el mecanismo
# de débito ya queda cableado y atómico. Subir esta constante activa el cobro sin
# más cambios. Ver reglas de negocio 10.3 (CLAUDE.md).
COSTO_COMPARTIR_TOKENS = 0


@router.post(
    "/vehiculos/{vehiculo_id}/compartir",
    response_model=EnlaceCompartidoSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_enlace_compartido(
    datos: EnlaceCompartidoCrear,
    vehiculo: Vehiculo = Depends(vehiculo_propio),
    sesion: Session = Depends(obtener_sesion),
):
    # Débito + creación del enlace se persisten en un solo commit (atómico): si el
    # saldo no alcanza, no se crea el enlace; si algo falla, el rollback revierte ambos.
    try:
        debitar_tokens(
            sesion, vehiculo.usuario, COSTO_COMPARTIR_TOKENS, motivo="compartir_enlace"
        )
    except SaldoInsuficiente as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    enlace = EnlaceCompartido(
        vehiculo_id=vehiculo.id,
        token=secrets.token_urlsafe(32),
        scope=datos.scope,
        fecha_expiracion=datetime.now(timezone.utc)
        + timedelta(days=datos.dias_validez),
    )
    sesion.add(enlace)
    sesion.commit()
    sesion.refresh(enlace)
    return enlace


@router.get("/compartido/{token}", response_model=VehiculoSalidaCompartida)
def ver_enlace_compartido(
    token: str,
    sesion: Session = Depends(obtener_sesion),
):
    enlace = sesion.execute(
        select(EnlaceCompartido).where(EnlaceCompartido.token == token)
    ).scalar_one_or_none()

    no_encontrado = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Enlace no encontrado o expirado",
    )

    if enlace is None or enlace.fecha_expiracion <= datetime.now(timezone.utc):
        raise no_encontrado

    vehiculo = enlace.vehiculo
    if vehiculo is None or vehiculo.eliminado_en is not None:
        raise no_encontrado

    return VehiculoSalidaCompartida.desde_modelo(vehiculo)
