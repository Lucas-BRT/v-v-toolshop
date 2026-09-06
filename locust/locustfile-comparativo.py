"""Locustfile do experimento comparativo — carregado so pelo perfil `comp`.

Fica separado do locustfile.py principal de proposito: o ComparativoUser
nao faz parte da mistura de trafego da suite, ele existe unicamente para
ser pareado com o cenario 15 do Artillery.
"""

from scenarios.comparativo import ComparativoUser

__all__ = ["ComparativoUser"]
