"""Servicio de consulta a la EPMTSD (EP Municipal de Transporte de Santo Domingo).

Portal público: https://servicios.axiscloud.ec/AutoServicio/inicio.jsp?ps_empresa=06&ps_accion=P55
(enlazado desde www.epmtsd.gob.ec → "Consultas" → "Multas y Citaciones" → "Citaciones EPMT-SD").

EPMTSD corre sobre la **misma plataforma AxisCloud AutoServicio que AMT**, solo cambia
`ps_empresa` (06 vs 03). Toda la mecánica y el parser están en el adaptador compartido
[_axiscloud.py](_axiscloud.py).

Cobertura: solo Santo Domingo de los Tsáchilas. Para vehículos de otras jurisdicciones
devolverá totales en cero.

Gotcha (AGENTS.md §8): igual que AMT, sirve `inputCode.jsp`/reCAPTCHA a IPs de datacenter,
por lo que en cloud se procesa vía el worker híbrido (IP residencial EC).
"""
from src.modules.consulta.services._axiscloud import consultar_axiscloud

PS_EMPRESA_EPMTSD = "06"


async def consultar_epmtsd(placa: str) -> dict:
    return await consultar_axiscloud(PS_EMPRESA_EPMTSD, "EPMTSD", placa)
