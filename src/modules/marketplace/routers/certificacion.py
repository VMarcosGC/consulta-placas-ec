"""Sello "revisado por mecánica" (migración 0028).

Flujo pensado para que el sello NO se desvalorice:
 1. Un ADMIN genera N códigos de un solo uso para una mecánica concreta
    (`POST /marketplace/certificacion/codigos`). La plataforma decide qué mecánicas
    reciben códigos; en la etapa 2 las mecánicas con cuenta los emitirán solas.
 2. La mecánica revisa el auto y le entrega UN código al vendedor.
 3. El vendedor lo canjea en SU publicación
    (`POST /marketplace/publicaciones/{id}/certificar`). El sello guarda el nombre de la
    mecánica y la fecha — específico y rastreable, distinto del "Verificado por la
    plataforma" (§10.6).

Un código se canjea una vez y expira. Solo BD propia (§10.2). Gratis (§1.0.3).
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import CodigoCertificacion, PublicacionInterna
from src.modules.marketplace.schemas import (
    CertificarConCodigo,
    CodigoCertificacionSalida,
    CodigosCertificacionCrear,
    PublicacionInternaSalida,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

# Alfabeto sin caracteres ambiguos (0/O, 1/I/L). El código se dicta por teléfono.
_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
MAX_LISTA_CODIGOS = 100


def _generar_codigo() -> str:
    cuerpo = "".join(secrets.choice(_ALFABETO) for _ in range(8))
    return f"MEC-{cuerpo[:4]}-{cuerpo[4:]}"


@router.post(
    "/certificacion/codigos",
    response_model=list[CodigoCertificacionSalida],
    status_code=status.HTTP_201_CREATED,
)
def crear_codigos(
    datos: CodigosCertificacionCrear,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(admin_actual),
):
    """Genera `cantidad` códigos para una mecánica. Solo admin."""
    expira = datetime.now(timezone.utc) + timedelta(days=datos.dias_validez)
    nuevos: list[CodigoCertificacion] = []
    for _ in range(datos.cantidad):
        c = CodigoCertificacion(
            codigo=_generar_codigo(),
            mecanica_nombre=datos.mecanica_nombre.strip(),
            mecanica_ciudad=datos.mecanica_ciudad.strip(),
            emitido_por_usuario_id=admin.id,
            expira_en=expira,
        )
        sesion.add(c)
        nuevos.append(c)
    sesion.commit()
    for c in nuevos:
        sesion.refresh(c)
    return [CodigoCertificacionSalida.model_validate(c) for c in nuevos]


@router.get(
    "/certificacion/codigos", response_model=list[CodigoCertificacionSalida]
)
def listar_codigos(
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(admin_actual),
):
    """Últimos códigos emitidos (usados y sin usar). Solo admin."""
    filas = (
        sesion.execute(
            select(CodigoCertificacion)
            .order_by(CodigoCertificacion.creado_en.desc())
            .limit(MAX_LISTA_CODIGOS)
        )
        .scalars()
        .all()
    )
    return [CodigoCertificacionSalida.model_validate(c) for c in filas]


@router.post(
    "/publicaciones/{publicacion_id}/certificar",
    response_model=PublicacionInternaSalida,
)
def certificar_publicacion(
    publicacion_id: int,
    datos: CertificarConCodigo,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El vendedor canjea el código de la mecánica en su publicación.

    - 404 si la publicación no es suya.
    - 422 si el código no existe, ya se usó o expiró.
    - Idempotente por publicación: si ya tiene sello de la MISMA mecánica, no reclama
      otro código (evita quemar códigos por doble clic).
    """
    pub = sesion.execute(
        select(PublicacionInterna).where(
            PublicacionInterna.id == publicacion_id,
            PublicacionInterna.usuario_id == usuario.id,
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada"
        )

    codigo = (datos.codigo or "").strip().upper()
    fila = sesion.execute(
        select(CodigoCertificacion).where(CodigoCertificacion.codigo == codigo)
    ).scalar_one_or_none()
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El código no existe. Revisa que lo escribiste bien.",
        )

    ahora = datetime.now(timezone.utc)
    if pub.mecanica_nombre == fila.mecanica_nombre and pub.certificado_mecanica_en:
        return PublicacionInternaSalida.desde_modelo(pub)  # ya sellada por esta mecánica

    if fila.usado_en is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ese código ya se usó.",
        )
    if fila.expira_en <= ahora:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ese código ya expiró. Pídele uno nuevo a la mecánica.",
        )

    fila.usado_en = ahora
    fila.usado_publicacion_id = pub.id
    pub.mecanica_nombre = fila.mecanica_nombre
    pub.mecanica_ciudad = fila.mecanica_ciudad
    pub.certificado_mecanica_en = ahora
    sesion.commit()
    sesion.refresh(pub)
    return PublicacionInternaSalida.desde_modelo(pub)
