"""Mapa ciudad → provincia → región del Ecuador para el marketplace.

Las publicaciones guardan `ciudad` (catálogo cerrado de 12 ciudades en
`schemas.CiudadPublicacion` para las internas; texto libre para las referenciadas).
El comprador, en cambio, piensa en **provincia** y **región** ("autos en la Costa",
"autos en Pichincha"). Este módulo traduce entre los tres niveles SIN una tabla:
son datos geográficos que no cambian y no hay nada que auditar (mismo criterio que
el catálogo de ciudades).

Solo se mapean las ciudades del catálogo + un puñado de variantes de tipeo que
aparecen en las referencias externas. Una ciudad que no está acá cuenta en el total
general pero no suma a ninguna provincia (bucket implícito "otras").
"""

from __future__ import annotations

# ── Regiones continentales + insular. Orden de norte a sur / relevancia. ──────
REGIONES: tuple[str, ...] = ("Costa", "Sierra", "Amazonía", "Insular")

# ciudad (tal como se guarda) → (provincia, región)
CIUDAD_A_PROVINCIA: dict[str, tuple[str, str]] = {
    "Quito": ("Pichincha", "Sierra"),
    "Guayaquil": ("Guayas", "Costa"),
    "Cuenca": ("Azuay", "Sierra"),
    "Ambato": ("Tungurahua", "Sierra"),
    "Manta": ("Manabí", "Costa"),
    "Loja": ("Loja", "Sierra"),
    "Machala": ("El Oro", "Costa"),
    "Santo Domingo": ("Santo Domingo de los Tsáchilas", "Costa"),
    "Portoviejo": ("Manabí", "Costa"),
    "Ibarra": ("Imbabura", "Sierra"),
    "Riobamba": ("Chimborazo", "Sierra"),
    "Esmeraldas": ("Esmeraldas", "Costa"),
}

# Variantes de tipeo comunes en las referencias externas (texto libre). Se
# normaliza a minúsculas sin tildes antes de buscar acá.
_ALIAS_CIUDAD: dict[str, str] = {
    "santo domingo de los colorados": "Santo Domingo",
    "sto domingo": "Santo Domingo",
    "gye": "Guayaquil",
    "uio": "Quito",
    "quito dm": "Quito",
}


def _normalizar(texto: str) -> str:
    """minúsculas, sin tildes, sin espacios de sobra — para casar texto libre."""
    t = texto.strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u")):
        t = t.replace(a, b)
    return " ".join(t.split())


# Índice normalizado del catálogo + alias, para resolver texto libre de las refs.
_INDICE_NORMALIZADO: dict[str, str] = {
    _normalizar(c): c for c in CIUDAD_A_PROVINCIA
}
_INDICE_NORMALIZADO.update({_normalizar(k): v for k, v in _ALIAS_CIUDAD.items()})


def ciudad_canonica(ciudad: str | None) -> str | None:
    """Devuelve el nombre de ciudad del catálogo que corresponde a `ciudad`
    (exacto o por alias/tipeo), o None si no se reconoce."""
    if not ciudad:
        return None
    if ciudad in CIUDAD_A_PROVINCIA:
        return ciudad
    return _INDICE_NORMALIZADO.get(_normalizar(ciudad))


def provincia_de(ciudad: str | None) -> str | None:
    canon = ciudad_canonica(ciudad)
    return CIUDAD_A_PROVINCIA[canon][0] if canon else None


def region_de(ciudad: str | None) -> str | None:
    canon = ciudad_canonica(ciudad)
    return CIUDAD_A_PROVINCIA[canon][1] if canon else None


def ciudades_de_provincia(provincia: str) -> list[str]:
    """Ciudades del catálogo que pertenecen a esa provincia (para filtrar)."""
    return [c for c, (prov, _) in CIUDAD_A_PROVINCIA.items() if prov == provincia]


def ciudades_de_region(region: str) -> list[str]:
    return [c for c, (_, reg) in CIUDAD_A_PROVINCIA.items() if reg == region]


# Provincias con al menos una ciudad en el catálogo — el conjunto válido para el
# filtro `?provincia=`. Ordenadas alfabéticamente para un 422 predecible.
PROVINCIAS: tuple[str, ...] = tuple(
    sorted({prov for (prov, _) in CIUDAD_A_PROVINCIA.values()})
)
