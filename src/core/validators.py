import re


def validar_placa(placa: str) -> str:
    placa = placa.upper().replace("-", "").replace(" ", "")
    patron = r"^[A-Z]{3}[0-9]{3,4}$"
    if not re.match(patron, placa):
        raise ValueError("Formato de placa inválido")
    return placa


def validar_cedula(cedula: str) -> str:
    """Valida una cédula ecuatoriana (10 dígitos con dígito verificador módulo 10).

    Reglas:
      - 10 dígitos numéricos.
      - Los dos primeros = código de provincia (01-24, o 30 transferidos).
      - El tercero < 6 para personas naturales.
      - Dígito verificador con coeficientes alternos 2,1,2,1,2,1,2,1,2 (mod 10).

    Devuelve la cédula normalizada (sin guiones ni espacios). Lanza ValueError
    con mensaje en español si algo falla.
    """
    cedula = cedula.strip().replace("-", "").replace(" ", "")

    if not cedula.isdigit() or len(cedula) != 10:
        raise ValueError("Cédula debe tener exactamente 10 dígitos numéricos")

    provincia = int(cedula[:2])
    if not (1 <= provincia <= 24 or provincia == 30):
        raise ValueError(f"Código de provincia inválido: {provincia:02d}")

    tercer = int(cedula[2])
    if tercer >= 6:
        raise ValueError(f"El tercer dígito de una cédula natural debe ser < 6 (es {tercer})")

    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    suma = 0
    for i, c in enumerate(cedula[:9]):
        producto = int(c) * coeficientes[i]
        if producto >= 10:
            producto -= 9
        suma += producto

    verificador_esperado = (10 - (suma % 10)) % 10
    verificador_dado = int(cedula[9])

    if verificador_esperado != verificador_dado:
        raise ValueError("Dígito verificador de cédula incorrecto")

    return cedula


# Tabla de transliteración del estándar ISO 3779 para validar el dígito
# verificador del VIN (posición 9). Letras I, O, Q no son válidas.
_VIN_VALORES = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9,
}
_VIN_PESOS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def validar_vin(vin: str) -> str:
    """Valida un VIN (Vehicle Identification Number) según ISO 3779/3780.

    Reglas:
      - 17 caracteres alfanuméricos.
      - No puede contener I, O, Q (confusión con 1 y 0).
      - El dígito verificador (posición 9) coincide con el algoritmo de la
        norma (suma ponderada mod 11, donde 10 se representa como 'X').

    Devuelve el VIN normalizado (mayúsculas, sin espacios). Lanza ValueError
    con mensaje en español si algo falla.
    """
    vin = vin.upper().strip().replace("-", "").replace(" ", "")

    if len(vin) != 17:
        raise ValueError(f"VIN debe tener exactamente 17 caracteres (tiene {len(vin)})")

    if not vin.isalnum():
        raise ValueError("VIN solo admite caracteres alfanuméricos")

    invalidas = set(vin) & {"I", "O", "Q"}
    if invalidas:
        raise ValueError(
            f"VIN no puede contener las letras {sorted(invalidas)} (confusión con 1/0)"
        )

    suma = 0
    for i, c in enumerate(vin):
        if c not in _VIN_VALORES:
            raise ValueError(f"Carácter inválido en VIN: {c!r} en posición {i + 1}")
        suma += _VIN_VALORES[c] * _VIN_PESOS[i]

    esperado_num = suma % 11
    esperado = "X" if esperado_num == 10 else str(esperado_num)
    real = vin[8]

    if esperado != real:
        raise ValueError(
            f"Dígito verificador del VIN incorrecto: esperaba {esperado}, recibió {real}"
        )

    return vin
