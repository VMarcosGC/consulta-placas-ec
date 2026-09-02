"""Pruebas del perfil de vendedor y del contacto comprador-vendedor (TASK-001).

No requieren PostgreSQL ni red: la sesión se aísla con `Mock` y las dependencias de
FastAPI se sustituyen con `app.dependency_overrides`. Los modelos usan JSONB, así que
SQLite no serviría como sustituto de la BD.

Se usa `unittest` de la stdlib (el repo no tiene pytest y no se agrega una dependencia
por esto, §4). `pytest` ejecuta `TestCase` sin cambios si algún día se instala:

    python -m unittest tests.test_contacto_vendedor -v
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    ContactoRevelado,
    Conversacion,
    EstadoConversacion,
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
    TipoVendedor,
    Vendedor,
)
from src.modules.marketplace.schemas import (
    armar_whatsapp_url,
    normalizar_telefono_ec,
)


def _sesion_falsa(resultados_execute):
    """Sesión mockeada: cada `execute()` devuelve el siguiente valor de la lista.

    `refresh` completa los valores que en la BD real pondrían los defaults de columna
    (id, creado_en), para que el schema de salida pueda serializar el objeto recién
    creado sin necesidad de un flush real.
    """
    sesion = Mock()
    sesion.execute.side_effect = [
        Mock(scalar_one_or_none=Mock(return_value=r)) for r in resultados_execute
    ]

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    sesion.refresh.side_effect = _refresh
    return sesion


def _usuario(id_=7, nombre="Marcos G."):
    return Usuario(id=id_, email="vendedor@example.com", password_hash="x", nombre=nombre)


def _publicacion(estado=EstadoPublicacion.ACTIVA.value, vendedor_id=None, usuario_id=7):
    """Publicación interna mínima pero **serializable** por `PublicacionInternaSalida`.

    Los campos de plan/verificación/fecha no los usa el endpoint de contacto, pero sí la
    salida del alta (`desde_modelo` los convierte a enum y reventaría con None).
    """
    return PublicacionInterna(
        id=10,
        usuario_id=usuario_id,
        vendedor_id=vendedor_id,
        placa="ABC1234",
        titulo="Mazda 3 2016",
        precio_usd=12000,
        estado=estado,
        plan=PlanPublicacion.LIGHT.value,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=False,
        creado_en=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
    )


def _vendedor(telefono="593987654321"):
    return Vendedor(
        id=3,
        usuario_id=7,
        tipo=TipoVendedor.PARTICULAR.value,
        nombre_publico="Marcos G.",
        telefono=telefono,
        telefono_verificado=False,
        creado_en=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
    )


def _conversacion(habilitado=True, comprador_id=99, estado=EstadoConversacion.ABIERTA.value):
    """Hilo del comprador con el vendedor de la publicación 10. `habilitado` = el
    vendedor ya respondió, así que la barrera del WhatsApp está levantada."""
    c = Conversacion(
        id=1,
        publicacion_interna_id=10,
        comprador_usuario_id=comprador_id,
        vendedor_usuario_id=7,
        estado=estado,
        no_leidos_comprador=0,
        no_leidos_vendedor=0,
    )
    c.contacto_habilitado_en = (
        datetime(2026, 8, 4, 13, 0, tzinfo=timezone.utc) if habilitado else None
    )
    return c


class NormalizacionTelefonoTests(unittest.TestCase):
    """El formato acordado: celular `09XXXXXXXX` o E.164 `5939XXXXXXXX` → E.164 sin `+`."""

    def test_formas_validas_se_normalizan_a_e164(self):
        casos = {
            "0987654321": "593987654321",
            "098 765 4321": "593987654321",
            "098-765-4321": "593987654321",
            "+593987654321": "593987654321",
            "593 98 765 4321": "593987654321",
            "(09) 8765-4321": "593987654321",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_telefono_ec(entrada), esperado)

    def test_formas_invalidas_lanzan_valueerror(self):
        invalidos = [
            "",                # vacío
            "12345",           # muy corto
            "0887654321",      # celular no empieza en 09
            "022345678",       # convencional: WhatsApp no aplica
            "09876543210",     # un dígito de más
            "593887654321",    # E.164 sin el 9 de celular
            "098765432a",      # letras
            "0987654321;DROP", # basura
        ]
        for entrada in invalidos:
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValueError):
                    normalizar_telefono_ec(entrada)

    def test_whatsapp_url_usa_el_numero_normalizado_y_copy_no_agresivo(self):
        url = armar_whatsapp_url("593987654321", "Mazda 3 2016")
        self.assertTrue(url.startswith("https://wa.me/593987654321?text="))
        self.assertIn("Mazda", url)
        self.assertIn("Hola", url)


class PerfilVendedorTests(unittest.TestCase):
    """`PATCH/GET /marketplace/vendedor/mi-perfil` — privado, gratis, crea si no existe."""

    def setUp(self):
        self.usuario = _usuario()
        main.app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, sesion):
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

    def test_telefono_valido_se_guarda_normalizado_a_e164(self):
        sesion = _sesion_falsa([None])  # todavía no tiene perfil → lo crea
        self._con_sesion(sesion)

        respuesta = self.cliente.patch(
            "/marketplace/vendedor/mi-perfil",
            json={"telefono": "098 765 4321", "nombre_publico": "Marcos G."},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["telefono"], "593987654321")
        creado = sesion.add.call_args.args[0]
        self.assertIsInstance(creado, Vendedor)
        self.assertEqual(creado.usuario_id, self.usuario.id)
        self.assertEqual(creado.tipo, TipoVendedor.PARTICULAR.value)
        self.assertEqual(creado.telefono, "593987654321")
        sesion.commit.assert_called_once()

    def test_telefono_invalido_devuelve_422(self):
        sesion = _sesion_falsa([None])
        self._con_sesion(sesion)

        respuesta = self.cliente.patch(
            "/marketplace/vendedor/mi-perfil", json={"telefono": "12345"}
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.commit.assert_not_called()  # no llegó a tocar la BD

    def test_telefono_sin_nombre_publico_devuelve_422(self):
        """Opt-in explícito del nombre (compuerta M5).

        Antes, un PATCH que solo mandaba teléfono heredaba el nombre de la CUENTA y lo
        publicaba sin que nadie lo eligiera. Teléfono y nombre salen juntos por el
        endpoint de contacto, así que cargar el número es lo que te vuelve público.
        """
        sesion = _sesion_falsa([None])
        self._con_sesion(sesion)

        respuesta = self.cliente.patch(
            "/marketplace/vendedor/mi-perfil", json={"telefono": "0987654321"}
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.commit.assert_not_called()
        sesion.rollback.assert_called_once()

    def test_borrar_el_nombre_con_telefono_cargado_devuelve_422(self):
        """La regla se evalúa sobre el estado RESULTANTE, así que cubre las dos
        direcciones: no se puede dejar un teléfono publicado sin nombre."""
        sesion = _sesion_falsa([_vendedor()])  # ya tiene teléfono y nombre
        self._con_sesion(sesion)

        respuesta = self.cliente.patch(
            "/marketplace/vendedor/mi-perfil", json={"nombre_publico": None}
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.commit.assert_not_called()

    def test_carrera_en_la_creacion_relee_el_perfil_existente(self):
        """Dos peticiones de la misma cuenta: `uq_vendedores_usuario_id` rechaza la
        segunda. Es un upsert, no un error del usuario → 200 releyendo, nunca 500."""
        sesion = _sesion_falsa([None, _vendedor()])
        sesion.flush.side_effect = IntegrityError(
            "INSERT INTO vendedores", {}, Exception("uq_vendedores_usuario_id")
        )
        self._con_sesion(sesion)

        respuesta = self.cliente.patch(
            "/marketplace/vendedor/mi-perfil",
            json={"telefono": "0987654321", "nombre_publico": "Marcos G."},
        )

        self.assertEqual(respuesta.status_code, 200)
        sesion.rollback.assert_called_once()
        self.assertEqual(respuesta.json()["telefono"], "593987654321")

    def test_get_sin_perfil_devuelve_404(self):
        """404 = estado de ONBOARDING, no fallo. T5 debe pintar el formulario."""
        self._con_sesion(_sesion_falsa([None]))
        respuesta = self.cliente.get("/marketplace/vendedor/mi-perfil")
        self.assertEqual(respuesta.status_code, 404)

    def test_get_devuelve_el_perfil_propio(self):
        self._con_sesion(_sesion_falsa([_vendedor()]))
        respuesta = self.cliente.get("/marketplace/vendedor/mi-perfil")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["telefono"], "593987654321")


class AltaEnganchaVendedorTests(unittest.TestCase):
    """El alta de publicaciones puebla `vendedor_id`: la invariante no se degrada.

    Es la corrección que cierra el hallazgo bloqueante de la auditoría cruzada. Un
    backfill corre UNA vez; si el alta no engancha el vínculo, toda publicación creada
    después nace en NULL y el dato empeora con cada anuncio.
    """

    def setUp(self):
        self.usuario = _usuario()
        main.app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_crear_publicacion_asigna_vendedor_id(self):
        creada = _publicacion(estado=EstadoPublicacion.BORRADOR.value, vendedor_id=3)
        sesion = _sesion_falsa([None, creada])  # sin perfil de vendedor → lo crea

        def _flush():
            # La BD real asigna el id en el INSERT; sin él no habría qué enganchar.
            for llamada in sesion.add.call_args_list:
                obj = llamada.args[0]
                if isinstance(obj, Vendedor) and obj.id is None:
                    obj.id = 3

        sesion.flush.side_effect = _flush
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "titulo": "Mazda 3 2016", "precio_usd": 12000},
        )

        self.assertEqual(respuesta.status_code, 201)
        agregados = [ll.args[0] for ll in sesion.add.call_args_list]
        vendedor = next(o for o in agregados if isinstance(o, Vendedor))
        publicacion = next(o for o in agregados if isinstance(o, PublicacionInterna))
        self.assertEqual(publicacion.vendedor_id, vendedor.id)
        self.assertIsNotNone(publicacion.vendedor_id)
        # El perfil nace SIN nombre público: publicarlo es una decisión aparte (M5).
        self.assertIsNone(vendedor.nombre_publico)
        self.assertIsNone(vendedor.telefono)


class ContactoPublicacionTests(unittest.TestCase):
    """`POST /marketplace/publicaciones/{id}/contacto` — con sesión y tras el chat.

    Barrera de seguridad (migración 0035): ya no es público. La cobertura del gateo
    vive en `tests/test_chat.py::ContactoGateTests`; acá se cubren las ramas 404/409
    y que el número solo sale con una conversación habilitada.
    """

    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=99, nombre="Compradora")

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, sesion):
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

    def test_contacto_exitoso_devuelve_telefono_y_registra_una_revelacion(self):
        sesion = _sesion_falsa(
            [_publicacion(vendedor_id=3), _vendedor(), _conversacion(habilitado=True)]
        )
        self._con_sesion(sesion)

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["telefono"], "593987654321")
        self.assertEqual(cuerpo["nombre_publico"], "Marcos G.")
        self.assertTrue(cuerpo["whatsapp_url"].startswith("https://wa.me/593987654321"))

        # Exactamente UNA fila de ContactoRevelado, atada a la interna.
        self.assertEqual(sesion.add.call_count, 1)
        registro = sesion.add.call_args.args[0]
        self.assertIsInstance(registro, ContactoRevelado)
        self.assertEqual(registro.publicacion_interna_id, 10)
        self.assertIsNone(registro.publicacion_referenciada_id)
        sesion.commit.assert_called_once()

    def test_sin_conversacion_habilitada_da_422(self):
        """El corazón de la barrera: sin chat respondido, no hay número."""
        sesion = _sesion_falsa([_publicacion(vendedor_id=3), _vendedor(), None])
        self._con_sesion(sesion)

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(respuesta.json()["detail"]["codigo"], "chat_requerido")
        sesion.add.assert_not_called()

    def test_sin_vendedor_enganchado_devuelve_409_y_no_busca_por_usuario(self):
        """Sin fallback: `vendedor_id` NULL sale como 409, no se resuelve por cuenta."""
        sesion = _sesion_falsa([_publicacion(vendedor_id=None)])
        self._con_sesion(sesion)

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 409)
        # Una sola consulta (la de la publicación): no hubo búsqueda de respaldo.
        self.assertEqual(sesion.execute.call_count, 1)
        sesion.add.assert_not_called()

    def test_vendedor_sin_telefono_devuelve_409_y_no_registra(self):
        sesion = _sesion_falsa([_publicacion(vendedor_id=3), _vendedor(telefono=None)])
        self._con_sesion(sesion)

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 409)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()

    def test_sin_perfil_de_vendedor_devuelve_409(self):
        sesion = _sesion_falsa([_publicacion(vendedor_id=None), None])
        self._con_sesion(sesion)

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 409)
        sesion.add.assert_not_called()

    def test_publicacion_inexistente_devuelve_404(self):
        sesion = _sesion_falsa([None])
        self._con_sesion(sesion)

        respuesta = self.cliente.post("/marketplace/publicaciones/999/contacto")

        self.assertEqual(respuesta.status_code, 404)
        sesion.add.assert_not_called()

    def test_ahora_exige_autenticacion(self):
        """La barrera empieza por exigir cuenta: sin sesión, 401 (antes era público)."""
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides[obtener_sesion] = lambda: Mock()

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 401)
        ruta = next(
            r
            for r in main.app.routes
            if getattr(r, "path", None) == "/marketplace/publicaciones/{publicacion_id}/contacto"
        )
        nombres_dependencias = {d.call.__name__ for d in ruta.dependant.dependencies}
        self.assertIn("usuario_actual", nombres_dependencias)


class ContactoNoCuentaAlVendedorTests(unittest.TestCase):
    """El dueño del anuncio ve su propio número, se saltea el chat y no ensucia la
    métrica de demanda (`ContactoRevelado` mide compradores, no autoconsumo)."""

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con(self, sesion, usuario):
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        main.app.dependency_overrides[usuario_actual] = lambda: usuario

    def test_el_vendedor_recibe_el_contacto_pero_no_se_registra(self):
        # id=7 == `_vendedor().usuario_id`: es el dueño, no pasa por el chat.
        sesion = _sesion_falsa([_publicacion(vendedor_id=3), _vendedor()])
        self._con(sesion, _usuario())

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["telefono"], "593987654321")
        # Ni la fila ni el commit: la métrica queda intacta.
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()

    def test_otro_usuario_con_chat_habilitado_si_cuenta(self):
        """Un comprador (id≠7) con la conversación ya respondida: se registra la fila."""
        sesion = _sesion_falsa(
            [_publicacion(vendedor_id=3), _vendedor(), _conversacion(habilitado=True)]
        )
        self._con(sesion, _usuario(id_=99, nombre="Compradora"))

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(sesion.add.call_count, 1)
        self.assertIsInstance(sesion.add.call_args.args[0], ContactoRevelado)

    def test_anonimo_ahora_da_401(self):
        """Sin token ya no se entrega el número: la barrera arranca en la sesión."""
        main.app.dependency_overrides[obtener_sesion] = lambda: Mock()

        respuesta = self.cliente.post("/marketplace/publicaciones/10/contacto")

        self.assertEqual(respuesta.status_code, 401)


def _indice_ruta(path: str, metodo: str) -> int:
    """Posición de una ruta REGISTRADA (no del código fuente) por path + método.

    Se filtra por método a propósito: `/publicaciones/{publicacion_id}` está registrada
    tres veces (GET, PATCH, DELETE), así que buscar solo por path daría la primera y la
    comparación de orden sería falsa.
    """
    rutas = [
        r for r in main.app.routes if getattr(r, "methods", None) and r.path == path
    ]
    for i, r in enumerate(main.app.routes):
        if r in rutas and metodo in r.methods:
            return i
    raise AssertionError(f"No existe la ruta {metodo} {path}")


class OrdenDeRutasTests(unittest.TestCase):
    """§5: las dinámicas se declaran después de las literales del mismo prefijo.

    Se verifica sobre las rutas REGISTRADAS en la app, no leyendo el archivo fuente.
    """

    def test_contacto_se_declara_antes_que_el_detalle_dinamico(self):
        self.assertLess(
            _indice_ruta("/marketplace/publicaciones/{publicacion_id}/contacto", "POST"),
            _indice_ruta("/marketplace/publicaciones/{publicacion_id}", "GET"),
        )

    def test_literales_del_prefijo_publicaciones_siguen_alcanzables(self):
        indice_dinamica = _indice_ruta(
            "/marketplace/publicaciones/{publicacion_id}", "GET"
        )
        for literal in (
            "/marketplace/publicaciones/mias",
            "/marketplace/publicaciones/pendientes-verificacion",
        ):
            self.assertLess(_indice_ruta(literal, "GET"), indice_dinamica)


if __name__ == "__main__":
    unittest.main()
