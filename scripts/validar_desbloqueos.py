"""Validación rápida de la lógica de microdesbloqueos (sin BD).

Comprueba el seed del catálogo (precios y 1 token = USD 0.04) y el gateo del consolidador
(ficha pública gratis, multas/identificadores gateados, bundle). No toca la base de datos:
usa datos simulados.

Uso:  python -m scripts.validar_desbloqueos
"""
from decimal import Decimal
from types import SimpleNamespace

from src.modules.consulta.services.catalogo_productos import BUNDLE_INCLUYE, SEED_PRODUCTOS
from src.modules.consulta.services.consolidador import consolidar_placa

# Precios en tokens del catálogo vigente (Fase 2.5: solo se cobra por costo/valor real).
PRECIOS_ESPERADOS = {
    "consulta_publica_base": 0,
    "identificadores_tecnicos": 3,
    "titular_validado": 5,
    "alertas_legales": 8,
    "multas_con_montos": 10,
    "valores_matricula_sri": 12,
    "reporte_compra_segura": 40,
    "verificacion_marketplace": 100,
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
    # 1) Catálogo: códigos, precios en tokens y 1 token = USD 0.04.
    codigos = {p["codigo"] for p in SEED_PRODUCTOS}
    assert codigos == set(PRECIOS_ESPERADOS), f"Catálogo incompleto: {codigos}"
    for p in SEED_PRODUCTOS:
        assert p["tokens"] == PRECIOS_ESPERADOS[p["codigo"]], f"Precio mal en {p['codigo']}"
        esperado = (Decimal(p["tokens"]) * Decimal("0.04")).quantize(Decimal("0.01"))
        assert Decimal(p["precio_referencial_usd"]) == esperado, (
            f"USD ref mal en {p['codigo']}: {p['precio_referencial_usd']} != {esperado}"
        )
    assert BUNDLE_INCLUYE["reporte_compra_segura"], "El bundle debe incluir productos"

    # 2) Gateo: con datos de ANT (ficha + citación pendiente), la ficha pública es gratis,
    #    el detalle de multas se oculta hasta desbloquear `multas_con_montos`.
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
    assert teaser.datos_basicos.bloqueado is False, "La ficha pública debe ser gratis"
    assert teaser.datos_basicos.clase == "AUTOMOVIL", "Clase es dato público gratis"
    assert teaser.multas_bloqueado is True, "Teaser debe ocultar el detalle de multas"
    assert teaser.tiene_pendientes is True, "El veredicto gratis debe ser True"
    disp = {p.codigo for p in teaser.productos if p.disponible}
    assert "consulta_publica_base" in disp, f"Base pública debe estar disponible: {disp}"
    assert "multas_con_montos" in disp, f"Multas debe estar disponible: {disp}"
    # Sin proveedor confiable: no se ofrecen como cobrables.
    assert "titular_validado" not in disp, "Titular no debe ser disponible (sin proveedor)"
    assert "valores_matricula_sri" not in disp, "Valores SRI no disponibles (enlace oficial)"
    assert "alertas_legales" not in disp, "Alertas legales no disponibles (enlace oficial)"

    unlock = consolidar_placa("ABC1234", fuentes, {"multas_con_montos"}, cat)
    assert unlock.multas_bloqueado is False, "Desbloqueado: multas visibles"

    # 3) Proveedor (capa providers/): con capacidades, identificadores y titular quedan
    #    disponibles; el titular NUNCA expone el nombre crudo (solo validación + ofuscado).
    import asyncio
    from src.modules.consulta.providers import obtener_proveedor

    prov = obtener_proveedor()
    res = asyncio.run(prov.consultar("ABC1234"))
    assert res.estado == "consulta_realizada" and res.vin and res.titular, "Mock debe entregar datos"
    capac = prov.capacidades

    teaser_prov = consolidar_placa("ABC1234", fuentes, set(), cat, proveedor_capacidades=capac)
    disp_prov = {p.codigo for p in teaser_prov.productos if p.disponible}
    assert {"identificadores_tecnicos", "titular_validado"} <= disp_prov, f"Disponibles: {disp_prov}"
    assert teaser_prov.titular.bloqueado is True, "Titular en teaser va bloqueado"
    assert teaser_prov.titular.nombre_ofuscado is None, "Teaser no revela el titular"

    unlock_prov = consolidar_placa(
        "ABC1234", fuentes, {"identificadores_tecnicos", "titular_validado"}, cat,
        proveedor_datos=res.to_dict(), proveedor_capacidades=capac,
    )
    assert unlock_prov.identificacion.vin == res.vin, "Desbloqueado: VIN visible"
    assert unlock_prov.titular.validado is True, "Titular validado tras desbloqueo"
    assert unlock_prov.titular.nombre_ofuscado and "***" in unlock_prov.titular.nombre_ofuscado, (
        "El titular SIEMPRE va ofuscado, nunca crudo"
    )
    assert res.titular not in (unlock_prov.titular.nombre_ofuscado or ""), "Nunca el nombre crudo"

    print("OK · catálogo (8 productos, 1 token=USD0.04), gateo y capa de proveedores (mock) válidos.")


if __name__ == "__main__":
    main()
