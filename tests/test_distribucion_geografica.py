"""Distribución geográfica del marketplace + filtro por provincia/región.

La portada muestra "¿dónde están los autos?": conteo de publicaciones activas por
provincia y región, derivado de `ciudad` (no hay columna provincia). Desde ahí el
comprador filtra `GET /marketplace/buscar?provincia=…` / `?region=…`.

Cubre: los helpers puros de `geografia.py`, el endpoint `/marketplace/distribucion`
con filas mockeadas, y la validación 422 del filtro geográfico en `/buscar`.

    python -m unittest tests.test_distribucion_geografica -v
"""

import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.marketplace import geografia


class GeografiaHelpersTests(unittest.TestCase):
    def test_ciudad_del_catalogo_resuelve_provincia_y_region(self):
        self.assertEqual(geografia.provincia_de("Quito"), "Pichincha")
        self.assertEqual(geografia.region_de("Quito"), "Sierra")
        self.assertEqual(geografia.provincia_de("Guayaquil"), "Guayas")
        self.assertEqual(geografia.region_de("Guayaquil"), "Costa")

    def test_dos_ciudades_pueden_caer_en_la_misma_provincia(self):
        self.assertEqual(geografia.provincia_de("Manta"), "Manabí")
        self.assertEqual(geografia.provincia_de("Portoviejo"), "Manabí")

    def test_alias_y_tipeo_de_texto_libre_se_normalizan(self):
        self.assertEqual(geografia.ciudad_canonica("sto domingo"), "Santo Domingo")
        self.assertEqual(geografia.ciudad_canonica("GYE"), "Guayaquil")
        self.assertEqual(geografia.ciudad_canonica("  quito  "), "Quito")
        self.assertEqual(
            geografia.ciudad_canonica("Santo Domingo de los Colorados"), "Santo Domingo"
        )

    def test_ciudad_desconocida_devuelve_none(self):
        self.assertIsNone(geografia.ciudad_canonica("Tulcán"))
        self.assertIsNone(geografia.provincia_de(None))
        self.assertIsNone(geografia.region_de(""))

    def test_ciudades_de_provincia_y_region(self):
        self.assertCountEqual(
            geografia.ciudades_de_provincia("Manabí"), ["Manta", "Portoviejo"]
        )
        costa = geografia.ciudades_de_region("Costa")
        self.assertIn("Guayaquil", costa)
        self.assertNotIn("Quito", costa)

    def test_provincias_es_el_conjunto_valido_ordenado(self):
        self.assertEqual(list(geografia.PROVINCIAS), sorted(geografia.PROVINCIAS))
        self.assertIn("Pichincha", geografia.PROVINCIAS)
        self.assertNotIn("Galápagos", geografia.PROVINCIAS)  # sin ciudad en el catálogo


def _sesion_execute(*resultados):
    """Sesión mockeada: cada `execute().all()` devuelve el siguiente resultado."""
    sesion = Mock()
    sesion.execute.side_effect = [Mock(all=Mock(return_value=r)) for r in resultados]
    return sesion


class DistribucionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_agrupa_por_region_y_provincia_y_cuenta_sin_ubicacion(self):
        # (ciudad, count) por tabla: internas y luego referenciadas.
        internas = [("Quito", 10), ("Guayaquil", 6), ("Manta", 2), ("Tulcán", 3)]
        referenciadas = [("Portoviejo", 1), (None, 4)]
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion_execute(
            internas, referenciadas
        )

        r = self.cliente.get("/marketplace/distribucion")
        self.assertEqual(r.status_code, 200)
        d = r.json()

        # 10+6+2+3 + 1+4 = 26; con ubicación reconocida = 10+6+2+1 = 19.
        self.assertEqual(d["total"], 26)
        self.assertEqual(d["con_ubicacion"], 19)

        regiones = {x["region"]: x for x in d["regiones"]}
        self.assertEqual(regiones["Sierra"]["total"], 10)  # solo Quito
        self.assertEqual(regiones["Costa"]["total"], 9)     # Guayaquil 6 + Manabí 3

        manabi = next(
            p for p in regiones["Costa"]["provincias"] if p["provincia"] == "Manabí"
        )
        self.assertEqual(manabi["total"], 3)  # Manta 2 + Portoviejo 1

        # Regiones ordenadas por total desc: Sierra(10) antes que Costa(9).
        self.assertEqual([x["region"] for x in d["regiones"]], ["Sierra", "Costa"])

    def test_sin_publicaciones_devuelve_ceros_y_lista_vacia(self):
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion_execute([], [])
        r = self.cliente.get("/marketplace/distribucion")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"total": 0, "con_ubicacion": 0, "regiones": []})


class FiltroGeograficoBuscarTests(unittest.TestCase):
    """La validación del filtro geográfico ocurre ANTES de tocar la BD, así que
    una sesión mockeada sin resultados basta para probar el 422."""

    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[obtener_sesion] = lambda: Mock()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_provincia_desconocida_da_422_con_opciones(self):
        r = self.cliente.get("/marketplace/buscar", params={"provincia": "Marte"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("Pichincha", r.json()["detail"])

    def test_region_desconocida_da_422_con_opciones(self):
        r = self.cliente.get("/marketplace/buscar", params={"region": "Oceanía"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("Costa", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
