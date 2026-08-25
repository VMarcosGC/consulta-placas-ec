"""Endpoints de autenticación: registro, login (contraseña y Google) y perfil."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import obtener_sesion
from src.modules.auth.models import Usuario, TransaccionToken
from src.modules.auth.models import SALDO_INICIAL_TOKENS
from src.modules.auth.schemas import (
    GoogleLoginEntrada,
    Token,
    UsuarioCrear,
    UsuarioSalida,
)
from src.modules.auth.security import hashear_password, verificar_password, crear_token_acceso
from src.modules.auth.dependencies import usuario_actual, es_email_admin
from src.modules.auth.google import (
    ClaimsGoogle,
    ClaimsGoogleInsuficientes,
    CredencialGoogleInvalida,
    GoogleNoDisponible,
    identidad_google_autoritativa,
    verificar_id_token_google,
)


router = APIRouter(prefix="/auth", tags=["auth"])

# Copy del 409 más frecuente: una cuenta local cuyo correo no es de un dominio que Google
# opere. Es fricción deliberada (ver `identidad_google_autoritativa`), así que el mensaje
# tiene que decir exactamente qué hacer, sin culpar a nadie.
MENSAJE_VINCULAR_DESDE_PERFIL = (
    "Ya tienes una cuenta con este correo. Entra con tu contraseña y vincula Google "
    "desde tu perfil."
)


def _verificar_google(id_token_recibido: str) -> ClaimsGoogle:
    """Traduce las excepciones del verificador al contrato de errores del proyecto.

    Nunca deja escapar el mensaje original de jose al cliente ni registra el token.
    """
    try:
        return verificar_id_token_google(id_token_recibido)
    except CredencialGoogleInvalida:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de Google inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ClaimsGoogleInsuficientes as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except GoogleNoDisponible as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )


def _buscar_por_email(sesion: Session, email: str) -> list[Usuario]:
    """Búsqueda insensible a mayúsculas.

    `/auth/registro` guarda el email tal como lo escribió el usuario y Google lo devuelve
    en minúsculas: con `==` exacto, una cuenta creada como `Marcos@Gmail.com` no haría
    match, el flujo saltaría al alta e intentaría insertar una segunda fila con el mismo
    correo real → choque contra el índice único de `email` → 500. Normalizar el email en
    `/auth/registro` es deuda preexistente y queda fuera de alcance.
    """
    return list(
        sesion.execute(
            select(Usuario).where(func.lower(Usuario.email) == email.lower())
        ).scalars().all()
    )


def _por_id_google(sesion: Session, sub: str) -> Usuario | None:
    return sesion.execute(
        select(Usuario).where(Usuario.id_google == sub)
    ).scalar_one_or_none()


def _mensaje_sub_tomado() -> str:
    return (
        "Esa cuenta de Google ya está vinculada a otra cuenta de Revisa tu Carro EC. "
        "Entra con ella, o escríbenos si crees que hay un error."
    )


def _commitear_enlace(sesion: Session, usuario: Usuario, sub: str) -> None:
    """Persiste `id_google` resolviendo la carrera contra `ix_usuarios_id_google`.

    Las comprobaciones previas (¿ese `sub` ya es de alguien?) son un SELECT: entre ese
    SELECT y este COMMIT cabe otra petición que vincule el mismo `sub` a otra cuenta. El
    índice único la rechaza, y sin esta guarda el `IntegrityError` escaparía como **500**,
    contra §10.2 — un conflicto de negocio perfectamente esperable no puede reventar.

    Mismo patrón que `obtener_o_crear_vendedor` (TASK-001): capturar, `rollback`, releer
    la fila que ganó y responder según ella. **Si la violación no es la esperada se
    relanza**, en vez de tragarse en silencio un problema distinto.
    """
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        duenio = _por_id_google(sesion, sub)
        if duenio is None or duenio.id == usuario.id:
            # La violación no fue `ix_usuarios_id_google` (o el ganador somos nosotros y
            # entonces no había conflicto): no es nuestro caso, no la tragamos.
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_mensaje_sub_tomado()
        )
    sesion.refresh(usuario)


@router.post("/registro", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    datos: UsuarioCrear,
    sesion: Session = Depends(obtener_sesion),
):
    existente = sesion.execute(
        select(Usuario).where(Usuario.email == datos.email)
    ).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese email",
        )

    usuario = Usuario(
        email=datos.email,
        password_hash=hashear_password(datos.password),
        nombre=datos.nombre,
    )
    # Audita el saldo de cortesía inicial para que el ledger cuadre con el saldo.
    usuario.transacciones_tokens.append(
        TransaccionToken(monto=SALDO_INICIAL_TOKENS, motivo="saldo_inicial")
    )
    sesion.add(usuario)
    sesion.commit()
    sesion.refresh(usuario)
    return usuario


@router.post("/login", response_model=Token)
def iniciar_sesion(
    form: OAuth2PasswordRequestForm = Depends(),
    sesion: Session = Depends(obtener_sesion),
):
    """OAuth2PasswordRequestForm espera campos `username` y `password` (form-data).
    El `username` es el email del usuario.
    """
    usuario = sesion.execute(
        select(Usuario).where(Usuario.email == form.username)
    ).scalar_one_or_none()

    # `password_hash` es nullable desde la migración 0025: una cuenta creada por Google
    # no tiene contraseña. Sin esta guarda, `passlib` recibiría None y reventaría con
    # TypeError → 500 por una condición de negocio perfectamente esperable.
    # El mensaje es el MISMO que el de una contraseña equivocada: decir "esa cuenta usa
    # Google" revelaría qué correos están registrados y con qué proveedor a cualquiera
    # que pruebe. La pista de que existe login con Google la da el botón de la pantalla.
    if (
        usuario is None
        or not usuario.password_hash
        or not verificar_password(form.password, usuario.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o password incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = crear_token_acceso(subject=usuario.email)
    return Token(access_token=token)


@router.post("/google", response_model=Token)
def iniciar_sesion_con_google(
    datos: GoogleLoginEntrada,
    sesion: Session = Depends(obtener_sesion),
):
    """Canjea un ID token de Google por el JWT propio del proyecto.

    El token de Google se verifica y **se descarta**: no se guarda, no se reenvía y no se
    refresca. La salida es el mismo schema `Token` que `/auth/login`, así que el frontend
    no distingue de dónde salió la sesión.

    Orden de resolución (normativo): por `id_google`, luego por email, luego alta.
    """
    claims = _verificar_google(datos.id_token)

    # 1. Por `id_google == sub`. Es la cuenta aunque su email ya no coincida con el que
    #    manda Google hoy, y el email guardado NO se actualiza: es el `sub` de nuestro
    #    propio JWT y la clave de negocio de toda la app. Reescribirlo invalidaría las
    #    sesiones vivas y podría chocar contra el índice único de `email`.
    usuario = sesion.execute(
        select(Usuario).where(Usuario.id_google == claims.sub)
    ).scalar_one_or_none()
    if usuario is not None:
        return Token(access_token=crear_token_acceso(subject=usuario.email))

    # 2. Por email, insensible a mayúsculas.
    candidatos = _buscar_por_email(sesion, claims.email)
    if len(candidatos) > 1:
        # Colisión real de datos: dos cuentas cuyo email solo difiere en mayúsculas.
        # Elegir una a dedo sería entregarle a alguien la cuenta de otro.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Hay más de una cuenta con este correo. Escríbenos para resolverlo y "
                "mientras tanto entra con tu contraseña."
            ),
        )

    if candidatos:
        usuario = candidatos[0]
        if usuario.id_google:
            # El paso 1 no la encontró por `sub`, así que su `id_google` es OTRO.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Esta cuenta ya está vinculada a otra cuenta de Google. Entra con "
                    "esa cuenta o usa tu contraseña."
                ),
            )
        if not identidad_google_autoritativa(claims):
            # No se vincula NI se crea una segunda cuenta: el índice único de `email` lo
            # impediría igual. La salida del usuario es /auth/google/vincular, ya
            # autenticado — autenticarse es la prueba de posesión que el claim no da.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MENSAJE_VINCULAR_DESDE_PERFIL,
            )

        usuario.id_google = claims.sub
        usuario.email_verificado = True
        # `proveedor_autenticacion` NO se toca: la cuenta se creó local y eso no cambia.
        # Tampoco se acreditan tokens: el usuario ya recibió sus 5 al registrarse y su
        # fila `saldo_inicial` ya está en el ledger.
        _commitear_enlace(sesion, usuario, claims.sub)
        return Token(access_token=crear_token_acceso(subject=usuario.email))

    # 3. No existe → alta. Esta rama NO depende de la autoritatividad: sin cuenta previa
    #    no hay nada que tomar, y el correo queda asociado a quien lo controla hoy.
    usuario = Usuario(
        email=claims.email,
        password_hash=None,
        nombre=claims.nombre,
        proveedor_autenticacion="google",
        id_google=claims.sub,
        email_verificado=True,
    )
    # El saldo de cortesía se acredita SOLO acá, dentro del bloque que construye el
    # Usuario. La regla es estructural, no un `if`: así no hay forma de que un segundo
    # canje agregue una segunda fila `saldo_inicial`. Mismo motivo y mismo monto que el
    # registro local, para que el ledger sea una sola serie legible.
    usuario.transacciones_tokens.append(
        TransaccionToken(monto=SALDO_INICIAL_TOKENS, motivo="saldo_inicial")
    )
    sesion.add(usuario)
    try:
        sesion.commit()
    except IntegrityError:
        # Carrera del alta: entre los SELECT de los pasos 1-2 y este INSERT, otra petición
        # creó la fila. Los índices únicos de `email` y de `id_google` la rechazan, y sin
        # esta guarda saldría como 500 — el caso más probable de todos, porque un doble
        # clic en "Entrar con Google" manda dos peticiones idénticas a la vez.
        sesion.rollback()
        ganador = _por_id_google(sesion, claims.sub)
        if ganador is not None:
            # El caso normal de la carrera: la otra petición traía los mismos claims.
            # Su fila es la buena, y el resultado para el usuario es el mismo.
            return Token(access_token=crear_token_acceso(subject=ganador.email))

        otros = _buscar_por_email(sesion, claims.email)
        if len(otros) == 1 and not otros[0].id_google:
            # Alguien registró ese correo por contraseña mientras resolvíamos. No es
            # nuestro `sub`, así que NO se auto-enlaza acá: aplica §0.1 igual que si la
            # cuenta hubiera existido desde el principio.
            if identidad_google_autoritativa(claims):
                otros[0].id_google = claims.sub
                otros[0].email_verificado = True
                _commitear_enlace(sesion, otros[0], claims.sub)
                return Token(access_token=crear_token_acceso(subject=otros[0].email))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MENSAJE_VINCULAR_DESDE_PERFIL,
            )
        # No es ninguna de las dos violaciones esperadas: que suba.
        raise
    sesion.refresh(usuario)
    return Token(access_token=crear_token_acceso(subject=usuario.email))


@router.post("/google/vincular", response_model=UsuarioSalida)
def vincular_google(
    datos: GoogleLoginEntrada,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
):
    """Vincula una cuenta de Google a la cuenta ya autenticada.

    Es la salida del 409 de `/auth/google`: sin esto, un usuario con correo no
    autoritativo quedaría permanentemente fuera del login con Google.

    El JWT propio es la prueba de posesión que el claim `email_verified` no da — quien
    pide el enlace ya demostró que sabe la contraseña. Con eso, la autoritatividad **deja
    de importar** y no se comprueba. El email del token tampoco tiene que coincidir con
    el de la cuenta: vincular es decir "esta cuenta de Google, aunque use otro correo,
    soy yo".
    """
    claims = _verificar_google(datos.id_token)

    if usuario.id_google and usuario.id_google != claims.sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            # No se ofrece "desvincúlala": desvincular está fuera de alcance y no existe
            # el endpoint. Prometer una salida que no está construida es peor que decir
            # que hace falta ayuda.
            detail=(
                "Tu cuenta ya está vinculada a otra cuenta de Google. Entra con esa "
                "cuenta de Google, o escríbenos si necesitas cambiarla."
            ),
        )

    # El índice único de `id_google` lo garantiza, pero se comprueba antes para devolver
    # un 409 legible en vez de un IntegrityError → 500.
    duenio = _por_id_google(sesion, claims.sub)
    if duenio is not None and duenio.id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_mensaje_sub_tomado()
        )

    # `email_verificado` NO se toca: sigue describiendo el correo *de la cuenta*, que
    # Google no verificó. `proveedor_autenticacion` tampoco: la cuenta no cambia de
    # origen. Y no se acredita ningún token — la cuenta ya existía.
    usuario.id_google = claims.sub
    # El SELECT de arriba no es atómico: dos vinculaciones concurrentes del mismo `sub`
    # desde cuentas distintas lo pasan las dos y chocan recién en el COMMIT.
    _commitear_enlace(sesion, usuario, claims.sub)
    usuario.es_admin = es_email_admin(usuario.email)
    return usuario


@router.get("/me", response_model=UsuarioSalida)
def perfil(usuario: Usuario = Depends(usuario_actual)):
    # Atributo transitorio (no columna): le dice al frontend si mostrar moderación.
    usuario.es_admin = es_email_admin(usuario.email)
    return usuario
