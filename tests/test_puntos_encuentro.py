"""Puntos de encuentro seguros (migración 0033).

Catálogo curado (admin) + presencias que anuncia el dueño de una publicación. Sin
PostgreSQL: sesión con `Mock`.

    python -m unittest tests.test_puntos_encuentro -v
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import admin_actual, usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    EstadoPresencia,
    EstadoPublicacion,
    PlanPublicacion,
    PresenciaPunto,
    PublicacionInterna,
    PuntoEncuentro,
)
from src.modules.marketplace.schemas import PresenciaCrear

HOY = date(2026, 8, 30)
AHORA = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _resultado(r):
    filas = r if isinstance(r, list) else [r]
    return Mock(
        scalar_one_or_none=Mock(return_value=r),
        scalar_one=Mock(return_value=r),
        one=Mock(return_value=r),
        all=Mock(return_value=filas),
        scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [_resultado(r) for r in resultados]
    s.add = Mock()
    s.commit = Mock()
    s.delete = Mock()

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = AHORA
        if getattr(obj, "actualizado_en", None) is None:
            obj.actualizado_en = AHORA

    s.refresh.side_effect = _refresh
    return s


def _usuario(id_=7):
    return Usuario(id=id_, email="u@example.com", password_hash="x", nombre="Ana")


def _punto(id_=1, activo=True):
    return PuntoEncuentro(
        id=id_, nombre="CC El Recreo", ciudad="Quito", sector="Sur",
        direccion="Av. Test", referencia=None, latitud=None, longitud=None,
        horario=None, tiene_seguridad=False, notas=None, activo=activo, orden=1,
    )


def _publicacion(id_=10, usuario_id=7, estado=EstadoPublicacion.ACTIVA.value):
    return PublicacionInterna(
        id=id_, usuario_id=usuario_id, placa="ABC1234", precio_usd=Decimal("9000"),
        plan=PlanPublicacion.LIGHT.value, estado=estado, destacado=False,
        creado_en=AHORA, renovada_en=AHORA, fotos=[], vehiculo=None,
    )


class SchemaTests(unittest.TestCase):
    def test_fecha_pasada_no_valida(self):
        with self.assertRaises(Exception):
            PresenciaCrear(publicacion_id=1, fecha=date(2000, 1, 1), franja="manana")

    def test_alta_minima_valida(self):
        p = PresenciaCrear(publicacion_id=1, fecha=date.today(), franja="tarde")
        self.assertEqual(p.franja.value, "tarde")


class ListarPuntosTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_lista_publica_incluye_conteo(self):
        punto = _punto()
        sesion = _sesion([punto], [(1, 3)])
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/puntos-encuentro")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo[0]["nombre"], "CC El Recreo")
        self.assertEqual(cuerpo[0]["presencias_activas"], 3)


class DetallePuntoTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_punto_inexistente_da_404(self):
        sesion = Mock()
        sesion.get.return_value = None
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/puntos-encuentro/999")
        self.assertEqual(r.status_code, 404)

    def test_punto_inactivo_da_404(self):
        sesion = Mock()
        sesion.get.return_value = _punto(activo=False)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/puntos-encuentro/1")
        self.assertEqual(r.status_code, 404)

    def test_detalle_lista_autos_anunciados(self):
        punto = _punto()
        pub = _publicacion()
        presencia = PresenciaPunto(
            id=5, punto_id=1, publicacion_interna_id=pub.id, usuario_id=7,
            fecha=HOY, franja="tarde", estado=EstadoPresencia.ANUNCIADA.value,
            nota=None, creado_en=AHORA,
        )
        presencia.publicacion = pub
        sesion = Mock()
        sesion.get.return_value = punto
        sesion.execute.side_effect = [_resultado([presencia])]
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/puntos-encuentro/1")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(len(cuerpo["presencias"]), 1)
        self.assertEqual(cuerpo["presencias"][0]["vehiculo"]["placa"], "ABC1234")


class AnunciarPresenciaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_anuncia_auto_propio_activo(self):
        punto = _punto()
        pub = _publicacion()
        sesion = Mock()
        sesion.get.return_value = punto
        sesion.execute.side_effect = [_resultado(pub)]
        sesion.add = Mock()
        sesion.commit = Mock()
        sesion.refresh.side_effect = lambda o: setattr(o, "id", 5) or setattr(
            o, "creado_en", AHORA
        )
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro/1/presencias",
            json={"publicacion_id": 10, "fecha": str(date.today()), "franja": "manana"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["vehiculo"]["publicacion_id"], 10)

    def test_punto_inexistente_da_404(self):
        sesion = Mock()
        sesion.get.return_value = None
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro/999/presencias",
            json={"publicacion_id": 10, "fecha": str(date.today()), "franja": "manana"},
        )
        self.assertEqual(r.status_code, 404)

    def test_publicacion_ajena_da_404(self):
        sesion = Mock()
        sesion.get.return_value = _punto()
        sesion.execute.side_effect = [_resultado(None)]
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro/1/presencias",
            json={"publicacion_id": 999, "fecha": str(date.today()), "franja": "manana"},
        )
        self.assertEqual(r.status_code, 404)

    def test_publicacion_no_activa_da_422(self):
        sesion = Mock()
        sesion.get.return_value = _punto()
        sesion.execute.side_effect = [
            _resultado(_publicacion(estado=EstadoPublicacion.PAUSADA.value))
        ]
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro/1/presencias",
            json={"publicacion_id": 10, "fecha": str(date.today()), "franja": "manana"},
        )
        self.assertEqual(r.status_code, 422)

    def test_sin_sesion_da_401(self):
        main.app.dependency_overrides.clear()
        sesion = Mock()
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro/1/presencias",
            json={"publicacion_id": 10, "fecha": str(date.today()), "franja": "manana"},
        )
        self.assertEqual(r.status_code, 401)


class MisPresenciasTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_lista_las_propias(self):
        punto = _punto()
        pub = _publicacion()
        presencia = PresenciaPunto(
            id=5, punto_id=1, publicacion_interna_id=pub.id, usuario_id=7,
            fecha=HOY, franja="noche", estado=EstadoPresencia.ANUNCIADA.value,
            nota="Llego 10 min antes", creado_en=AHORA,
        )
        presencia.punto = punto
        presencia.publicacion = pub
        sesion = Mock()
        sesion.execute.side_effect = [_resultado([presencia])]
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/marketplace/presencias/mias")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo[0]["punto"]["nombre"], "CC El Recreo")


class ActualizarEliminarPresenciaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_ajena_o_inexistente_da_404(self):
        sesion = Mock()
        sesion.execute.side_effect = [_resultado(None)]
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.delete("/marketplace/presencias/999")
        self.assertEqual(r.status_code, 404)

    def test_no_se_puede_volver_a_anunciada(self):
        with self.assertRaises(Exception):
            from src.modules.marketplace.schemas import PresenciaActualizar
            PresenciaActualizar(estado="anunciada")

    def test_cancelar_propia(self):
        punto = _punto()
        pub = _publicacion()
        presencia = PresenciaPunto(
            id=5, punto_id=1, publicacion_interna_id=pub.id, usuario_id=7,
            fecha=HOY, franja="tarde", estado=EstadoPresencia.ANUNCIADA.value,
            nota=None, creado_en=AHORA,
        )
        presencia.punto = punto
        presencia.publicacion = pub
        sesion = Mock()
        sesion.execute.side_effect = [_resultado(presencia), _resultado(presencia)]
        sesion.commit = Mock()
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.patch(
            "/marketplace/presencias/5", json={"estado": "cancelada"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(presencia.estado, "cancelada")


class AdminPuntoTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_crear_requiere_admin(self):
        sesion = _sesion()
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro",
            json={"nombre": "Nuevo punto", "direccion": "Av. X"},
        )
        self.assertEqual(r.status_code, 401)

    def test_admin_crea_punto(self):
        sesion = _sesion()
        main.app.dependency_overrides[admin_actual] = lambda: _usuario(id_=1)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/puntos-encuentro",
            json={"nombre": "Nuevo punto", "direccion": "Av. X"},
        )
        self.assertEqual(r.status_code, 201)
        creado = sesion.add.call_args.args[0]
        self.assertIsInstance(creado, PuntoEncuentro)
        self.assertEqual(creado.nombre, "Nuevo punto")

    def test_admin_desactiva_punto(self):
        punto = _punto()
        sesion = Mock()
        sesion.get.return_value = punto
        sesion.commit = Mock()
        main.app.dependency_overrides[admin_actual] = lambda: _usuario(id_=1)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.patch(
            "/marketplace/puntos-encuentro/1", json={"activo": False}
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(punto.activo)


if __name__ == "__main__":
    unittest.main()
