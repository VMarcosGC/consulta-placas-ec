"""Router de microdesbloqueos por tokens (v2): catálogo por placa, desbloqueo y historial.

Endpoints (contrato §6 / respuesta-api-estandar):
- `GET  /consultar/{placa}/productos`            → catálogo con estado para la placa (auth opcional).
- `POST /consultar/{placa}/desbloquear/{codigo}` → desbloquea un producto (cobra tokens).
- `POST /consultar/{placa}/desbloquear`          → alias retrocompatible (identificadores_tecnicos).
- `GET  /consultar/{placa}/desbloqueos`          → historial de desbloqueos del usuario para la placa.

Reutiliza el débito de tokens (402), el consolidador (gateo) y `_obtener_fuentes_placa`.
No scrapea nada nuevo: una fuente caída no rompe la respuesta (la maneja el consolidador).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.core.validators import validar_placa
from src.modules.auth.dependencies import usuario_actual, usuario_actual_opcional
from src.modules.auth.models import Usuario
from src.modules.tokens.service import SaldoInsuficiente
from src.modules.consulta.schemas import (
    DesbloqueoConsultaRequest,
    DesbloqueoConsultaResponse,
    EstadoProductosPlacaResponse,
    VehiculoConsolidadoResponse,
)
from src.modules.consulta.services import desbloqueos as svc
from src.modules.consulta.services.consolidador import consolidar_placa
from src.modules.consulta.services.catalogo_productos import BUNDLE_INCLUYE
from src.modules.consulta.services.proveedor import (
    asegurar_datos_proveedor,
    capacidades_proveedor,
    leer_proveedor_cacheado,
    proveedor_y_costo,
)
from src.modules.consulta.routers.consulta import _obtener_fuentes_placa

logger = logging.getLogger(__name__)

router = APIRouter(tags=["consulta"])

# Productos cuyo dato lo entrega la capa de proveedores (providers/), no el scraping público.
# Al desbloquearlos se invoca al proveedor (con caché) y se cobra SOLO si entrega el dato.
PRODUCTOS_PROVEEDOR = {"identificadores_tecnicos", "titular_validado"}


def _placa(placa: str) -> str:
    try:
        return validar_placa(placa)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _hay_identificadores(datos: dict | None) -> bool:
    """True si el resultado del proveedor trae al menos un identificador técnico."""
    d = datos or {}
    return bool(d.get("vin") or d.get("motor") or d.get("chasis"))


async def _consolidar(
    sesion: Session, placa_limpia: str, usuario: Usuario | None
) -> VehiculoConsolidadoResponse:
    """Consolida el perfil de la placa gateado por los desbloqueos del usuario (si hay).

    Lee el proveedor SOLO de caché (no lo llama): el preview no debe gatillar un cobro externo.
    """
    desbloqueados = (
        svc.productos_desbloqueados(sesion, usuario.id, placa_limpia) if usuario else set()
    )
    catalogo = svc.catalogo_activo(sesion)
    fuentes = await _obtener_fuentes_placa(sesion, placa_limpia)
    return consolidar_placa(
        placa_limpia,
        fuentes,
        desbloqueados,
        catalogo,
        proveedor_datos=leer_proveedor_cacheado(sesion, placa_limpia),
        proveedor_capacidades=capacidades_proveedor(),
    )


@router.get("/consultar/{placa}/productos", response_model=EstadoProductosPlacaResponse)
async def listar_productos(
    placa: str,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario | None = Depends(usuario_actual_opcional),
):
    """Catálogo de productos con su estado (desbloqueado/disponible/tokens) para la placa.

    Auth opcional: con sesión marca lo ya desbloqueado; anónimo → todo `desbloqueado=false`.
    """
    placa_limpia = _placa(placa)
    perfil = await _consolidar(sesion, placa_limpia, usuario)
    return EstadoProductosPlacaResponse(placa=placa_limpia, productos=perfil.productos)


async def _desbloquear(
    sesion: Session, usuario: Usuario, placa_limpia: str, codigo: str
) -> VehiculoConsolidadoResponse:
    """Valida producto + disponibilidad, cobra y devuelve el perfil con la sección revelada.

    400 producto inexistente · 422 producto inactivo · 409 dato no disponible (no cobra) ·
    402 saldo insuficiente · idempotente si ya estaba desbloqueado.
    """
    prod = svc.obtener_producto(sesion, codigo)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Producto desconocido: {codigo!r}"
        )
    if not prod.activo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ese producto está inactivo y no puede desbloquearse.",
        )

    desbloqueados = svc.productos_desbloqueados(sesion, usuario.id, placa_limpia)
    catalogo = svc.catalogo_activo(sesion)
    fuentes = await _obtener_fuentes_placa(sesion, placa_limpia)
    capacidades = capacidades_proveedor()
    proveedor_datos = leer_proveedor_cacheado(sesion, placa_limpia)
    perfil = consolidar_placa(
        placa_limpia, fuentes, desbloqueados, catalogo,
        proveedor_datos=proveedor_datos, proveedor_capacidades=capacidades,
    )

    estado = next((p for p in perfil.productos if p.codigo == codigo), None)
    if estado is None or not estado.disponible:
        # No hay dato que entregar → no se cobra (regla: cobrar solo lo entregado).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese dato no está disponible para esta placa por ahora.",
        )
    if estado.desbloqueado:
        return perfil  # idempotente: ya pagado, no se recobra

    # Si el producto (o el bundle) depende del proveedor y el proveedor puede entregarlo,
    # se invoca AHORA (con caché) para obtener el dato real antes de cobrar.
    proveedor_usado = costo = None
    codigos_a_revisar = {codigo} | set(BUNDLE_INCLUYE.get(codigo, ()))
    if PRODUCTOS_PROVEEDOR & codigos_a_revisar & capacidades:
        proveedor_datos = await asegurar_datos_proveedor(sesion, placa_limpia)
        proveedor_usado, costo = proveedor_y_costo(proveedor_datos)
        # Cobrar solo lo entregado: para un producto-proveedor puntual, exigir su dato.
        if codigo == "identificadores_tecnicos" and not _hay_identificadores(proveedor_datos):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No pudimos obtener los identificadores técnicos para esta placa.",
            )
        if codigo == "titular_validado" and not (proveedor_datos or {}).get("titular"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No pudimos validar el titular para esta placa.",
            )

    try:
        svc.desbloquear(
            sesion, usuario, placa_limpia, prod,
            proveedor_usado=proveedor_usado, costo_estimado=costo,
        )
    except SaldoInsuficiente as e:
        sesion.rollback()
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e))

    desbloqueados = svc.productos_desbloqueados(sesion, usuario.id, placa_limpia)
    return consolidar_placa(
        placa_limpia, fuentes, desbloqueados, catalogo,
        proveedor_datos=proveedor_datos, proveedor_capacidades=capacidades,
    )


@router.post(
    "/consultar/{placa}/desbloquear/{producto_codigo}",
    response_model=VehiculoConsolidadoResponse,
)
async def desbloquear(
    placa: str,
    producto_codigo: str,
    datos: DesbloqueoConsultaRequest | None = None,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Desbloquea un producto del catálogo para esta placa (cobra tokens). Requiere sesión.

    Devuelve el perfil ya con la sección revelada (para que el frontend la pinte sin otra
    llamada). El registro del desbloqueo se ve en `GET /consultar/{placa}/desbloqueos`.
    """
    return await _desbloquear(sesion, usuario, _placa(placa), producto_codigo)


@router.post("/consultar/{placa}/desbloquear", response_model=VehiculoConsolidadoResponse)
async def desbloquear_alias(
    placa: str,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Alias retrocompatible: equivale a desbloquear `identificadores_tecnicos`."""
    return await _desbloquear(sesion, usuario, _placa(placa), "identificadores_tecnicos")


@router.get("/consultar/{placa}/desbloqueos", response_model=list[DesbloqueoConsultaResponse])
def listar_desbloqueos(
    placa: str,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Historial de desbloqueos del usuario para esta placa (auditoría comercial)."""
    return svc.listar_desbloqueos(sesion, usuario.id, _placa(placa))
