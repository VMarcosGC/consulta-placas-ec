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
