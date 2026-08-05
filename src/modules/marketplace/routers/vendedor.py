"""Perfil comercial del vendedor (TASK-001).

`Vendedor` es la identidad con la que un comprador ve y contacta a quien vende, separada
de la cuenta de autenticación (`Usuario`): el teléfono es un dato comercial, no de cuenta
(AGENTS §1.0.4). En la etapa 1 la relación es 1:1 con la cuenta; la etapa 2 (patios) la
vuelve N:1 sin reescribir el modelo.

Ambos endpoints son PRIVADOS (`Depends(usuario_actual)`) y GRATIS: cargar el teléfono es
lo que cierra el circuito del marketplace, no un servicio que se cobre (§1.0.3).
Solo tocan la BD propia; jamás invocan scraping (§10.2).

Todas las rutas de este router son literales (`/mi-perfil`), así que no hay riesgo de que
una dinámica capture a una literal. Vive en su propio prefijo `/marketplace/vendedor`,
separado de `/marketplace/publicaciones`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import TipoVendedor, Vendedor
from src.modules.marketplace.schemas import (
    VendedorActualizar,
    VendedorPerfilSalida,
)


router = APIRouter(prefix="/marketplace/vendedor", tags=["marketplace"])


def _mi_vendedor(sesion: Session, usuario: Usuario) -> Vendedor | None:
    """Perfil de vendedor de la cuenta, o `None` si todavía no lo creó."""
    return sesion.execute(
        select(Vendedor).where(Vendedor.usuario_id == usuario.id)
    ).scalar_one_or_none()


def obtener_o_crear_vendedor(sesion: Session, usuario: Usuario) -> Vendedor:
    """Devuelve el `Vendedor` de la cuenta, creándolo si no existe. **No commitea.**

    Es la ÚNICA vía por la que una publicación consigue su `vendedor_id`: el alta de
    publicaciones la llama para que el vínculo quede explícito desde la primera fila. No
    existe resolución alternativa por `usuario_id` a la hora de leer — esa segunda vía
    devolvería un vendedor arbitrario en la etapa 2, cuando una cuenta pueda tener varios.

    `nombre_publico` nace **NULL a propósito**: publicar el nombre de la cuenta es una
    decisión del vendedor, no un efecto secundario de crear un anuncio (compuerta M5). Se
    exige explícitamente recién cuando carga su teléfono, que es lo que lo hace visible.

    **Precondición:** llamarla antes de agregar otros objetos a la sesión. Ante una
    carrera hace `rollback()`, que descartaría cualquier trabajo pendiente.
    """
    vendedor = _mi_vendedor(sesion, usuario)
    if vendedor is not None:
        return vendedor

    vendedor = Vendedor(
        usuario_id=usuario.id,
        tipo=TipoVendedor.PARTICULAR.value,
        telefono_verificado=False,
    )
    sesion.add(vendedor)
    try:
        # `flush` (no `commit`): el caller decide cuándo persistir, pero necesitamos el
        # `id` ya asignado para poder engancharle la publicación en la misma transacción.
        sesion.flush()
    except IntegrityError:
        # Carrera: otra petición de la misma cuenta insertó el perfil entre el SELECT y
        # este INSERT, y `uq_vendedores_usuario_id` lo rechazó. Es un upsert, no un error
        # del usuario: se deshace el intento y se devuelve el perfil que ganó. Nunca 500.
        sesion.rollback()
        existente = _mi_vendedor(sesion, usuario)
        if existente is None:
            # La violación no fue la UK esperada; no la tragamos en silencio.
            raise
        return existente
    return vendedor


@router.get("/mi-perfil", response_model=VendedorPerfilSalida)
def obtener_mi_perfil(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Devuelve el perfil de vendedor propio.

    404 si todavía no existe: el perfil se crea con el `PATCH`, porque un GET no debería
    escribir en la BD. El copy le dice al usuario qué hacer, sin regañarlo.
    """
    vendedor = _mi_vendedor(sesion, usuario)
    if vendedor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Todavía no tienes un perfil de vendedor. "
                "Completa tu nombre y tu número para que los compradores puedan escribirte."
            ),
        )
    return VendedorPerfilSalida.model_validate(vendedor)


@router.patch("/mi-perfil", response_model=VendedorPerfilSalida)
def actualizar_mi_perfil(
    datos: VendedorActualizar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(usuario_actual),
):
    """Crea o actualiza el perfil de vendedor propio (upsert parcial).

    - El teléfono llega validado y normalizado a E.164 sin `+` por el schema
      (`normalizar_telefono_ec`); un formato inválido corta en **422** antes de tocar
      la BD.
    - Solo se tocan los campos ENVIADOS (`model_fields_set`): omitir uno lo deja
      intacto, `nombre_publico: null` lo borra y `telefono: null` retira el número.
    - **Publicar el teléfono exige un `nombre_publico` explícito** (ver abajo).
    - El `tipo` no se acepta del cliente: en la etapa 1 siempre es `particular`.
    """
    vendedor = obtener_o_crear_vendedor(sesion, usuario)

    enviados = datos.model_fields_set
    if "nombre_publico" in enviados:
        vendedor.nombre_publico = datos.nombre_publico
    if "telefono" in enviados:
        vendedor.telefono = datos.telefono

    # Opt-in explícito del nombre (compuerta M5: nada de PII sin opt-in).
    #
    # El teléfono y el nombre salen JUNTOS por el endpoint de contacto, así que cargar el
    # número es lo que vuelve público al vendedor. Antes, un PATCH que solo mandaba
    # teléfono heredaba el nombre de la CUENTA y lo publicaba sin que nadie lo eligiera.
    # Ahora el nombre con el que te ven los compradores se decide a mano, y tampoco se
    # puede borrar dejando un teléfono publicado sin nombre.
    #
    # Se evalúa el estado RESULTANTE, no lo enviado: así cubre las dos direcciones
    # (poner teléfono sin nombre, y quitar el nombre teniendo teléfono).
    if vendedor.telefono and not vendedor.nombre_publico:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Para publicar tu número, dinos también con qué nombre quieres que "
                "te vean los compradores."
            ),
        )

    sesion.commit()
    sesion.refresh(vendedor)
    return VendedorPerfilSalida.model_validate(vendedor)
