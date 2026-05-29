"""Ofuscación de identificadores vehiculares sensibles (VIN, motor, chasis)
y decodificación de origen del VIN.

Niveles de visibilidad:
- "completo"  → valor sin ofuscar (solo dueño autenticado).
- "origen"    → solo los primeros 3 caracteres + máscara. Útil para mostrar
                procedencia del vehículo sin exponer el identificador completo.
                Caso típico: comprador interesado con token de compra-venta.
- "oculto"    → valor totalmente enmascarado. Solo aparecen datos derivados
                (país, descripción WMI) si están disponibles.
"""

# Primer carácter del VIN (WMI) → región/país de fabricación.
# Cobertura de los códigos más relevantes para el parque ecuatoriano.
# Referencia: ISO 3779 (World Manufacturer Identifier).
PAISES_VIN: dict[str, str] = {
    # Norteamérica
    "1": "Estados Unidos",
    "4": "Estados Unidos",
    "5": "Estados Unidos",
    "2": "Canadá",
    "3": "México",
    # Sudamérica
    "8": "Argentina/Chile/Ecuador/Perú/Venezuela",
    "9": "Brasil",
    # Asia
    "J": "Japón",
    "K": "Corea del Sur",
    "L": "China",
    "M": "India/Indonesia/Tailandia",
    "N": "Turquía",
    "P": "Filipinas/Malasia",
    "R": "Taiwán/Emiratos Árabes Unidos",
    # Europa
    "S": "Reino Unido",
    "T": "Suiza/Checa/Hungría",
    "U": "Dinamarca/Irlanda/Rumanía",
    "V": "Francia/España/Austria",
    "W": "Alemania",
    "X": "Rusia",
    "Y": "Bélgica/Suecia/Noruega/Finlandia",
    "Z": "Italia",
    # África / Oceanía
    "6": "Australia",
    "7": "Nueva Zelanda",
    "A": "Sudáfrica",
}


def decodificar_origen_vin(vin: str) -> dict:
    """A partir del VIN devuelve `{pais, wmi, descripcion}` o valores nulos
    si el VIN es muy corto o el código no es conocido.

    El WMI (World Manufacturer Identifier) son los 3 primeros caracteres:
      - Carácter 1: región/país.
      - Caracteres 2-3: identifican al fabricante (no decodificamos: hay
        miles de combinaciones; se puede integrar contra una tabla externa
        si se necesita).
    """
    if not vin or len(vin) < 3:
        return {"pais": None, "wmi": None, "descripcion": None}

    vin = vin.upper()
    primer = vin[0]
    wmi = vin[:3]
    pais = PAISES_VIN.get(primer)

    descripcion = (
        f"WMI {wmi} — origen: {pais}" if pais else f"WMI {wmi} — origen desconocido"
    )

    return {"pais": pais, "wmi": wmi, "descripcion": descripcion}


def ofuscar_identificador(
    valor: str | None,
    caracteres_visibles: int = 3,
    relleno: str = "*",
) -> str | None:
    """Devuelve el identificador con solo los primeros `caracteres_visibles`
    visibles y el resto sustituido por `relleno`.

    >>> ofuscar_identificador("JTDBR32E840012345", 3)
    'JTD**************'
    >>> ofuscar_identificador(None)
    None
    """
    if not valor:
        return None
    if caracteres_visibles >= len(valor):
        return valor
    visible = valor[:caracteres_visibles]
    oculto = relleno * (len(valor) - caracteres_visibles)
    return visible + oculto


def ofuscar_vin(vin: str | None, nivel: str = "origen") -> dict:
    """Devuelve un dict con el VIN según el nivel solicitado.

    Estructura:
      {
        "valor_mostrado": str | None,   # el VIN tal como debe mostrarse al receptor
        "pais": str | None,             # país de origen (siempre presente si decodificable)
        "descripcion": str | None,      # descripción del WMI
        "nivel": str,                   # eco del nivel aplicado
      }

    Niveles soportados:
      - "completo": valor sin ofuscar.
      - "origen":   primeros 3 + máscara. Default para vistas compartidas.
      - "oculto":   sin valor mostrado, solo origen decodificado.
    """
    if not vin:
        return {
            "valor_mostrado": None,
            "pais": None,
            "descripcion": None,
            "nivel": nivel,
        }

    origen = decodificar_origen_vin(vin)

    if nivel == "completo":
        valor_mostrado = vin
    elif nivel == "origen":
        valor_mostrado = ofuscar_identificador(vin, caracteres_visibles=3)
    elif nivel == "oculto":
        valor_mostrado = None
    else:
        raise ValueError(
            f"Nivel de ofuscación inválido: {nivel!r}. "
            "Valores válidos: completo, origen, oculto."
        )

    return {
        "valor_mostrado": valor_mostrado,
        "pais": origen["pais"],
        "descripcion": origen["descripcion"],
        "nivel": nivel,
    }
