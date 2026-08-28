"""Calificaciones de comprador a vendedor (migración 0027).

Un comprador califica a un vendedor (1..5 + comentario). Upsert por (autor, vendedor);
nadie califica su propio perfil; sin calificaciones el promedio es `None` (línea base).

Sin PostgreSQL: sesión con `Mock`.

    python -m unittest tests.test_calificaciones -v
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual, usuario_actual_opcional
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import Calificacion, Vendedor
from src.modules.marketplace.routers.calificaciones import (
    _autor_nombre,
    resumen_calificaciones,
)
from src.modules.marketplace.schemas import CalificacionCrear


def _res(valor):
    filas = valor if isinstance(valor, list) else [valor]
    return Mock(
        scalar_one_or_none=Mock(return_value=valor),
        one=Mock(return_value=valor),
        all=Mock(return_value=filas),
        scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [_res(r) for r in resultados]
    return s


def _usuario(id_=7, nombre="Marcos G."):
    return Usuario(id=id_, email="c@example.com", password_hash="x", nombre=nombre)


def _vendedor(id_=3, usuario_id=99):
    return Vendedor(id=id_, usuario_id=usuario_id, nombre_publico="Autos X")


class HelpersTests(unittest.TestCase):
    def test_autor_nombre_es_solo_el_primer_nombre_o_generico(self):
        self.assertEqual(_autor_nombre(_usuario(nombre="Marcos Guerrero")), "Marcos")
        self.assertEqual(_autor_nombre(_usuario(nombre="")), "Un comprador")
        self.assertEqual(_autor_nombre(None), "Un comprador")

    def test_resumen_sin_calificaciones_da_promedio_none(self):
        r = resumen_calificaciones(_sesion((None, 0)), 3)
        self.assertIsNone(r.promedio)
        self.assertEqual(r.total, 0)

    def test_resumen_redondea_a_un_decimal(self):
        r = resumen_calificaciones(_sesion((4.3333, 3)), 3)
        self.assertEqual(r.promedio, 4.3)
        self.assertEqual(r.total, 3)


class RangoEstrellasSchemaTests(unittest.TestCase):
    def test_fuera_de_1_a_5_no_valida(self):
        for mala in (0, 6, -1):
            with self.assertRaises(Exception):
                CalificacionCrear(estrellas=mala)
        for buena in (1, 3, 5):
            self.assertEqual(CalificacionCrear(estrellas=buena).estrellas, buena)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_calificar_el_propio_perfil_da_422(self):
        yo = _usuario(id_=7)
        vendedor_mio = _vendedor(id_=3, usuario_id=7)  # mismo usuario
        main.app.dependency_overrides[usuario_actual] = lambda: yo
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion(vendedor_mio)

        r = self.cliente.post(
            "/marketplace/vendedores/3/calificar", json={"estrellas": 5}
        )
        self.assertEqual(r.status_code, 422)

    def test_calificar_vendedor_inexistente_da_404(self):
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion(None)

        r = self.cliente.post(
            "/marketplace/vendedores/999/calificar", json={"estrellas": 4}
        )
        self.assertEqual(r.status_code, 404)

    def test_calificar_nuevo_persiste_y_devuelve_resumen(self):
        yo = _usuario(id_=7)
        vendedor = _vendedor(id_=3, usuario_id=99)
        # execute: (1) _vendedor, (2) existente=None, (3) _listado filas=[],
        # (4) _listado propia=None, (5) resumen (avg, count)
        sesion = _sesion(vendedor, None, [], None, (5.0, 1))
        sesion.add = Mock()
        sesion.commit = Mock()
        main.app.dependency_overrides[usuario_actual] = lambda: yo
        main.app.dependency_overrides[usuario_actual_opcional] = lambda: yo
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

        r = self.cliente.post(
            "/marketplace/vendedores/3/calificar",
            json={"estrellas": 5, "comentario": "Buen trato"},
        )
        self.assertEqual(r.status_code, 200)
        agregada = sesion.add.call_args.args[0]
        self.assertIsInstance(agregada, Calificacion)
        self.assertEqual(agregada.estrellas, 5)
        self.assertEqual(r.json()["resumen"]["promedio"], 5.0)
        sesion.commit.assert_called_once()

    def test_listado_publico_sin_sesion_funciona(self):
        vendedor = _vendedor(id_=3)
        c = Calificacion(
            autor_usuario_id=8,
            vendedor_id=3,
            estrellas=4,
            comentario="ok",
            creado_en=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        # execute: (1) _vendedor, (2) _listado filas=[(c, usuario)], (3) resumen
        sesion = _sesion(vendedor, [(c, _usuario(id_=8, nombre="Ana Ruiz"))], (4.0, 1))
        main.app.dependency_overrides[usuario_actual_opcional] = lambda: None
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion

        r = self.cliente.get("/marketplace/vendedores/3/calificaciones")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["resumen"]["promedio"], 4.0)
        self.assertEqual(d["items"][0]["autor"], "Ana")
        self.assertIsNone(d["mia"])


if __name__ == "__main__":
    unittest.main()
