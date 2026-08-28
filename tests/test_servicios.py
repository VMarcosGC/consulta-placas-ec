"""Directorio de servicios automotrices (migración 0029).

Alta → moderación → directorio público. Mismo patrón que las referencias.
Sin PostgreSQL: sesión con `Mock`.

    python -m unittest tests.test_servicios -v
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import EstadoModeracion, Servicio
from src.modules.marketplace.schemas import ServicioCrear


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
        for campo, val in (
            ("id", 1),
            ("creado_en", datetime.now(timezone.utc)),
            ("estado_moderacion", EstadoModeracion.PENDIENTE.value),
            ("activo", True),
            ("certificado", False),
        ):
            if getattr(obj, campo, None) is None:
                setattr(obj, campo, val)

    s.refresh.side_effect = _refresh
    return s


def _usuario(id_=7):
    return Usuario(id=id_, email="u@example.com", password_hash="x", nombre="Ana")


BASE = {
    "nombre": "Taller Vera",
    "categoria": "mecanica",
    "provincia": "Manabí",
    "ciudad": "Manta",
}


class SchemaTests(unittest.TestCase):
    def test_provincia_fuera_de_catalogo_no_valida(self):
        with self.assertRaises(Exception):
            ServicioCrear(**{**BASE, "provincia": "Marte"})

    def test_categoria_fuera_de_catalogo_no_valida(self):
        with self.assertRaises(Exception):
            ServicioCrear(**{**BASE, "categoria": "nave_espacial"})

    def test_alta_minima_valida(self):
        s = ServicioCrear(**BASE)
        self.assertEqual(s.categoria, "mecanica")


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_alta_entra_pendiente(self):
        sesion = _sesion()
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

        r = self.cliente.post("/marketplace/servicios", json=BASE)
        self.assertEqual(r.status_code, 201)
        creado = sesion.add.call_args.args[0]
        self.assertIsInstance(creado, Servicio)
        self.assertEqual(creado.aportado_por_usuario_id, 7)
        self.assertEqual(r.json()["estado_moderacion"], "pendiente")

    def test_alta_sin_sesion_da_401(self):
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion()
        r = self.cliente.post("/marketplace/servicios", json=BASE)
        self.assertEqual(r.status_code, 401)

    def test_directorio_publico_lista_solo_aprobados(self):
        aprobado = Servicio(
            id=1,
            nombre="Taller Vera",
            categoria="mecanica",
            provincia="Manabí",
            ciudad="Manta",
            certificado=False,
            estado_moderacion=EstadoModeracion.APROBADA.value,
            activo=True,
            creado_en=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion([aprobado])
        r = self.cliente.get("/marketplace/servicios")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["nombre"], "Taller Vera")

    def test_moderar_inexistente_da_404(self):
        main.app.dependency_overrides[admin_actual] = lambda: _usuario(id_=1)
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion(None)
        r = self.cliente.post(
            "/marketplace/servicios/999/moderar", json={"decision": "aprobada"}
        )
        self.assertEqual(r.status_code, 404)

    def test_moderar_aprueba_y_puede_certificar(self):
        s = Servicio(
            id=5,
            nombre="Mecánica Vera",
            categoria="mecanica_certificada",
            provincia="Manabí",
            ciudad="Manta",
            certificado=False,
            estado_moderacion=EstadoModeracion.PENDIENTE.value,
            activo=True,
            creado_en=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        sesion = _sesion(s)
        sesion.refresh = Mock()
        main.app.dependency_overrides[admin_actual] = lambda: _usuario(id_=1)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/servicios/5/moderar",
            json={"decision": "aprobada", "certificado": True},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(s.estado_moderacion, "aprobada")
        self.assertTrue(s.certificado)


if __name__ == "__main__":
    unittest.main()
