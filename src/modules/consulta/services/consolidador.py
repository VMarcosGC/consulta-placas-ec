"""Agrega las respuestas por-fuente en un `VehiculoConsolidadoResponse`.

Convierte los dicts crudos que devuelven las funciones `consultar_*` (ANT, SRI,
AMT, FGE) en el perfil consolidado orientado a la entidad (ver schemas.py). Es la
contraparte server-side del puente que vivía en el frontend (`src/lib/consolidar.ts`).

No scrapea ni toca la BD: solo transforma dicts ya obtenidos por el router.
"""
from __future__ import annotations

from src.modules.consulta.schemas import (
    CategoriaMulta,
    DatosBasicos,
    EstadoFuente,
    EstadoFuenteItem,
    Identificacion,
    MultaDetalle,
    MultaItem,
    NovedadLegal,
    ValoresTributarios,
    VehiculoConsolidadoResponse,
)
from src.modules.consulta.services.catalogo_fuentes import CATALOGO_FUENTES


def _item_estado(clave: str, crudo: dict | None) -> EstadoFuenteItem:
    """Construye el item del tablero de fuentes para una fuente del catálogo.

    Si `crudo` es None la fuente no se consultó (aún no implementada) → `no_integrada`.
    Si trae un dict, se mapea su `estado` crudo al enum consolidado.
    """
    fuente = CATALOGO_FUENTES[clave]
    if crudo is None:
        return EstadoFuenteItem(
            clave=clave,
            nombre=fuente.nombre,
            prioridad=fuente.prioridad,
            origen=fuente.origen,
            estado=EstadoFuente.NO_INTEGRADA,
            detalle=None,
        )
    # Detalle útil: URL del portal (consulta_externa) o mensaje de error.
    detalle = crudo.get("url_consulta") or crudo.get("error")
    return EstadoFuenteItem(
        clave=clave,
        nombre=fuente.nombre,
        prioridad=fuente.prioridad,
        origen=fuente.origen,
        estado=EstadoFuente.desde_estado_servicio(crudo.get("estado")),
        detalle=detalle,
    )


def _parsear_anio(*candidatos) -> int | None:
    """Primer candidato convertible a año (int) entre los valores dados."""
    for valor in candidatos:
        if valor is None:
            continue
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            continue
    return None


def consolidar_placa(
    placa: str,
    resultados: dict[str, dict],
) -> VehiculoConsolidadoResponse:
    """Agrega las respuestas por-fuente en el perfil consolidado.

    `resultados` viene keyed por la clave del catálogo (ej. {"ANT": {...}, "AMT": {...}}):
    solo contiene las fuentes efectivamente consultadas. `estado_fuentes` se arma desde
    `CATALOGO_FUENTES`, así que las fuentes del catálogo aún no implementadas aparecen
    como `no_integrada` sin tener que tocar este archivo al sumarlas.
    """
    ant = resultados.get("ANT") or {}
    sri = resultados.get("SRI") or {}
    fge = resultados.get("FGE") or {}

    ant_veh = (ant.get("datos") or {}).get("vehiculo") or {}
    sri_datos = sri.get("datos") or {}
    sri_veh = sri_datos.get("vehiculo") or {}

    datos_basicos = DatosBasicos(
        marca=ant_veh.get("marca") or sri_veh.get("marca"),
        modelo=ant_veh.get("modelo") or sri_veh.get("modelo"),
        anio=_parsear_anio(ant_veh.get("anio_vehiculo"), sri_veh.get("anio_modelo")),
        color=ant_veh.get("color"),
        clase=ant_veh.get("clase"),
        servicio=ant_veh.get("servicio"),
        fecha_matricula=ant_veh.get("fecha_matricula"),
        fecha_caducidad=ant_veh.get("fecha_caducidad"),
        pais_origen=sri_veh.get("pais"),
    )

    # Identificación: chasis/motor vienen de fuentes no oficiales aún sin integrar;
    # por ahora solo el país de origen (cuando lo aporte el SRI).
    identificacion = Identificacion(pais_origen=sri_veh.get("pais"))

    # Valores tributarios (SRI): enlace al portal (consulta_externa) o montos.
    valores_tributarios: ValoresTributarios | None = None
    if sri.get("estado") == "consulta_externa":
        valores_tributarios = ValoresTributarios(url_consulta=sri.get("url_consulta"))
    elif sri_datos:
        valores = sri_datos.get("valores") or {}
        valores_tributarios = ValoresTributarios(
            matricula_usd=valores.get("matricula"),
            total_a_pagar_usd=valores.get("total_a_pagar"),
        )

    # Multas: solo lo PENDIENTE. ANT da el conteo; AMT da conteo + monto.
    multas_pendientes: list[MultaItem] = []
    citaciones_ant = (ant.get("datos") or {}).get("citaciones") or {}
    pendientes_ant = citaciones_ant.get("pendientes", 0)
    if pendientes_ant > 0:
        multas_pendientes.append(
            MultaItem(
                fuente="ANT",
                concepto=f"{pendientes_ant} citación(es) de tránsito",
                estado="pendiente",
            )
        )
    # Infracciones municipales: AMT (Quito) y EPMTSD (Santo Domingo) comparten el
    # mismo shape (portal AxisCloud). Un ítem por fuente con infracciones pendientes.
    for clave in ("AMT", "EPMTSD"):
        infracciones = (resultados.get(clave, {}).get("datos") or {}).get("infracciones") or {}
        pendientes = infracciones.get("pendientes", 0)
        total = infracciones.get("total_a_pagar", 0) or 0
        if pendientes > 0 or total > 0:
            multas_pendientes.append(
                MultaItem(
                    fuente=clave,
                    concepto=f"{pendientes} infracción(es) municipal(es)",
                    valor_usd=total if total > 0 else None,
                    estado="pendiente",
                )
            )

    # Detalle por fuente (desglose completo) para la vista. No repite datos del
    # vehículo: solo el conteo de citaciones/infracciones por estado.
    _ETIQUETAS = {
        "pendientes": "Pendientes",
        "pagadas": "Pagadas",
        "anuladas": "Anuladas",
        "en_convenio": "En convenio",
        "en_coactiva": "En coactiva",
        "en_impugnacion": "En impugnación",
    }
    multas_detalle: list[MultaDetalle] = []

    # ANT: citaciones de tránsito (conteos por estado; ANT no informa montos).
    if citaciones_ant:
        cats_ant = [
            CategoriaMulta(etiqueta=_ETIQUETAS.get(k, k), cantidad=citaciones_ant.get(k, 0) or 0)
            for k in ("pendientes", "en_impugnacion", "anuladas", "pagadas", "en_convenio")
        ]
        multas_detalle.append(
            MultaDetalle(
                fuente="ANT",
                ambito="Nacional (ANT)",
                total_registros=citaciones_ant.get("total_registros", 0) or 0,
                pendientes=pendientes_ant,
                total_a_pagar_usd=None,
                categorias=[c for c in cats_ant if c.cantidad > 0],
            )
        )

    # AMT (Quito) y EPMTSD (Santo Domingo): infracciones con conteo + monto por categoría.
    _AMBITO = {"AMT": "Quito (AMT)", "EPMTSD": "Santo Domingo (EPMTSD)"}
    for clave in ("AMT", "EPMTSD"):
        infr = (resultados.get(clave, {}).get("datos") or {}).get("infracciones") or {}
        if not infr:
            continue
        cats = [
            CategoriaMulta(
                etiqueta=_ETIQUETAS.get(k, k.replace("_", " ").capitalize()),
                cantidad=v.get("cantidad", 0) or 0,
                monto_usd=v.get("monto"),
            )
            for k, v in (infr.get("categorias") or {}).items()
            if (v.get("cantidad", 0) or 0) > 0
        ]
        multas_detalle.append(
            MultaDetalle(
                fuente=clave,
                ambito=_AMBITO[clave],
                total_registros=infr.get("total_registros", 0) or 0,
                pendientes=infr.get("pendientes", 0) or 0,
                total_a_pagar_usd=infr.get("total_a_pagar") or None,
                categorias=cats,
            )
        )

    # Novedades legales: noticias del delito de FGE.
    detalle_fge = ((fge.get("datos") or {}).get("denuncias") or {}).get("detalle") or []
    novedades_legales = [
        NovedadLegal(
            fuente="FGE",
            ndd=d.get("ndd"),
            delito=d.get("delito"),
            fecha=d.get("fecha"),
            lugar=d.get("lugar"),
            unidad=d.get("unidad"),
        )
        for d in detalle_fge
    ]

    # Tablero de fuentes desde el catálogo (orden de declaración = prioridad alta→baja).
    # Las consultadas muestran su estado vivo; las del catálogo aún sin servicio salen
    # como `no_integrada`. Sumar una fuente nueva solo requiere implementarla y rutearla.
    estado_fuentes = [
        _item_estado(clave, resultados.get(clave)) for clave in CATALOGO_FUENTES
    ]

    return VehiculoConsolidadoResponse(
        placa=placa,
        datos_basicos=datos_basicos,
        identificacion=identificacion,
        valores_tributarios=valores_tributarios,
        multas_pendientes=multas_pendientes,
        multas_detalle=multas_detalle,
        novedades_legales=novedades_legales,
        estado_fuentes=estado_fuentes,
    )
