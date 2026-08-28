"""Sello "revisado por mecánica" con códigos de un solo uso (migración 0028).

Un admin genera códigos para una mecánica; el vendedor canjea UNO en su publicación y
aparece el sello. Código: se usa una vez y expira. Sin PostgreSQL: sesión con `Mock`.

    python -m unittest tests.test_sello_mecanica -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    CodigoCertificacion,
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
)
from src.modules.marketplace.routers.certificacion import _generar_codigo
from src.modules.marketplace.schemas import PublicacionInternaSalida


def _res(v):
    filas = v if isinstance(v, list) else [v]
    return Mock(
        scalar_one_or_none=Mock(return_value=v),
        one=Mock(return_value=v),
        all=Mock(return_value=filas),
        scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [_res(r) for r in resultados]
    s.add = Mock()
    s.commit = Mock()

    def _refresh(obj):
        # Simula lo que hace la BD tras el commit: rellena defaults del servidor.
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = 1

    s.refresh.side_effect = _refresh
    return s


def _usuario(id_=7):
    return Usuario(id=id_, email="v@example.com", password_hash="x", nombre="Vendedora")


def _pub():
    p = PublicacionInterna(
        id=10,
        usuario_id=7,
        placa="ABC1234",
        titulo="Auto",
        precio_usd=10000,
        estado=EstadoPublicacion.ACTIVA.value,
        plan=PlanPublicacion.LIGHT.value,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=False,
        creado_en=datetime(2026, 8, 1, tzinfo=timezone.utc),
        renovada_en=datetime.now(timezone.utc),
    )
    p.ficha = None
    p.fotos = []
    p.vehiculo = None
    p.mecanica_nombre = None
    p.mecanica_ciudad = None
    p.certificado_mecanica_en = None
    return p


def _codigo(*, usado=False, expirado=False, nombre="Taller Vera"):
    return CodigoCertificacion(
        id=1,
        codigo="MEC-ABCD-EFGH",
        mecanica_nombre=nombre,
        mecanica_ciudad="Manta",
        expira_en=datetime.now(timezone.utc)
        + timedelta(days=-1 if expirado else 20),
        usado_en=datetime.now(timezone.utc) if usado else None,
    )


class CodigoTests(unittest.TestCase):
    def test_formato_del_codigo(self):
        c = _generar_codigo()
        self.assertRegex(c, r"^MEC-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        # Sin caracteres ambiguos.
        for malo in "01OIL":
            self.assertNotIn(malo, c)


class SalidaSelloTests(unittest.TestCase):
    def test_sin_sello_es_none(self):
        self.assertIsNone(PublicacionInternaSalida.desde_modelo(_pub()).sello_mecanica)

    def test_con_sello_expone_nombre_ciudad_fecha(self):
        p = _pub()
        p.mecanica_nombre = "Taller Vera"
        p.mecanica_ciudad = "Manta"
        p.certificado_mecanica_en = datetime(2026, 8, 25, tzinfo=timezone.utc)
        s = PublicacionInternaSalida.desde_modelo(p)
        self.assertIsNotNone(s.sello_mecanica)
        self.assertEqual(s.sello_mecanica.nombre, "Taller Vera")
        self.assertEqual(s.sello_mecanica.ciudad, "Manta")


class CertificarEndpointTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_canje_valido_pone_el_sello_y_marca_el_codigo(self):
        pub, cod = _pub(), _codigo()
        sesion = _sesion(pub, cod)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

        r = self.cliente.post(
            "/marketplace/publicaciones/10/certificar", json={"codigo": "mec-abcd-efgh"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(pub.mecanica_nombre, "Taller Vera")
        self.assertIsNotNone(pub.certificado_mecanica_en)
        self.assertIsNotNone(cod.usado_en)
        self.assertEqual(cod.usado_publicacion_id, 10)
        self.assertEqual(r.json()["sello_mecanica"]["nombre"], "Taller Vera")

    def test_codigo_inexistente_da_422(self):
        sesion = _sesion(_pub(), None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/publicaciones/10/certificar", json={"codigo": "MEC-ZZZZ-ZZZZ"}
        )
        self.assertEqual(r.status_code, 422)

    def test_codigo_ya_usado_da_422(self):
        sesion = _sesion(_pub(), _codigo(usado=True))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/publicaciones/10/certificar", json={"codigo": "MEC-ABCD-EFGH"}
        )
        self.assertEqual(r.status_code, 422)
        self.assertIn("us", r.json()["detail"].lower())

    def test_codigo_expirado_da_422(self):
        sesion = _sesion(_pub(), _codigo(expirado=True))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/publicaciones/10/certificar", json={"codigo": "MEC-ABCD-EFGH"}
        )
        self.assertEqual(r.status_code, 422)
        self.assertIn("expir", r.json()["detail"].lower())

    def test_publicacion_ajena_da_404(self):
        sesion = _sesion(None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/publicaciones/999/certificar", json={"codigo": "MEC-ABCD-EFGH"}
        )
        self.assertEqual(r.status_code, 404)


class CrearCodigosAdminTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[admin_actual] = lambda: _usuario(id_=1)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_admin_genera_n_codigos(self):
        sesion = _sesion()
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

        r = self.cliente.post(
            "/marketplace/certificacion/codigos",
            json={"mecanica_nombre": "Taller Vera", "mecanica_ciudad": "Manta", "cantidad": 3},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(sesion.add.call_count, 3)
        self.assertEqual(len(r.json()), 3)
        for c in r.json():
            self.assertEqual(c["mecanica_nombre"], "Taller Vera")
            self.assertIsNone(c["usado_en"])


if __name__ == "__main__":
    unittest.main()
