"""reajuste comercial del catalogo de microdesbloqueos (solo se cobra por costo/valor real)

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-31

Fase 2.5: el catalogo solo debe cobrar por datos que generen costo de proveedor externo,
dificultad real o valor comercial relevante. Los datos publicos simples (marca, modelo, anio,
color, clase, servicio, estado de matricula) pasan a ser GRATIS via `consulta_publica_base`.

Cambios (migracion manual, 10.2):
- Valor referencial del token: USD 0.05 -> USD 0.04 (se refleja en precio_referencial_usd).
- DESACTIVA los productos que cobraban datos publicos poco relevantes:
  `vehiculo_basico`, `vehiculo_tecnico` (activo=false; se conservan por auditoria).
- RENOMBRA (UPDATE codigo) los productos que siguen vigentes con nuevo nombre/precio:
  `vehiculo_identificadores` -> `identificadores_tecnicos` (3t),
  `vehiculo_titular_validado` -> `titular_validado` (5t),
  `vehiculo_multas`          -> `multas_con_montos` (10t).
- AJUSTA precios de los que cambian de tarifa:
  `reporte_compra_segura` 30t -> 40t,  `verificacion_marketplace` 80t -> 100t.
- SIEMBRA los nuevos (ON CONFLICT DO NOTHING): `consulta_publica_base` (0t),
  `valores_matricula_sri` (12t), `alertas_legales` (8t).
- MIGRA los desbloqueos ya registrados (datos de prueba) al nuevo codigo equivalente.

Idempotente y reversible. Ver docs/producto/catalogo_productos_consulta.md.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Renombres 1:1 (codigo viejo -> nuevo, nombre, descripcion, tokens, precio, sensibilidad, orden).
_RENOMBRES = [
    ("vehiculo_identificadores", "identificadores_tecnicos", "Ver identificadores tecnicos",
     "VIN, motor y chasis ofuscados a origen (primeros caracteres + pais del WMI) mas datos tecnicos disponibles.",
     3, "0.12", "media", 20),
    ("vehiculo_titular_validado", "titular_validado", "Validar titular registrado",
     "Validacion del titular (coincide/ofuscado), nunca el dato crudo. Requiere proveedor autorizado.",
     5, "0.20", "alta", 30),
    ("vehiculo_multas", "multas_con_montos", "Ver multas con valores",
     "Detalle con montos por fuente (ANT/AMT): pendientes, total a pagar y categorias.",
     10, "0.40", "media", 50),
]

# Productos nuevos (ON CONFLICT DO NOTHING).
_NUEVOS = [
    ("consulta_publica_base", "Consulta publica base",
     "Gratis: caracteristicas publicas (marca, modelo, anio, color, clase, servicio), estado de matricula, enlaces oficiales y estado de fuentes.",
     0, "0.00", "baja", 10),
    ("alertas_legales", "Ver alertas legales",
     "Novedades legales asociadas (FGE). Requiere fuente estructurada y legalmente segura; si no, se ofrece el enlace oficial.",
     8, "0.32", "alta", 40),
    ("valores_matricula_sri", "Ver valores de matricula (SRI)",
     "Valores tributarios del SRI. Sin proveedor automatico confiable: se ofrece el enlace oficial asistido.",
     12, "0.48", "media", 60),
    ("reporte_compra_segura", "Generar reporte compra segura",
     "Informe consolidado: identificadores tecnicos + multas con valores + alertas legales + valores SRI + titular validado (segun disponibilidad).",
     40, "1.60", "alta", 70),
    ("verificacion_marketplace", "Verificacion de la plataforma",
     "Sello Verificado por la plataforma para una publicacion premium del marketplace.",
     100, "4.00", "alta", 80),
]

# Migracion de desbloqueos existentes (datos de prueba) al nuevo codigo.
_MAP_DESBLOQUEOS = {
    "vehiculo_identificadores": "identificadores_tecnicos",
    "vehiculo_titular_validado": "titular_validado",
    "vehiculo_multas": "multas_con_montos",
}


def upgrade() -> None:
    # 1) Desactiva los productos que cobraban datos publicos poco relevantes (se conservan).
    op.execute(
        "UPDATE productos_consulta SET activo = false, actualizado_en = now() "
        "WHERE codigo IN ('vehiculo_basico', 'vehiculo_tecnico')"
    )

    # 2) Renombra/ajusta los vigentes (cambia codigo, nombre, precio, etc.).
    for viejo, nuevo, nombre, desc, tokens, precio, sens, orden in _RENOMBRES:
        op.execute(
            "UPDATE productos_consulta SET "
            f"codigo = '{nuevo}', nombre = '{nombre}', descripcion = '{desc}', "
            f"tokens = {tokens}, precio_referencial_usd = {precio}, sensibilidad = '{sens}', "
            f"orden = {orden}, actualizado_en = now() "
            f"WHERE codigo = '{viejo}'"
        )

    # 3) Reajusta precios/orden de los que solo cambian de tarifa (ya existen con su codigo).
    op.execute(
        "UPDATE productos_consulta SET tokens = 40, precio_referencial_usd = 1.60, "
        "orden = 70, actualizado_en = now() WHERE codigo = 'reporte_compra_segura'"
    )
    op.execute(
        "UPDATE productos_consulta SET tokens = 100, precio_referencial_usd = 4.00, "
        "orden = 80, actualizado_en = now() WHERE codigo = 'verificacion_marketplace'"
    )

    # 4) Siembra los nuevos productos (idempotente).
    valores = ", ".join(
        "('{codigo}', '{nombre}', '{desc}', {tokens}, {precio}, '{sens}', {orden})".format(
            codigo=c, nombre=n, desc=d, tokens=t, precio=p, sens=s, orden=o
        )
        for (c, n, d, t, p, s, o) in _NUEVOS
    )
    op.execute(
        "INSERT INTO productos_consulta "
        "(codigo, nombre, descripcion, tokens, precio_referencial_usd, sensibilidad, orden) "
        f"VALUES {valores} ON CONFLICT (codigo) DO NOTHING"
    )

    # 5) Migra los desbloqueos ya registrados al nuevo codigo equivalente.
    #    Los de productos ahora gratis/plegados (vehiculo_basico/tecnico) se eliminan: el dato
    #    es gratis o se fundio en identificadores_tecnicos (no se recobra de todos modos).
    op.execute(
        "DELETE FROM desbloqueos_consulta WHERE producto_codigo IN ('vehiculo_basico', 'vehiculo_tecnico')"
    )
    for viejo, nuevo in _MAP_DESBLOQUEOS.items():
        op.execute(
            f"UPDATE desbloqueos_consulta SET producto_codigo = '{nuevo}' WHERE producto_codigo = '{viejo}'"
        )


def downgrade() -> None:
    # Revierte los renombres y precios; reactiva los desactivados; borra los nuevos.
    op.execute(
        "DELETE FROM productos_consulta "
        "WHERE codigo IN ('consulta_publica_base', 'alertas_legales', 'valores_matricula_sri')"
    )
    op.execute(
        "UPDATE productos_consulta SET tokens = 30, precio_referencial_usd = 1.50, "
        "orden = 60, actualizado_en = now() WHERE codigo = 'reporte_compra_segura'"
    )
    op.execute(
        "UPDATE productos_consulta SET tokens = 80, precio_referencial_usd = 4.00, "
        "orden = 70, actualizado_en = now() WHERE codigo = 'verificacion_marketplace'"
    )
    # Renombres inversos (restaura codigo, nombre y precio originales 1 token = USD 0.05).
    op.execute(
        "UPDATE productos_consulta SET codigo = 'vehiculo_identificadores', "
        "nombre = 'VIN, motor y chasis', "
        "descripcion = 'Identificadores ofuscados a origen (primeros caracteres + pais del WMI).', "
        "tokens = 3, precio_referencial_usd = 0.15, sensibilidad = 'media', orden = 30, "
        "actualizado_en = now() WHERE codigo = 'identificadores_tecnicos'"
    )
    op.execute(
        "UPDATE productos_consulta SET codigo = 'vehiculo_titular_validado', "
        "nombre = 'Titular validado', "
        "descripcion = 'Validacion del titular (coincide/ofuscado), nunca el dato crudo. Requiere proveedor autorizado.', "
        "tokens = 5, precio_referencial_usd = 0.25, sensibilidad = 'alta', orden = 40, "
        "actualizado_en = now() WHERE codigo = 'titular_validado'"
    )
    op.execute(
        "UPDATE productos_consulta SET codigo = 'vehiculo_multas', "
        "nombre = 'Multas e infracciones', "
        "descripcion = 'Detalle con montos por fuente (ANT/AMT): pendientes, total a pagar y categorias.', "
        "tokens = 8, precio_referencial_usd = 0.40, sensibilidad = 'media', orden = 50, "
        "actualizado_en = now() WHERE codigo = 'multas_con_montos'"
    )
    # Revierte los desbloqueos migrados a su codigo original.
    for viejo, nuevo in _MAP_DESBLOQUEOS.items():
        op.execute(
            f"UPDATE desbloqueos_consulta SET producto_codigo = '{viejo}' WHERE producto_codigo = '{nuevo}'"
        )
    # Reactiva los que se habian desactivado.
    op.execute(
        "UPDATE productos_consulta SET activo = true, actualizado_en = now() "
        "WHERE codigo IN ('vehiculo_basico', 'vehiculo_tecnico')"
    )
