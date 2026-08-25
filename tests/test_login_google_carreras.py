"""Carreras de BD del login con Google, contra **Postgres real** (pg-dev).

Por qué un archivo aparte y por qué no vale un Mock: las carreras que se prueban acá
sólo existen porque los índices únicos `ix_usuarios_email` e `ix_usuarios_id_google`
rechazan la segunda escritura. La `SesionFalsa` de `test_login_google.py` no ejerce
restricción alguna — un test con Mock afirmaría que el `except IntegrityError` funciona
sin que ningún `IntegrityError` llegue a levantarse. Sería una prueba que pasa siempre,
que es peor que no tenerla.

**Nunca toca Neon.** `exigir_pg_dev` parsea `TEST_DATABASE_URL` y exige host, puerto y
base de la pg-dev desechable por separado, sobre los componentes — nunca sobre el texto.
Si el contenedor no está levantado, las pruebas se **saltan** con motivo explícito: no
se silencian ni se sustituyen por una simulación.

Levantar el entorno:

    docker start pg-dev
    docker exec pg-dev psql -U postgres -c "CREATE DATABASE task015_carreras;"
    DATABASE_URL='postgresql+psycopg://postgres:dev@127.0.0.1:5433/task015_carreras' \
        python -m alembic upgrade head
"""

import os
import sys
import unittest

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from src.core.database import obtener_sesion  # noqa: E402
from src.modules.auth.dependencies import usuario_actual  # noqa: E402
from src.modules.auth.models import Usuario  # noqa: E402
from src.modules.auth.router import MENSAJE_VINCULAR_DESDE_PERFIL  # noqa: E402
from src.modules.auth.security import crear_token_acceso  # noqa: E402

from test_login_google import (  # noqa: E402
    CLIENT_ID,
    SUB_GOOGLE,
    BaseGoogle,
    claims_google,
    firmar,
)


URL_PG_DEV = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:dev@127.0.0.1:5433/task015_carreras",
)

OTRO_SUB = "110000000000000000999"


HOSTS_PG_DEV = frozenset({"127.0.0.1", "localhost"})
PUERTO_PG_DEV = 5433
BASE_DESECHABLE = "task015_carreras"


def exigir_pg_dev(url_texto):
    """Aborta salvo que la URL resuelva **exactamente** a la base desechable de pg-dev.

    Barrera dura, no cortesía: `setUp` hace `TRUNCATE usuarios`, así que una URL mal
    puesta apuntando a Neon **borraría la tabla de usuarios de producción**.

    Se compara sobre los **componentes parseados** por `make_url`, nunca sobre el texto.
    La versión anterior buscaba la subcadena `"127.0.0.1:5433"` dentro de la URL completa,
    y eso no es un guard: una URL a producción que lleve ese texto en un parámetro
    (`?options=-c%20search_path%3D127.0.0.1:5433`) o en la contraseña lo pasaba entero.
    Host, puerto y base se exigen por separado; los tres, o no se corre.
    """
    try:
        url = make_url(url_texto)
    except Exception as exc:  # URL malformada: tampoco se corre.
        raise RuntimeError(
            f"TEST_DATABASE_URL no es una URL válida ({exc}). Estas pruebas truncan `usuarios`."
        ) from exc

    problemas = []
    if url.host not in HOSTS_PG_DEV:
        problemas.append(f"host {url.host!r} no está en {sorted(HOSTS_PG_DEV)}")
    if url.port != PUERTO_PG_DEV:
        problemas.append(f"puerto {url.port!r} no es {PUERTO_PG_DEV}")
    if url.database != BASE_DESECHABLE:
        problemas.append(f"base {url.database!r} no es {BASE_DESECHABLE!r}")

    if problemas:
        raise RuntimeError(
            "TEST_DATABASE_URL debe apuntar a la base desechable de pg-dev "
            f"({'/'.join(sorted(HOSTS_PG_DEV))}:{PUERTO_PG_DEV}/{BASE_DESECHABLE}): "
            + "; ".join(problemas)
            + f". URL recibida: {url.render_as_string(hide_password=True)!r}. "
            "Estas pruebas truncan `usuarios`."
        )
    return url


def _motor_o_none():
    """Devuelve el engine si pg-dev responde y la URL es suya; si no, `None`."""
    url = exigir_pg_dev(URL_PG_DEV)
    try:
        # Se conecta con el objeto ya validado, no con el texto: así no cabe que lo
        # verificado y lo que abre la conexión sean cosas distintas.
        motor = create_engine(url, future=True)
        with motor.connect() as conexion:
            conexion.execute(text("select 1 from usuarios limit 1"))
        return motor
    except Exception:
        return None


MOTOR = _motor_o_none()

SIN_PG = MOTOR is None
MOTIVO_SKIP = (
    f"pg-dev no disponible en {URL_PG_DEV}. "
    "Levántalo con `docker start pg-dev` y aplica `alembic upgrade head` "
    "sobre la base desechable (ver docstring)."
)


@unittest.skipIf(SIN_PG, MOTIVO_SKIP)
class BaseCarreras(BaseGoogle):
    """Sesión real contra pg-dev, con `usuarios` limpia antes de cada prueba."""

    def setUp(self):
        super().setUp()
        with MOTOR.connect() as conexion:
            conexion.execute(text("TRUNCATE usuarios RESTART IDENTITY CASCADE"))
            conexion.commit()

        self.sesion_real = Session(MOTOR)
        self.addCleanup(self.sesion_real.close)
        main.app.dependency_overrides[obtener_sesion] = lambda: self.sesion_real

    def competidor(self, sql, **params):
        """Ejecuta un INSERT/UPDATE rival justo ANTES del flush de la petición.

        `before_flush` y no `after_flush`: si el rival escribiera después de que nuestro
        INSERT ya salió, quedaría bloqueado por el índice único esperando nuestro COMMIT
        y la prueba se colgaría en un deadlock. Escribiendo antes, nuestro flush encuentra
        la fila ya commiteada y levanta el `IntegrityError` de verdad.
        """
        estado = {"disparado": False}

        def _antes_del_flush(sesion, contexto, instancias):
            if estado["disparado"]:
                return
            estado["disparado"] = True
            with MOTOR.connect() as conexion:
                conexion.execute(text(sql), params)
                conexion.commit()

        event.listen(self.sesion_real, "before_flush", _antes_del_flush)
        self.addCleanup(
            lambda: event.remove(self.sesion_real, "before_flush", _antes_del_flush)
        )
        return estado

    def filas(self):
        with MOTOR.connect() as conexion:
            return conexion.execute(
                text("select email, id_google, proveedor_autenticacion from usuarios")
            ).fetchall()

    def insertar(self, email, id_google=None, proveedor="local", password_hash="x"):
        with MOTOR.connect() as conexion:
            conexion.execute(
                text(
                    "insert into usuarios (email, password_hash, id_google,"
                    " proveedor_autenticacion, email_verificado)"
                    " values (:e, :p, :g, :prov, false)"
                ),
                {"e": email, "p": password_hash, "g": id_google, "prov": proveedor},
            )
            conexion.commit()


class PruebaCarreraAlta(BaseCarreras):
    """`POST /auth/google`, rama de alta nueva (§3 paso 3)."""

    SQL_RIVAL = (
        "insert into usuarios (email, password_hash, id_google,"
        " proveedor_autenticacion, email_verificado)"
        " values (:email, null, :sub, 'google', true)"
    )

    def test_dos_altas_simultaneas_devuelven_200_y_una_sola_fila(self):
        """El caso más probable de todos: doble clic en «Entrar con Google»."""
        self.competidor(self.SQL_RIVAL, email="ana@gmail.com", sub=SUB_GOOGLE)

        respuesta = self.cliente.post(
            "/auth/google", json={"id_token": firmar(claims_google())}
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.assertIn("access_token", respuesta.json())
        # La fila que ganó es la del rival, y es la única: no se duplicó la cuenta.
        self.assertEqual(len(self.filas()), 1)

    def test_correo_registrado_por_contrasena_en_la_carrera_no_autoritativo_da_409(self):
        """Alguien registró ese correo mientras resolvíamos, y no es identidad autoritativa.

        No se auto-enlaza: aplica §0.1 igual que si la cuenta hubiera existido desde el
        principio. Lo que NO puede pasar es un 500.
        """
        self.competidor(
            "insert into usuarios (email, password_hash, proveedor_autenticacion,"
            " email_verificado) values (:email, 'hash', 'local', false)",
            email="juan@hotmail.com",
        )

        respuesta = self.cliente.post(
            "/auth/google",
            json={"id_token": firmar(claims_google(email="juan@hotmail.com"))},
        )

        self.assertEqual(respuesta.status_code, 409, respuesta.text)
        self.assertEqual(respuesta.json()["detail"], MENSAJE_VINCULAR_DESDE_PERFIL)
        self.assertEqual(self.filas()[0].id_google, None)

    def test_correo_registrado_en_la_carrera_autoritativo_enlaza(self):
        """Mismo choque, pero la identidad SÍ es autoritativa (gmail.com) → enlaza."""
        self.competidor(
            "insert into usuarios (email, password_hash, proveedor_autenticacion,"
            " email_verificado) values (:email, 'hash', 'local', false)",
            email="ana@gmail.com",
        )

        respuesta = self.cliente.post(
            "/auth/google", json={"id_token": firmar(claims_google())}
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        filas = self.filas()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0].id_google, SUB_GOOGLE)
        # Se creó local y eso no cambia al vincular.
        self.assertEqual(filas[0].proveedor_autenticacion, "local")


class PruebaCarreraEnlaceAutoritativo(BaseCarreras):
    """`POST /auth/google`, rama de vinculación del §3 paso 2."""

    def test_otro_se_queda_con_el_sub_durante_el_enlace(self):
        """El SELECT previo dijo que el `sub` estaba libre; entre medio dejó de estarlo."""
        self.insertar("ana@gmail.com", id_google=None)
        self.competidor(
            "insert into usuarios (email, password_hash, id_google,"
            " proveedor_autenticacion, email_verificado)"
            " values ('ladron@gmail.com', null, :sub, 'google', true)",
            sub=SUB_GOOGLE,
        )

        respuesta = self.cliente.post(
            "/auth/google", json={"id_token": firmar(claims_google())}
        )

        self.assertEqual(respuesta.status_code, 409, respuesta.text)
        self.assertNotEqual(respuesta.status_code, 500)


@unittest.skipIf(SIN_PG, MOTIVO_SKIP)
class PruebaCarreraVincular(BaseCarreras):
    """`POST /auth/google/vincular` (§3.1)."""

    def setUp(self):
        super().setUp()
        self.insertar("juan@hotmail.com", id_google=None)
        self.yo = self.sesion_real.execute(
            text("select id, email from usuarios where email = 'juan@hotmail.com'")
        ).fetchone()

    def _autenticado(self):
        usuario = self.sesion_real.get(Usuario, self.yo.id)
        main.app.dependency_overrides[usuario_actual] = lambda: usuario
        return usuario

    def test_dos_cuentas_vinculan_el_mismo_sub_a_la_vez(self):
        """Ambas pasan el SELECT de dueño y chocan recién en el COMMIT → 409, no 500."""
        self._autenticado()
        self.competidor(
            "insert into usuarios (email, password_hash, id_google,"
            " proveedor_autenticacion, email_verificado)"
            " values ('otra@hotmail.com', null, :sub, 'google', true)",
            sub=SUB_GOOGLE,
        )

        respuesta = self.cliente.post(
            "/auth/google/vincular",
            json={"id_token": firmar(claims_google(email="juan@hotmail.com"))},
            headers={"Authorization": f"Bearer {crear_token_acceso(subject=self.yo.email)}"},
        )

        self.assertEqual(respuesta.status_code, 409, respuesta.text)
        self.assertIn("ya está vinculada", respuesta.json()["detail"])

    def test_sin_carrera_vincula_y_persiste(self):
        """Control: sin rival, el enlace se guarda de verdad en Postgres."""
        self._autenticado()

        respuesta = self.cliente.post(
            "/auth/google/vincular",
            json={"id_token": firmar(claims_google(email="juan@hotmail.com"))},
            headers={"Authorization": f"Bearer {crear_token_acceso(subject=self.yo.email)}"},
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        with MOTOR.connect() as conexion:
            guardado = conexion.execute(
                text("select id_google, email_verificado from usuarios where id = :i"),
                {"i": self.yo.id},
            ).fetchone()
        self.assertEqual(guardado.id_google, SUB_GOOGLE)
        # `email_verificado` NO se toca al vincular: Google no verificó ESE correo.
        self.assertFalse(guardado.email_verificado)


class PruebaBarreraTestDatabaseUrl(unittest.TestCase):
    """La barrera de `TEST_DATABASE_URL` misma, sobre componentes parseados.

    **No se salta si pg-dev no está levantado**: es lo único de este archivo que corre
    siempre, y es a propósito. El día que alguien "simplifique" `exigir_pg_dev` de vuelta
    a un `in` sobre el texto, estas pruebas fallan en CI sin necesidad de un Postgres.
    """

    URL_BUENA = "postgresql+psycopg://postgres:dev@127.0.0.1:5433/task015_carreras"

    def test_url_de_pg_dev_pasa(self):
        for url in (
            self.URL_BUENA,
            "postgresql+psycopg://postgres:dev@localhost:5433/task015_carreras",
        ):
            with self.subTest(url=url):
                self.assertEqual(exigir_pg_dev(url).database, BASE_DESECHABLE)

    def test_produccion_con_el_texto_de_pg_dev_en_un_parametro_aborta(self):
        """El agujero real: la subcadena está, pero la conexión va a Neon.

        `make_url` mete `options` en `query`, así que el host sigue siendo el de
        producción. Un guard que compare texto ve `127.0.0.1:5433` y deja pasar un
        `TRUNCATE usuarios` contra la base real.
        """
        url = (
            "postgresql+psycopg://usuario:clave@ep-prod-123.us-east-2.aws.neon.tech"
            "/neondb?options=-c search_path=127.0.0.1:5433"
        )
        # La subcadena literal está: el guard viejo (`"127.0.0.1:5433" in url`) pasaba.
        self.assertIn("127.0.0.1:5433", url)

        with self.assertRaises(RuntimeError) as caja:
            exigir_pg_dev(url)  # Y aun así aborta, porque `host` es de Neon.

        self.assertIn("neon.tech", str(caja.exception))

    def test_password_con_el_texto_de_pg_dev_aborta(self):
        """Misma trampa, en la contraseña. El mensaje no debe filtrarla."""
        url = "postgresql+psycopg://usuario:127.0.0.1:5433@ep-prod-123.aws.neon.tech/neondb"
        self.assertIn("127.0.0.1:5433", url)

        with self.assertRaises(RuntimeError) as caja:
            exigir_pg_dev(url)

        self.assertIn("neon.tech", str(caja.exception))
        # El mensaje se arma con `hide_password=True`: la clave no va al log de CI.
        self.assertNotIn("127.0.0.1:5433@", str(caja.exception))

    def test_host_bueno_pero_puerto_de_produccion_aborta(self):
        """127.0.0.1:5432 es el Postgres real de la máquina, no el contenedor desechable."""
        with self.assertRaises(RuntimeError) as caja:
            exigir_pg_dev("postgresql+psycopg://postgres:dev@127.0.0.1:5432/task015_carreras")
        self.assertIn("puerto", str(caja.exception))

    def test_host_y_puerto_buenos_pero_otra_base_aborta(self):
        """pg-dev hospeda varias bases (TASK-010); solo la desechable puede truncarse."""
        with self.assertRaises(RuntimeError) as caja:
            exigir_pg_dev("postgresql+psycopg://postgres:dev@127.0.0.1:5433/consulta_placas")
        self.assertIn("base", str(caja.exception))

    def test_sin_puerto_explicito_aborta(self):
        """Sin puerto, `make_url` devuelve `None` y el default de psycopg sería 5432."""
        with self.assertRaises(RuntimeError):
            exigir_pg_dev("postgresql+psycopg://postgres:dev@127.0.0.1/task015_carreras")

    def test_url_malformada_aborta(self):
        with self.assertRaises(RuntimeError):
            exigir_pg_dev("esto no es una url")


def tearDownModule():
    """Cierra el pool: si no, psycopg avisa de conexiones abiertas al terminar el proceso."""
    if MOTOR is not None:
        MOTOR.dispose()


if __name__ == "__main__":
    unittest.main()
