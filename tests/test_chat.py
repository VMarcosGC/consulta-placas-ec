"""Chat interno comprador↔vendedor + barrera del WhatsApp (migración 0035).

Sin PostgreSQL: sesión con `Mock` (mismo patrón que test_agendamiento).

    python -m unittest tests.test_chat -v
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    Conversacion,
    EstadoConversacion,
    Mensaje,
    PublicacionInterna,
    RolConversacion,
    Vendedor,
)
from src.modules.marketplace.schemas import (
    ConversacionCrear,
    EstadoConversacionPatch,
    MensajeCrear,
)

AHORA = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _res(v):
    filas = v if isinstance(v, list) else [v]
    return Mock(
        scalar_one_or_none=Mock(return_value=v),
        scalar_one=Mock(return_value=v),
        scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
        all=Mock(return_value=filas),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [_res(r) for r in resultados]
    s.add = Mock()
    s.flush = Mock()
    s.commit = Mock()

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = AHORA

    s.refresh.side_effect = _refresh
    return s


def _usuario(id_=7, email="comprador@example.com", nombre="Ana"):
    return Usuario(id=id_, email=email, password_hash="x", nombre=nombre)


def _vendedor(id_=3, usuario_id=99, tel="593999000111"):
    return Vendedor(
        id=id_, usuario_id=usuario_id, nombre_publico="AutosQuito",
        telefono=tel, tipo="particular",
    )


def _pub(id_=10, vendedor_id=3):
    return PublicacionInterna(
        id=id_, placa="PABC1234", titulo="Kia Sportage 2019",
        precio_usd=Decimal("18500.00"), estado="activa", vendedor_id=vendedor_id,
    )


def _conv(
    id_=1,
    comprador_id=7,
    vendedor_id=99,
    estado=EstadoConversacion.ABIERTA.value,
    habilitado=None,
    mensajes=None,
    con_publicacion=True,
):
    c = Conversacion(
        id=id_,
        publicacion_interna_id=10,
        comprador_usuario_id=comprador_id,
        vendedor_usuario_id=vendedor_id,
        estado=estado,
        no_leidos_comprador=0,
        no_leidos_vendedor=0,
    )
    c.contacto_habilitado_en = habilitado
    c.ultimo_mensaje_en = None
    c.mensajes = mensajes if mensajes is not None else []
    if con_publicacion:
        p = _pub()
        p.fotos = []
        p.vendedor = _vendedor()
        c.publicacion = p
    c.comprador = _usuario()
    return c


def _msg(rol=RolConversacion.COMPRADOR.value, autor=7, cuerpo="Hola"):
    m = Mensaje(
        id=1, conversacion_id=1, autor_usuario_id=autor, rol_autor=rol, cuerpo=cuerpo
    )
    m.leido_en = None
    m.creado_en = AHORA
    return m


# ════════════════════════════ Schemas ════════════════════════════


class SchemaTests(unittest.TestCase):
    def test_mensaje_vacio_no_valida(self):
        with self.assertRaises(Exception):
            MensajeCrear(cuerpo="   ")

    def test_mensaje_se_recorta(self):
        self.assertEqual(MensajeCrear(cuerpo="  hola  ").cuerpo, "hola")

    def test_conversacion_crear_sin_mensaje(self):
        self.assertIsNone(ConversacionCrear().mensaje)

    def test_conversacion_crear_mensaje_blanco_es_none(self):
        self.assertIsNone(ConversacionCrear(mensaje="   ").mensaje)

    def test_estado_patch_valor_invalido(self):
        with self.assertRaises(Exception):
            EstadoConversacionPatch(estado="cerrada")


# ══════════════════ Barrera del WhatsApp (POST /publicaciones/{id}/contacto) ══════════════════


class ContactoGateTests(unittest.TestCase):
    RUTA = "/marketplace/publicaciones/10/contacto"

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _como(self, usuario):
        main.app.dependency_overrides[usuario_actual] = lambda: usuario

    def test_sin_sesion_da_401(self):
        main.app.dependency_overrides[obtener_sesion] = lambda: Mock()
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 401)

    def test_sin_conversacion_da_422_chat_requerido(self):
        self._como(_usuario(id_=7))
        sesion = _sesion(_pub(), _vendedor(usuario_id=99), None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 422)
        det = r.json()["detail"]
        self.assertEqual(det["codigo"], "chat_requerido")
        self.assertIsNone(det["conversacion_id"])

    def test_conversacion_sin_respuesta_da_422_con_id(self):
        self._como(_usuario(id_=7))
        conv = _conv(id_=55, habilitado=None)
        sesion = _sesion(_pub(), _vendedor(usuario_id=99), conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 422)
        det = r.json()["detail"]
        self.assertEqual(det["codigo"], "chat_requerido")
        self.assertEqual(det["conversacion_id"], 55)

    def test_conversacion_bloqueada_da_422_chat_bloqueado(self):
        self._como(_usuario(id_=7))
        conv = _conv(estado=EstadoConversacion.BLOQUEADA.value, habilitado=AHORA)
        sesion = _sesion(_pub(), _vendedor(usuario_id=99), conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["codigo"], "chat_bloqueado")

    def test_contacto_habilitado_devuelve_whatsapp(self):
        self._como(_usuario(id_=7))
        conv = _conv(habilitado=AHORA)
        sesion = _sesion(_pub(), _vendedor(usuario_id=99), conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["telefono"], "593999000111")
        self.assertIn("wa.me/593999000111", cuerpo["whatsapp_url"])
        # se registró la métrica de demanda
        self.assertTrue(sesion.add.called)

    def test_el_vendedor_ve_su_numero_sin_chat(self):
        # quien consulta ES el dueño (usuario 99 == vendedor.usuario_id)
        self._como(_usuario(id_=99, email="v@example.com"))
        sesion = _sesion(_pub(), _vendedor(usuario_id=99))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 200)
        # NO se registra ContactoRevelado para el propio vendedor
        self.assertFalse(sesion.add.called)

    def test_vendedor_sin_telefono_da_409(self):
        self._como(_usuario(id_=7))
        sesion = _sesion(_pub(), _vendedor(usuario_id=99, tel=None))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 409)

    def test_publicacion_inexistente_da_404(self):
        self._como(_usuario(id_=7))
        sesion = _sesion(None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA)
        self.assertEqual(r.status_code, 404)


# ══════════════════ Abrir conversación ══════════════════


class AbrirConversacionTests(unittest.TestCase):
    RUTA = "/marketplace/publicaciones/10/conversacion"

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_sobre_propio_anuncio_da_422(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=99)
        sesion = _sesion(_pub(), _vendedor(usuario_id=99))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={})
        self.assertEqual(r.status_code, 422)

    def test_crea_hilo_y_primer_mensaje(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        creada = _conv(mensajes=[_msg(cuerpo="Hola, ¿sigue disponible?")])
        sesion = _sesion(
            _pub(),                       # lookup publicación
            _vendedor(usuario_id=99),     # _vendedor_de
            None,                         # conv existente → no hay
            creada,                       # recarga tras commit
        )
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={"mensaje": "Hola, ¿sigue disponible?"})
        self.assertEqual(r.status_code, 200)
        agregados = [c.args[0] for c in sesion.add.call_args_list]
        self.assertTrue(any(isinstance(x, Conversacion) for x in agregados))
        self.assertTrue(any(isinstance(x, Mensaje) for x in agregados))
        cuerpo = r.json()
        self.assertEqual(cuerpo["mi_rol"], "comprador")
        self.assertFalse(cuerpo["contacto_habilitado"])

    def test_publicacion_inexistente_da_404(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        sesion = _sesion(None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={})
        self.assertEqual(r.status_code, 404)


# ══════════════════ Enviar mensaje / desbloqueo ══════════════════


class EnviarMensajeTests(unittest.TestCase):
    RUTA = "/marketplace/conversaciones/1/mensajes"

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_respuesta_del_vendedor_habilita_contacto(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(
            id_=99, email="v@example.com"
        )
        conv = _conv(habilitado=None, mensajes=[_msg(autor=7)])  # ya hay msg del comprador
        sesion = _sesion(conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={"cuerpo": "Sí, disponible. Te paso datos."})
        self.assertEqual(r.status_code, 201)
        self.assertIsNotNone(conv.contacto_habilitado_en)
        self.assertEqual(conv.no_leidos_comprador, 1)

    def test_mensaje_del_comprador_no_habilita_contacto(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        conv = _conv(habilitado=None, mensajes=[])
        sesion = _sesion(conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={"cuerpo": "Hola"})
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(conv.contacto_habilitado_en)
        self.assertEqual(conv.no_leidos_vendedor, 1)

    def test_tercero_no_participante_da_404(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=555)
        conv = _conv()
        sesion = _sesion(conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={"cuerpo": "Hola"})
        self.assertEqual(r.status_code, 404)

    def test_chat_bloqueado_da_422(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        conv = _conv(estado=EstadoConversacion.BLOQUEADA.value)
        sesion = _sesion(conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(self.RUTA, json={"cuerpo": "Hola"})
        self.assertEqual(r.status_code, 422)


class CompartirYBloquearTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_solo_el_vendedor_comparte_contacto(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)  # comprador
        conv = _conv()
        sesion = _sesion(conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post("/marketplace/conversaciones/1/compartir-contacto")
        self.assertEqual(r.status_code, 422)

    def test_vendedor_comparte_contacto(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(
            id_=99, email="v@example.com"
        )
        conv = _conv(habilitado=None)
        # 1ª carga; 2ª recarga tras commit
        sesion = _sesion(conv, _conv(habilitado=AHORA))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post("/marketplace/conversaciones/1/compartir-contacto")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(conv.contacto_habilitado_en)

    def test_comprador_no_puede_bloquear(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        conv = _conv()
        sesion = _sesion(conv)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.patch(
            "/marketplace/conversaciones/1", json={"estado": "bloqueada"}
        )
        self.assertEqual(r.status_code, 422)


class BandejaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_no_leidos_suma_segun_rol(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        # (comprador_id, vendedor_id, nl_comprador, nl_vendedor)
        filas = [(7, 99, 3, 0), (50, 7, 0, 2)]  # soy comprador en una, vendedor en otra
        sesion = _sesion(filas)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/conversaciones/no-leidos")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 5)

    def test_lista_conversaciones_del_usuario(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        conv = _conv(mensajes=[_msg(cuerpo="Hola")])
        sesion = _sesion([conv])
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/conversaciones")
        self.assertEqual(r.status_code, 200)
        item = r.json()[0]
        self.assertEqual(item["mi_rol"], "comprador")
        self.assertEqual(item["ultimo_mensaje"], "Hola")
        self.assertEqual(item["contraparte_nombre"], "AutosQuito")


if __name__ == "__main__":
    unittest.main()
