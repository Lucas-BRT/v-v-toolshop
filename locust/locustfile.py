"""Entrypoint do Locust para a suite de carga do Toolshop.

Importa todos os cenarios para que fiquem disponiveis na UI web e na
linha de comando. Para rodar so um deles, passe o nome da classe:

    locust -f locustfile.py BrowseUser

O peso relativo de cada classe (`weight`) define a mistura de trafego
quando nenhuma classe e escolhida explicitamente.
"""

from common import catalog  # noqa: F401  (registra o hook de test_start)
from scenarios.authenticated import AuthenticatedUser
from scenarios.browse import BrowseUser
from scenarios.cart import CartUser

__all__ = ["BrowseUser", "CartUser", "AuthenticatedUser"]
