"""Control de gastos del vehículo (migración 0032).

Alta → listado con resumen derivado → borrado. Sin PostgreSQL: sesión con `Mock`.

    python -m unittest tests.test_gastos_vehiculo -v
"""

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import vehiculo_propio
from src.modules.vehiculos.models.gasto import GastoVehiculo
from src.modules.vehiculos.models.vehiculo import Vehiculo
from src.modules.vehiculos.routers.gastos import _meses_entre, _resumen
from src.modules.vehiculos.schemas.gasto import GastoCrear


def _gasto(tipo, monto, fecha, km=None):
    return GastoVehiculo(
        id=1, vehiculo_id=1, tipo=tipo, monto_usd=Decimal(str(monto)),
        fecha=fecha, kilometraje=km, nota=None,
        creado_en=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [
        Mock(
            scalar_one=Mock(return_value=r),
            scalar_one_or_none=Mock(return_value=r),
            scalars=Mock(return_value=Mock(all=Mock(return_value=r if isinstance(r, list) else [r]))),
        )
        for r in resultados
    ]
    s.add = Mock()
    s.commit = Mock()
    s.delete = Mock()

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = datetime.now(timezone.utc)

    s.refresh.side_effect = _refresh
    return s


class SchemaTests(unittest.TestCase):
    def test_monto_debe_ser_positivo(self):
        with self.assertRaises(Exception):
            GastoCrear(tipo="combustible", monto_usd=0, fecha=date(2026, 8, 1))

    def test_tipo_fuera_de_catalogo(self):
        with self.assertRaises(Exception):
            GastoCrear(tipo="nave", monto_usd=10, fecha=date(2026, 8, 1))

    def test_alta_minima_valida(self):
        g = GastoCrear(tipo="combustible", monto_usd=Decimal("25.50"), fecha=date(2026, 8, 1))
        self.assertEqual(g.tipo, "combustible")


class ResumenTests(unittest.TestCase):
    def test_meses_entre_inclusive(self):
        self.assertEqual(_meses_entre(date(2026, 1, 10), date(2026, 1, 20)), 1)
        self.assertEqual(_meses_entre(date(2026, 1, 1), date(2026, 3, 31)), 3)

    def test_resumen_desglosa_por_tipo_y_promedia(self):
        filas = [
            _gasto("combustible", 30, date(2026, 1, 5)),
            _gasto("combustible", 30, date(2026, 2, 5)),
            _gasto("seguro", 120, date(2026, 3, 5)),
        ]
        sesion = _sesion(Decimal("0"))  # sum(Mantenimiento.costo) → 0
        r = _resumen(sesion, 1, filas)
        self.assertEqual(r.total_usd, Decimal("180"))
        self.assertEqual(r.cantidad, 3)
        self.assertEqual(r.meses_con_datos, 3)
        self.assertEqual(r.promedio_mensual_usd, Decimal("60.00"))
        self.assertEqual(r.por_tipo[0].tipo, "seguro")  # mayor total primero
        self.assertEqual(r.por_tipo[0].total_usd, Decimal("120"))

    def test_resumen_vacio_incluye_costo_mantenimientos(self):
        sesion = _sesion(Decimal("340"))
        r = _resumen(sesion, 1, [])
        self.assertEqual(r.total_usd, Decimal("0"))
        self.assertEqual(r.mantenimientos_costo_usd, Decimal("340"))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[vehiculo_propio] = lambda: Vehiculo(
            id=9, usuario_id=7, placa="ABC1234"
        )

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_alta_201_cuelga_del_vehiculo(self):
        sesion = _sesion()
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/vehiculos/9/gastos",
            json={"tipo": "combustible", "monto_usd": "25.50", "fecha": "2026-08-01"},
        )
        self.assertEqual(r.status_code, 201)
        creado = sesion.add.call_args.args[0]
        self.assertIsInstance(creado, GastoVehiculo)
        self.assertEqual(creado.vehiculo_id, 9)

    def test_listar_devuelve_resumen_e_items(self):
        filas = [_gasto("combustible", 40, date(2026, 8, 1), km=50000)]
        sesion = _sesion(filas, Decimal("0"))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.get("/vehiculos/9/gastos")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["resumen"]["cantidad"], 1)
        self.assertEqual(len(cuerpo["items"]), 1)
        self.assertEqual(cuerpo["items"][0]["tipo"], "combustible")

    def test_borrar_inexistente_da_404(self):
        sesion = _sesion(None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.delete("/vehiculos/9/gastos/999")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
