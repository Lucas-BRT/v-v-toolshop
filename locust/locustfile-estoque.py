"""Locustfile do cenario de sobrevenda de estoque.

Separado do locustfile.py principal porque o EstoqueUser nao faz parte da
mistura de trafego da suite: ele nao mede desempenho, usa a carga para
provocar uma condicao de corrida e verificar uma regra de negocio.

    locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 30s --headless
"""

from scenarios.estoque import EstoqueUser

__all__ = ["EstoqueUser"]
