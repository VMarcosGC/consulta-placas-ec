"""Chat interno comprador↔vendedor sobre una publicación (migración 0035).

Marcos (2026-09-02): el comprador y el vendedor hablan DENTRO de CarStore. El
WhatsApp del vendedor no se entrega hasta que él responde en este chat (o comparte
su contacto a mano) — la barrera vive en `POST /publicaciones/{id}/contacto`, acá
solo se marca `Conversacion.contacto_habilitado_en`.

- Comprador: `POST /publicaciones/{id}/conversacion` abre (o reusa) el hilo;
  `POST /conversaciones/{id}/mensajes` escribe.
- Vendedor: ve la bandeja en `GET /conversaciones`, responde igual, y puede
  `POST /conversaciones/{id}/compartir-contacto` o `PATCH` a `bloqueada`.

Solo BD propia (§10.2). Gratis (§1.0.3). Texto plano, sin adjuntos.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    Conversacion,
    EstadoConversacion,
    EstadoPublicacion,
    Mensaje,
    PublicacionInterna,
    RolConversacion,
    Vendedor,
)
from src.modules.marketplace.schemas import (
    ConversacionCrear,
    ConversacionResumenSalida,
    ConversacionSalida,
    EstadoConversacionPatch,
    MensajeCrear,
    MensajeSalida,
)

router = APIRouter(prefix="/marketplace", tags=["chat"])


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _vendedor_de(sesion: Session, pub: PublicacionInterna) -> Vendedor | None:
    """El vendedor de una publicación por su vínculo explícito `vendedor_id` (igual
    criterio que `publicaciones.py`: NO se cae al atajo por `usuario_id`)."""
    if pub.vendedor_id is None:
        return None
    return sesion.execute(
        select(Vendedor).where(Vendedor.id == pub.vendedor_id)
    ).scalar_one_or_none()


def _portada(pub: PublicacionInterna) -> str | None:
    fotos = sorted(pub.fotos, key=lambda f: f.orden) if pub.fotos else []
    return fotos[0].url if fotos else None


def _contraparte_nombre(conv: Conversacion, mi_rol: RolConversacion) -> str:
    if mi_rol == RolConversacion.COMPRADOR:
        vend = getattr(conv.publicacion, "vendedor", None)
        return (vend.nombre_publico if vend and vend.nombre_publico else "El vendedor")
    comp = getattr(conv, "comprador", None)
    return (comp.nombre if comp and comp.nombre else "Comprador")


def _rol_de(conv: Conversacion, usuario: Usuario) -> RolConversacion | None:
    if conv.comprador_usuario_id == usuario.id:
        return RolConversacion.COMPRADOR
    if conv.vendedor_usuario_id == usuario.id:
        return RolConversacion.VENDEDOR
    return None


def _mensaje_salida(m: Mensaje, usuario: Usuario) -> MensajeSalida:
    return MensajeSalida(
        id=m.id,
        rol_autor=RolConversacion(m.rol_autor),
        cuerpo=m.cuerpo,
        mio=m.autor_usuario_id == usuario.id,
        leido_en=m.leido_en,
        creado_en=m.creado_en,
    )


def _conversacion_salida(
    conv: Conversacion, mi_rol: RolConversacion, usuario: Usuario
) -> ConversacionSalida:
    return ConversacionSalida(
        id=conv.id,
        publicacion_id=conv.publicacion_interna_id,
        publicacion_titulo=(conv.publicacion.titulo or conv.publicacion.placa),
        publicacion_foto=_portada(conv.publicacion),
        publicacion_precio=conv.publicacion.precio_usd,
        contraparte_nombre=_contraparte_nombre(conv, mi_rol),
        mi_rol=mi_rol,
        estado=EstadoConversacion(conv.estado),
        contacto_habilitado=conv.contacto_habilitado_en is not None,
        puede_bloquear=mi_rol == RolConversacion.VENDEDOR,
        mensajes=[_mensaje_salida(m, usuario) for m in conv.mensajes],
    )


def _cargar_para_participante(
    sesion: Session, conversacion_id: int, usuario: Usuario
) -> tuple[Conversacion, RolConversacion]:
    conv = sesion.execute(
        select(Conversacion)
        .options(
            selectinload(Conversacion.mensajes),
            selectinload(Conversacion.publicacion).selectinload(PublicacionInterna.fotos),
            selectinload(Conversacion.publicacion).selectinload(PublicacionInterna.vendedor),
            selectinload(Conversacion.comprador),
        )
        .where(Conversacion.id == conversacion_id)
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
    rol = _rol_de(conv, usuario)
    if rol is None:
        # 404 y no 403: no revelamos que el hilo existe a un tercero.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
    return conv, rol


def _marcar_leidos(conv: Conversacion, mi_rol: RolConversacion) -> None:
    """Marca como leídos los mensajes de la contraparte y pone en 0 mi contador."""
    otro = (
        RolConversacion.VENDEDOR
        if mi_rol == RolConversacion.COMPRADOR
        else RolConversacion.COMPRADOR
    )
    ahora = _ahora()
    for m in conv.mensajes:
        if m.rol_autor == otro.value and m.leido_en is None:
            m.leido_en = ahora
    if mi_rol == RolConversacion.COMPRADOR:
        conv.no_leidos_comprador = 0
    else:
        conv.no_leidos_vendedor = 0


# ── Abrir hilo (comprador) ────────────────────────────────────────────────────
# Va ANTES de la dinámica `GET /publicaciones/{publicacion_id}` de publicaciones.py:
# ambos routers cuelgan de `/marketplace` y el orden de `include_router` en main.py
# pone este primero (chat_router antes que publicaciones). Igual el path es distinto
# (`/publicaciones/{id}/conversacion`), así que no colisiona con `{publicacion_id}`.


@router.post(
    "/publicaciones/{publicacion_id}/conversacion",
    response_model=ConversacionSalida,
)
def abrir_conversacion(
    publicacion_id: int,
    datos: ConversacionCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Abre (o devuelve) el hilo del comprador actual con el vendedor de la
    publicación. Opcionalmente publica el primer mensaje."""
    pub = sesion.execute(
        select(PublicacionInterna).where(
            and_(
                PublicacionInterna.id == publicacion_id,
                PublicacionInterna.estado == EstadoPublicacion.ACTIVA.value,
            )
        )
    ).scalar_one_or_none()
    if pub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada")

    vendedor = _vendedor_de(sesion, pub)
    if vendedor is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este anuncio todavía no tiene un vendedor con el que chatear.",
        )
    if vendedor.usuario_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No puedes iniciar un chat sobre tu propio anuncio.",
        )

    conv = sesion.execute(
        select(Conversacion).where(
            and_(
                Conversacion.publicacion_interna_id == pub.id,
                Conversacion.comprador_usuario_id == usuario.id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        conv = Conversacion(
            publicacion_interna_id=pub.id,
            comprador_usuario_id=usuario.id,
            vendedor_usuario_id=vendedor.usuario_id,
            estado=EstadoConversacion.ABIERTA.value,
            no_leidos_comprador=0,
            no_leidos_vendedor=0,
        )
        sesion.add(conv)
        sesion.flush()

    if datos.mensaje:
        if conv.estado == EstadoConversacion.BLOQUEADA.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El vendedor cerró este chat.",
            )
        sesion.add(
            Mensaje(
                conversacion_id=conv.id,
                autor_usuario_id=usuario.id,
                rol_autor=RolConversacion.COMPRADOR.value,
                cuerpo=datos.mensaje,
            )
        )
        conv.ultimo_mensaje_en = _ahora()
        conv.no_leidos_vendedor = (conv.no_leidos_vendedor or 0) + 1
        if conv.estado == EstadoConversacion.ARCHIVADA.value:
            conv.estado = EstadoConversacion.ABIERTA.value

    sesion.commit()
    conv, rol = _cargar_para_participante(sesion, conv.id, usuario)
    return _conversacion_salida(conv, rol, usuario)


# ── Bandeja ──────────────────────────────────────────────────────────────────
# `/conversaciones/no-leidos` se declara ANTES que `/conversaciones/{id}` para que
# "no-leidos" no se lea como un id (§5, misma regla que `mias`/`pendientes`).


@router.get("/conversaciones/no-leidos")
def conteo_no_leidos(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Total de mensajes sin leer del usuario (para el punto rojo del ícono de chat)."""
    filas = sesion.execute(
        select(
            Conversacion.comprador_usuario_id,
            Conversacion.vendedor_usuario_id,
            Conversacion.no_leidos_comprador,
            Conversacion.no_leidos_vendedor,
        ).where(
            and_(
                or_(
                    Conversacion.comprador_usuario_id == usuario.id,
                    Conversacion.vendedor_usuario_id == usuario.id,
                ),
                Conversacion.estado != EstadoConversacion.ARCHIVADA.value,
            )
        )
    ).all()
    total = 0
    for comp_id, _vend_id, nl_comp, nl_vend in filas:
        total += (nl_comp or 0) if comp_id == usuario.id else (nl_vend or 0)
    return {"total": total}


@router.get("/conversaciones", response_model=list[ConversacionResumenSalida])
def listar_conversaciones(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Mis hilos (como comprador y como vendedor), del más reciente al más antiguo.
    Los archivados no salen."""
    convs = (
        sesion.execute(
            select(Conversacion)
            .options(
                selectinload(Conversacion.mensajes),
                selectinload(Conversacion.publicacion).selectinload(PublicacionInterna.fotos),
                selectinload(Conversacion.publicacion).selectinload(PublicacionInterna.vendedor),
                selectinload(Conversacion.comprador),
            )
            .where(
                and_(
                    or_(
                        Conversacion.comprador_usuario_id == usuario.id,
                        Conversacion.vendedor_usuario_id == usuario.id,
                    ),
                    Conversacion.estado != EstadoConversacion.ARCHIVADA.value,
                )
            )
            .order_by(
                Conversacion.ultimo_mensaje_en.desc().nullslast(),
                Conversacion.id.desc(),
            )
        )
        .scalars()
        .all()
    )

    salida: list[ConversacionResumenSalida] = []
    for conv in convs:
        rol = _rol_de(conv, usuario)
        if rol is None:
            continue
        ultimo = conv.mensajes[-1] if conv.mensajes else None
        no_leidos = (
            conv.no_leidos_comprador
            if rol == RolConversacion.COMPRADOR
            else conv.no_leidos_vendedor
        )
        salida.append(
            ConversacionResumenSalida(
                id=conv.id,
                publicacion_id=conv.publicacion_interna_id,
                publicacion_titulo=(conv.publicacion.titulo or conv.publicacion.placa),
                publicacion_foto=_portada(conv.publicacion),
                publicacion_precio=conv.publicacion.precio_usd,
                contraparte_nombre=_contraparte_nombre(conv, rol),
                mi_rol=rol,
                estado=EstadoConversacion(conv.estado),
                contacto_habilitado=conv.contacto_habilitado_en is not None,
                no_leidos=no_leidos or 0,
                ultimo_mensaje=(ultimo.cuerpo if ultimo else None),
                ultimo_mensaje_en=conv.ultimo_mensaje_en,
            )
        )
    return salida


@router.get("/conversaciones/{conversacion_id}", response_model=ConversacionSalida)
def obtener_conversacion(
    conversacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El hilo completo. Marca como leídos los mensajes de la contraparte."""
    conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    _marcar_leidos(conv, rol)
    sesion.commit()
    conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    return _conversacion_salida(conv, rol, usuario)


@router.post(
    "/conversaciones/{conversacion_id}/mensajes",
    response_model=MensajeSalida,
    status_code=status.HTTP_201_CREATED,
)
def enviar_mensaje(
    conversacion_id: int,
    datos: MensajeCrear,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Escribe en el hilo. Si lo hace el vendedor y ya había un mensaje del comprador,
    esto **habilita su WhatsApp** (`contacto_habilitado_en`)."""
    conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    if conv.estado == EstadoConversacion.BLOQUEADA.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Este chat está cerrado.",
        )

    hay_mensaje_comprador = any(
        m.rol_autor == RolConversacion.COMPRADOR.value for m in conv.mensajes
    )
    m = Mensaje(
        conversacion_id=conv.id,
        autor_usuario_id=usuario.id,
        rol_autor=rol.value,
        cuerpo=datos.cuerpo,
    )
    sesion.add(m)
    conv.ultimo_mensaje_en = _ahora()
    if conv.estado == EstadoConversacion.ARCHIVADA.value:
        conv.estado = EstadoConversacion.ABIERTA.value

    if rol == RolConversacion.COMPRADOR:
        conv.no_leidos_vendedor = (conv.no_leidos_vendedor or 0) + 1
    else:
        conv.no_leidos_comprador = (conv.no_leidos_comprador or 0) + 1
        # Barrera de seguridad: el vendedor respondió → su contacto queda habilitado.
        if conv.contacto_habilitado_en is None and hay_mensaje_comprador:
            conv.contacto_habilitado_en = _ahora()

    sesion.commit()
    sesion.refresh(m)
    return _mensaje_salida(m, usuario)


@router.post(
    "/conversaciones/{conversacion_id}/compartir-contacto",
    response_model=ConversacionSalida,
)
def compartir_contacto(
    conversacion_id: int,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """El vendedor habilita su WhatsApp para este comprador sin esperar a responder."""
    conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    if rol != RolConversacion.VENDEDOR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solo el vendedor puede compartir su contacto.",
        )
    if conv.contacto_habilitado_en is None:
        conv.contacto_habilitado_en = _ahora()
        sesion.commit()
        conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    return _conversacion_salida(conv, rol, usuario)


@router.patch("/conversaciones/{conversacion_id}", response_model=ConversacionSalida)
def cambiar_estado_conversacion(
    conversacion_id: int,
    datos: EstadoConversacionPatch,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """`archivada`/`abierta`: cualquiera de los dos. `bloqueada`: solo el vendedor."""
    conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    if datos.estado == "bloqueada" and rol != RolConversacion.VENDEDOR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solo el vendedor puede cerrar un chat.",
        )
    conv.estado = EstadoConversacion(datos.estado).value
    sesion.commit()
    conv, rol = _cargar_para_participante(sesion, conversacion_id, usuario)
    return _conversacion_salida(conv, rol, usuario)
