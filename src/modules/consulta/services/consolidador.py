"""Agrega las respuestas por-fuente en un `VehiculoConsolidadoResponse`.

Convierte los dicts crudos que devuelven las funciones `consultar_*` (ANT, SRI,
AMT, FGE) en el perfil consolidado orientado a la entidad (ver schemas.py). Es la
contraparte server-side del puente que vivía en el frontend (`src/lib/consolidar.ts`).

No scrapea ni toca la BD: solo transforma dicts ya obtenidos por el router.
"""
from __future__ import annotations

from datetime import date, datetime

from src.modules.consulta.schemas import (
    CategoriaMulta,
    DatosBasicos,
    EstadoFuente,
    EstadoFuenteItem,
    Identificacion,
    MultaDetalle,
    MultaItem,
    NovedadLegal,
    ProductoEstado,
    Titular,
    ValoresTributarios,
    VehiculoConsolidadoResponse,
)
from src.modules.consulta.services.catalogo_fuentes import CATALOGO_FUENTES
from src.core.ofuscacion import decodificar_origen_vin, ofuscar_identificador, ofuscar_nombre


def _matricula_vigente(fecha_caducidad: str | None) -> bool | None:
    """Interpreta la fecha de caducidad (DD-MM-YYYY o ISO) → vigente/vencida.

    Devuelve None si no hay fecha o no se puede parsear (no afirmamos nada).
    """
    if not fecha_caducidad:
        return None
    texto = fecha_caducidad.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date() >= date.today()
        except ValueError:
            continue
    return None


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
    # `consultado_en` lo inyecta la capa de caché (o el propio `consultar_con_cache` cuando
    # el dato es recién scrapeado). Las fuentes en_proceso/error no lo traen → None.
    return EstadoFuenteItem(
        clave=clave,
        nombre=fuente.nombre,
        prioridad=fuente.prioridad,
        origen=fuente.origen,
        estado=EstadoFuente.desde_estado_servicio(crudo.get("estado")),
        detalle=detalle,
        consultado_en=crudo.get("consultado_en"),
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


def _construir_identificacion(
    vin: str | None,
    motor: str | None,
    chasis: str | None,
    pais: str | None,
    desbloqueado: bool,
) -> Identificacion:
    """Arma la sección de identificadores sensibles según el nivel de acceso.

    - `desbloqueado=False` (default, vista pública/anónima): solo los campos
      `*_ofuscado` (primeros 3 caracteres + máscara). Los campos en claro van None.
    - `desbloqueado=True` (usuario pagó tokens): los campos en claro traen el valor
      completo, además de la vista ofuscada (por compatibilidad con el frontend).

    El país de origen se decodifica del WMI del VIN si la fuente no lo aportó directo.
    """
    pais_origen = pais or decodificar_origen_vin(vin or "").get("pais")
    return Identificacion(
        bloqueado=not desbloqueado,
        vin=vin if desbloqueado else None,
        numero_motor=motor if desbloqueado else None,
        numero_chasis=chasis if desbloqueado else None,
        vin_ofuscado=ofuscar_identificador(vin),
        numero_motor_ofuscado=ofuscar_identificador(motor),
        numero_chasis_ofuscado=ofuscar_identificador(chasis),
        pais_origen=pais_origen,
    )


def _construir_titular(
    proveedor_datos: dict | None,
    desbloqueado: bool,
    disponible: bool,
) -> Titular:
    """Arma la sección del titular respetando la política de PII.

    Nunca expone el nombre crudo: como máximo, validación + nombre ofuscado (iniciales). El
    nombre crudo solo lo ve el dueño en su garage, no esta vista pública.
    """
    nombre_crudo = (proveedor_datos or {}).get("titular") if proveedor_datos else None
    if not disponible:
        return Titular(bloqueado=True, disponible=False, mensaje=None)
    if not desbloqueado:
        return Titular(
            bloqueado=True,
            disponible=True,
            mensaje="Valida que el titular registrado coincide, sin exponer datos personales.",
        )
    # Desbloqueado: validación + nombre ofuscado (jamás el nombre completo).
    if nombre_crudo:
        return Titular(
            bloqueado=False,
            disponible=True,
            validado=True,
            nombre_ofuscado=ofuscar_nombre(nombre_crudo),
            mensaje="Titular registrado validado.",
        )
    return Titular(
        bloqueado=False,
        disponible=True,
        validado=False,
        mensaje="No se pudo validar el titular con la fuente disponible.",
    )


def consolidar_placa(
    placa: str,
    resultados: dict[str, dict],
    productos_desbloqueados: frozenset[str] | set[str] = frozenset(),
    catalogo: "list | tuple" = (),
    proveedor_datos: dict | None = None,
    proveedor_capacidades: frozenset[str] | set[str] = frozenset(),
) -> VehiculoConsolidadoResponse:
    """Agrega las respuestas por-fuente en el perfil consolidado, GATEADO por productos.

    `resultados` viene keyed por la clave del catálogo (ej. {"ANT": {...}, "AMT": {...}}):
    solo contiene las fuentes efectivamente consultadas. `estado_fuentes` se arma desde
    `CATALOGO_FUENTES`, así que las fuentes del catálogo aún no implementadas aparecen
    como `no_integrada` sin tener que tocar este archivo al sumarlas.

    `productos_desbloqueados` = códigos del catálogo que el usuario ya pagó para esta placa.
    GRATIS siempre (consulta_publica_base): la ficha pública completa (marca/modelo/año/color/
    clase/servicio/fechas), el estado de matrícula, los enlaces oficiales y el veredicto sí/no.
    Las secciones con costo/valor real (identificadores, multas con montos) se devuelven
    gateadas (`bloqueado=True`) hasta desbloquear con tokens. Datos sin proveedor confiable
    (titular, valores SRI, alertas legales) salen como enlace oficial, no como cobro.
    Ver docs/producto/modelo_tokens_microdesbloqueos.md.
    """
    productos_desbloqueados = set(productos_desbloqueados)
    proveedor_capacidades = set(proveedor_capacidades)
    prov = proveedor_datos or {}
    ant = resultados.get("ANT") or {}
    sri = resultados.get("SRI") or {}
    fge = resultados.get("FGE") or {}

    ant_veh = (ant.get("datos") or {}).get("vehiculo") or {}
    sri_datos = sri.get("datos") or {}
    sri_veh = sri_datos.get("vehiculo") or {}

    datos_basicos = DatosBasicos(
        marca=ant_veh.get("marca") or sri_veh.get("marca") or prov.get("marca"),
        modelo=ant_veh.get("modelo") or sri_veh.get("modelo") or prov.get("modelo"),
        anio=_parsear_anio(ant_veh.get("anio_vehiculo"), sri_veh.get("anio_modelo"), prov.get("anio")),
        color=ant_veh.get("color") or prov.get("color"),
        clase=ant_veh.get("clase") or prov.get("clase"),
        servicio=ant_veh.get("servicio") or prov.get("servicio"),
        fecha_matricula=ant_veh.get("fecha_matricula"),
        fecha_caducidad=ant_veh.get("fecha_caducidad"),
        pais_origen=sri_veh.get("pais"),
        matricula_vigente=_matricula_vigente(ant_veh.get("fecha_caducidad")),
    )
    # Identificación: VIN/motor/chasis los entrega el PROVEEDOR (capa providers/), cacheado
    # tras un desbloqueo pagado. Best-effort fallback a lo que aporte el scraping público.
    # Se ofuscan salvo que `desbloqueado` sea True (el usuario pagó `identificadores_tecnicos`).
    vin_crudo = prov.get("vin") or ant_veh.get("vin") or sri_veh.get("vin") or None
    motor_crudo = prov.get("motor") or ant_veh.get("numero_motor") or ant_veh.get("motor") or None
    chasis_crudo = prov.get("chasis") or ant_veh.get("numero_chasis") or ant_veh.get("chasis") or None
    identificacion = _construir_identificacion(
        vin_crudo,
        motor_crudo,
        chasis_crudo,
        sri_veh.get("pais"),
        desbloqueado="identificadores_tecnicos" in productos_desbloqueados,
    )

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

    # ── Veredicto GRATIS (antes de gatear): ¿hay algo pendiente? sí/no, sin detalle ──
    valor_sri = valores_tributarios.total_a_pagar_usd if valores_tributarios else None
    tiene_pendientes = bool(multas_pendientes) or bool(novedades_legales) or bool(valor_sri)

    # ── Disponibilidad (qué productos SÍ se pueden cobrar para esta placa) ──
    # Regla comercial (Fase 2.5): solo se cobra por datos con costo de proveedor, dificultad
    # real o valor comercial. Los datos públicos simples (toda la ficha + estado de matrícula)
    # son GRATIS vía `consulta_publica_base` (0 tokens), así que no se gatea `datos_basicos`.
    # Un dato es "disponible" si ya está (scraping/proveedor cacheado) O si el proveedor
    # activo declara que PUEDE entregarlo (capacidad), sin tener que llamarlo en el preview.
    identificadores_disponible = bool(
        identificacion.vin_ofuscado
        or identificacion.numero_motor_ofuscado
        or identificacion.numero_chasis_ofuscado
    ) or ("identificadores_tecnicos" in proveedor_capacidades)
    titular_disponible = "titular_validado" in proveedor_capacidades
    multas_disponible = len(multas_detalle) > 0
    disponibles: set[str] = {"consulta_publica_base"}  # la base pública siempre se entrega
    if identificadores_disponible:
        disponibles.add("identificadores_tecnicos")
    if titular_disponible:
        disponibles.add("titular_validado")
    if multas_disponible:
        disponibles.add("multas_con_montos")
    # `valores_matricula_sri` y `alertas_legales` quedan disponibles=false: sin proveedor
    # confiable / sin fuente estructurada legalmente segura todavía → se ofrece el enlace
    # oficial asistido, no un cobro (ver politica_datos_sensibles.md).
    if identificadores_disponible or multas_disponible or titular_disponible:
        disponibles.add("reporte_compra_segura")  # el bundle se ofrece si hay algo que agrupar

    # ── Titular (PII): validación/ofuscación, nunca el nombre crudo ──
    titular = _construir_titular(
        proveedor_datos,
        desbloqueado="titular_validado" in productos_desbloqueados,
        disponible=titular_disponible,
    )

    # ── Gateo de secciones según lo desbloqueado ──
    # `datos_basicos` ya NO se gatea: la ficha pública completa es gratis (consulta_publica_base).
    multas_bloqueado = "multas_con_montos" not in productos_desbloqueados
    if multas_bloqueado:
        # El detalle (montos/categorías) se oculta; el teaser solo dice si hay pendientes.
        multas_detalle = []
        multas_pendientes = [
            m.model_copy(update={"valor_usd": None}) for m in multas_pendientes
        ]

    # ── Catálogo (BD) con estado para el frontend ──
    productos = [
        ProductoEstado(
            codigo=p.codigo,
            nombre=p.nombre,
            tokens=p.tokens,
            precio_referencial_usd=getattr(p, "precio_referencial_usd", None),
            sensibilidad=p.sensibilidad,
            descripcion=p.descripcion,
            desbloqueado=p.codigo in productos_desbloqueados,
            disponible=p.codigo in disponibles,
        )
        for p in catalogo
    ]

    return VehiculoConsolidadoResponse(
        placa=placa,
        datos_basicos=datos_basicos,
        identificacion=identificacion,
        titular=titular,
        valores_tributarios=valores_tributarios,
        multas_pendientes=multas_pendientes,
        multas_detalle=multas_detalle,
        multas_bloqueado=multas_bloqueado,
        novedades_legales=novedades_legales,
        estado_fuentes=estado_fuentes,
        productos=productos,
        tiene_pendientes=tiene_pendientes,
    )
