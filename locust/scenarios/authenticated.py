"""Cenario 3 - cliente autenticado.

Mede o custo do login em si e das rotas que dependem do JWT: perfil,
favoritos e historico de faturas. Peso menor porque, em uma loja, a
fatia logada e minoria do trafego.
"""

from locust import between, task

from common import config
from common.auth import AuthMixin


class AuthenticatedUser(AuthMixin):
    """Cliente logado consultando area pessoal."""

    host = config.API_HOST
    wait_time = between(2, 5)
    weight = 2

    email = config.CUSTOMER_EMAIL
    password = config.CUSTOMER_PASSWORD

    @task(5)
    def me(self):
        self.client.get("/users/me", headers=self.auth_headers(), name="GET /users/me")

    @task(3)
    def favorites(self):
        self.client.get("/favorites", headers=self.auth_headers(), name="GET /favorites")

    @task(3)
    def invoices(self):
        self.client.get("/invoices", headers=self.auth_headers(), name="GET /invoices")

    @task(1)
    def relogin(self):
        """Reautentica de tempos em tempos para medir o custo do bcrypt."""
        self.login()
