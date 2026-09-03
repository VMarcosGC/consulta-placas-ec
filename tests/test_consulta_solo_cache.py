"""Pruebas unitarias del modo cache-only del perfil público.

No requieren PostgreSQL ni servicios externos: verifican la selección de la
orquestación y el shape que se entrega al consolidador en un cache miss.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from src.modules.consulta.routers import consulta
from src.modules.consulta.schemas import EstadoFuente
from src.modules.consulta.services.catalogo_fuentes import CATALOGO_FUENTES
from src.modules.consulta.services.consolidador import consolidar_placa


class ConsultaSoloCacheTests(unittest.TestCase):
    def test_cache_miss_no_consulta_ni_encola_fuentes(self):
        sesion = Mock()
        with patch.object(consulta, "obtener_consulta_reciente", return_value=None) as obtener:
            resultados = asyncio.run(
                consulta._obtener_fuentes_placa_solo_cache(sesion, "ABC1234")
            )

        self.assertEqual(obtener.call_count, len(CATALOGO_FUENTES))
        self.assertEqual(set(resultados), set(CATALOGO_FUENTES))
        self.assertTrue(
            all(resultado["estado"] == "no_consultada" for resultado in resultados.values())
        )
        perfil = consolidar_placa("ABC1234", resultados)
        self.assertTrue(
            all(item.estado is EstadoFuente.NO_CONSULTADA for item in perfil.estado_fuentes)
        )

    def test_cache_hit_se_conserva_en_perfil(self):
        sesion = Mock()
        respuesta = {
            "fuente": "ANT",
            "placa": "ABC1234",
            "estado": "consulta_realizada",
            "datos": {"vehiculo": {"marca": "Mazda"}},
            "consultado_en": "2026-07-25T12:00:00+00:00",
        }
        def obtener_cache(_, __, fuente):
            return respuesta if fuente == "ANT" else None

        with patch.object(consulta, "obtener_consulta_reciente", side_effect=obtener_cache):
            resultados = asyncio.run(
                consulta._obtener_fuentes_placa_solo_cache(sesion, "ABC1234")
            )

        self.assertEqual(resultados["ANT"]["estado"], "consulta_realizada")
        self.assertTrue(resultados["ANT"]["_cache"])
        self.assertEqual(resultados["ANT"]["consultado_en"], respuesta["consultado_en"])
        perfil = consolidar_placa("ABC1234", resultados)
        estados = {item.clave: item.estado for item in perfil.estado_fuentes}
        self.assertIs(estados["ANT"], EstadoFuente.COMPLETADA)
        self.assertIs(estados["AMT"], EstadoFuente.NO_CONSULTADA)
        self.assertEqual(perfil.datos_basicos.marca, "Mazda")

    def test_endpoint_solo_cache_no_usa_orquestacion_normal(self):
        sesion = Mock()
        cache_only = AsyncMock(return_value={})
        normal = AsyncMock(return_value={})
        with (
            patch.object(consulta, "_obtener_fuentes_placa_solo_cache", cache_only),
            patch.object(consulta, "_obtener_fuentes_placa", normal),
            patch.object(consulta, "catalogo_activo", return_value=[]),
            patch.object(consulta, "leer_proveedor_cacheado", return_value=None),
            patch.object(consulta, "capacidades_proveedor", return_value=set()),
            patch.object(consulta, "consolidar_placa", return_value={"placa": "ABC1234"}),
        ):
            resultado = asyncio.run(
                consulta.consultar_perfil("ABC1234", True, sesion, None)
            )

        self.assertEqual(resultado, {"placa": "ABC1234"})
        cache_only.assert_awaited_once_with(sesion, "ABC1234")
        normal.assert_not_awaited()

    def test_endpoint_normal_conserva_orquestacion_existente(self):
        sesion = Mock()
        cache_only = AsyncMock(return_value={})
        normal = AsyncMock(return_value={})
        with (
            patch.object(consulta, "_obtener_fuentes_placa_solo_cache", cache_only),
            patch.object(consulta, "_obtener_fuentes_placa", normal),
            patch.object(consulta, "catalogo_activo", return_value=[]),
            patch.object(consulta, "leer_proveedor_cacheado", return_value=None),
            patch.object(consulta, "capacidades_proveedor", return_value=set()),
            patch.object(consulta, "consolidar_placa", return_value={"placa": "ABC1234"}),
        ):
            asyncio.run(consulta.consultar_perfil("ABC1234", False, sesion, None))

        normal.assert_awaited_once_with(sesion, "ABC1234")
        cache_only.assert_not_awaited()


class PerfilConSesionTests(unittest.TestCase):
    """Con sesión, la consulta REAL llama al proveedor (API, no scraping) para poder
    revelar identificadores / n.º de dueños; `solo_cache` nunca lo hace. Anónimo solo
    salta al proveedor si ANT no respondió y hay un proveedor real configurado."""

    def _run(self, *, solo_cache: bool, usuario, fuentes=None, proveedor="mock", capacidades=None):
        sesion = Mock()
        asegurar = AsyncMock(return_value={"numero_propietarios": 3})
        leer = Mock(return_value=None)
        with (
            patch.object(consulta, "_obtener_fuentes_placa_solo_cache", AsyncMock(return_value=fuentes or {})),
            patch.object(consulta, "_obtener_fuentes_placa", AsyncMock(return_value=fuentes or {})),
            patch.object(consulta, "catalogo_activo", return_value=[]),
            patch.object(consulta, "asegurar_datos_proveedor", asegurar),
            patch.object(consulta, "leer_proveedor_cacheado", leer),
            patch.object(consulta, "nombre_proveedor_activo", return_value=proveedor),
            patch.object(consulta, "capacidades_proveedor", return_value=capacidades or set()),
            patch.object(consulta, "consolidar_placa", return_value={"placa": "ABC1234"}),
        ):
            asyncio.run(consulta.consultar_perfil("ABC1234", solo_cache, sesion, usuario))
        return asegurar, leer

    def test_con_sesion_llama_al_proveedor(self):
        asegurar, leer = self._run(solo_cache=False, usuario=Mock(id=7))
        asegurar.assert_awaited_once()
        self.assertEqual(asegurar.await_args.args[1], "ABC1234")
        leer.assert_not_called()

    def test_solo_cache_con_sesion_no_llama_al_proveedor(self):
        asegurar, leer = self._run(solo_cache=True, usuario=Mock(id=7))
        asegurar.assert_not_awaited()
        leer.assert_called_once()

    def test_anonimo_con_ant_ok_no_llama_al_proveedor(self):
        asegurar, leer = self._run(
            solo_cache=False, usuario=None,
            fuentes={"ANT": {"estado": "consulta_realizada"}},
            proveedor="consultas_ec", capacidades={"identificadores_tecnicos"},
        )
        asegurar.assert_not_awaited()
        leer.assert_called_once()

    def test_anonimo_con_ant_lento_y_proveedor_real_salta_al_proveedor(self):
        asegurar, leer = self._run(
            solo_cache=False, usuario=None,
            fuentes={"ANT": {"estado": "en_proceso"}},
            proveedor="consultas_ec", capacidades={"identificadores_tecnicos"},
        )
        asegurar.assert_awaited_once()
        leer.assert_called_once()  # primero se leyó la caché (None), luego el salto

    def test_anonimo_con_ant_lento_pero_proveedor_mock_no_salta(self):
        asegurar, leer = self._run(
            solo_cache=False, usuario=None,
            fuentes={"ANT": {"estado": "en_proceso"}},
            proveedor="mock", capacidades={"identificadores_tecnicos"},
        )
        asegurar.assert_not_awaited()


class AntTimeoutTests(unittest.TestCase):
    """`_ant_con_timeout`: si ANT excede el techo, encola para el worker y responde
    `en_proceso` sin colgar la request."""

    def test_timeout_encola_y_devuelve_en_proceso(self):
        sesion = Mock()

        async def _lento(*_a, **_k):
            await asyncio.sleep(10)

        with (
            patch.object(consulta, "consultar_con_cache", _lento),
            patch.object(consulta, "CONSULTA_TIMEOUT_ANT_SEGUNDOS", 0.01),
            patch.object(consulta, "encolar_scraping") as encolar,
        ):
            res = asyncio.run(consulta._ant_con_timeout(sesion, "ABC1234"))

        self.assertEqual(res["estado"], "en_proceso")
        self.assertIsNone(res["datos"])
        encolar.assert_called_once_with(sesion, "ABC1234", "ANT")

    def test_sin_timeout_devuelve_el_resultado_de_ant(self):
        sesion = Mock()
        ok = {"fuente": "ANT", "estado": "consulta_realizada", "datos": {"vehiculo": {}}}

        async def _rapido(*_a, **_k):
            return ok

        with (
            patch.object(consulta, "consultar_con_cache", _rapido),
            patch.object(consulta, "encolar_scraping") as encolar,
        ):
            res = asyncio.run(consulta._ant_con_timeout(sesion, "ABC1234"))

        self.assertEqual(res, ok)
        encolar.assert_not_called()


class HistorialPropietariosTests(unittest.TestCase):
    def test_anonimo_ve_bloqueado_sin_numero(self):
        perfil = consolidar_placa(
            "ABC1234", {}, set(), (),
            proveedor_datos={"numero_propietarios": 3},
            proveedor_capacidades={"identificadores_tecnicos"},
        )
        h = perfil.historial_propietarios
        self.assertTrue(h.bloqueado)
        self.assertIsNone(h.numero_propietarios)
        self.assertTrue(h.disponible)

    def test_desbloqueado_ve_el_numero(self):
        perfil = consolidar_placa(
            "ABC1234", {}, {"identificadores_tecnicos"}, (),
            proveedor_datos={"numero_propietarios": 3},
            proveedor_capacidades={"identificadores_tecnicos"},
        )
        h = perfil.historial_propietarios
        self.assertFalse(h.bloqueado)
        self.assertEqual(h.numero_propietarios, 3)

    def test_sin_proveedor_no_disponible(self):
        perfil = consolidar_placa("ABC1234", {}, {"identificadores_tecnicos"}, ())
        self.assertFalse(perfil.historial_propietarios.disponible)
        self.assertIsNone(perfil.historial_propietarios.numero_propietarios)
