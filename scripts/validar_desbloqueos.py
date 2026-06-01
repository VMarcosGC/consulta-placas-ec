"""Validación rápida de la lógica de microdesbloqueos (sin BD).

Comprueba el seed del catálogo (precios y 1 token = USD 0.05) y el gateo del consolidador
(teaser vs desbloqueado, bundle). No toca la base de datos: usa datos simulados.

Uso:  python -m scripts.validar_desbloqueos
"""
from decimal import Decimal
from types import SimpleNamespace

from src.modules.consulta.services.catalogo_productos import BUNDLE_INCLUYE, SEED_PRODUCTOS
from src.modules.consulta.services.consolidador import consolidar_placa

PRECIOS_ESPERADOS = {
    "vehiculo_basico": 3,
    "vehiculo_tecnico": 2,
    "vehiculo_identificadores": 3,
    "vehiculo_titular_validado": 5,
    "vehiculo_multas": 8,
    "reporte_compra_segura": 30,
    "verificacion_marketplace": 80,
}


def _catalogo_simulado():
    return [
        SimpleNamespace(
            codigo=p["codigo"],
            nombre=p["nombre"],
            tokens=p["tokens"],
            precio_referencial_usd=Decimal(p["precio_referencial_usd"]),
            sensibilidad=p["sensibilidad"],
            descripcion=p["descripcion"],
        )
        for p in SEED_PRODUCTOS
    ]


def main() -> None:
    # 1) Catálogo: códigos, precios en tokens y 1 token = USD 0.05.
    codigos = {p["codigo"] for p in SEED_PRODUCTOS}
    assert codigos == set(PRECIOS_ESPERADOS), f"Catálogo incompleto: {codigos}"
    for p in SEED_PRODUCTOS:
        assert p["tokens"] == PRECIOS_ESPERADOS[p["codigo"]], f"Precio mal en {p['codigo']}"
        esperado = (Decimal(p["tokens"]) * Decimal("0.05")).quantize(Decimal("0.01"))
        assert Decimal(p["precio_referencial_usd"]) == esperado, (
            f"USD ref mal en {p['codigo']}: {p['precio_referencial_usd']} != {esperado}"
        )
    assert BUNDLE_INCLUYE["reporte_compra_segura"], "El bundle debe incluir productos"

    # 2) Gateo: con datos de ANT (ficha + citación pendiente), teaser oculta; unlock revela.
    cat = _catalogo_simulado()
    fuentes = {
        "ANT": {
            "estado": "consulta_realizada",
            "datos": {
                "vehiculo": {"marca": "KIA", "clase": "AUTOMOVIL", "fecha_caducidad": "24-06-2030"},
                "citaciones": {"pendientes": 1, "total_registros": 1},
            },
        }
    }
    teaser = consolidar_placa("ABC1234", fuentes, set(), cat)
    assert teaser.datos_basicos.bloqueado is True, "Teaser debería ocultar la ficha"
    assert teaser.datos_basicos.clase is None, "Teaser no debe revelar clase"
    assert teaser.multas_bloqueado is True, "Teaser debe ocultar el detalle de multas"
    assert teaser.tiene_pendientes is True, "El veredicto gratis debe ser True"
    disp = {p.codigo for p in teaser.productos if p.disponible}
    assert "vehiculo_basico" in disp and "vehiculo_multas" in disp, f"Disponibles: {disp}"

    unlock = consolidar_placa("ABC1234", fuentes, {"vehiculo_basico", "vehiculo_multas"}, cat)
    assert unlock.datos_basicos.bloqueado is False, "Desbloqueado: ficha visible"
    assert unlock.datos_basicos.clase == "AUTOMOVIL", "Desbloqueado: clase visible"
    assert unlock.multas_bloqueado is False, "Desbloqueado: multas visibles"

    print("OK · catálogo (7 productos, 1 token=USD0.05) y gateo (teaser/unlock) válidos.")


if __name__ == "__main__":
    main()
