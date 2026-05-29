"""Servicio de consulta a la AMT (Agencia Metropolitana de Tránsito de Quito).

Portal público: https://servicios.axiscloud.ec/AutoServicio/inicio.jsp?ps_empresa=03&ps_accion=P55
(URL oficial enlazada desde www.amt.gob.ec → "Consulta tus valores a pagar" → "Infracciones AMT")

AMT corre sobre la plataforma **AxisCloud AutoServicio**, idéntica a la de EPMTSD salvo el
código de empresa. La mecánica de scraping y el parser viven en el adaptador compartido
[_axiscloud.py](_axiscloud.py); aquí solo se fija `ps_empresa=03`.

Cobertura: solo Quito (DMQ). Para vehículos de otras provincias devolverá
estado=sin_resultados o estado=consulta_realizada con totales en cero.

Gotcha (AGENTS.md §8): el portal sirve `inputCode.jsp`/reCAPTCHA a IPs de datacenter,
así que en cloud va por el worker híbrido (IP residencial EC).
"""
from src.modules.consulta.services._axiscloud import consultar_axiscloud

PS_EMPRESA_AMT = "03"


async def consultar_amt(placa: str) -> dict:
    return await consultar_axiscloud(PS_EMPRESA_AMT, "AMT", placa)
