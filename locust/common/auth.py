"""Mixin de autenticacao para os usuarios virtuais que precisam de token."""

import time

from locust import HttpUser

from common import config


class AuthMixin(HttpUser):
    """Faz login em /users/login e mantem o Bearer token renovado.

    O token da API expira em 300s, entao renovamos por tempo e tambem
    reagimos a um 401 vindo de qualquer chamada autenticada.
    """

    abstract = True

    email = config.CUSTOMER_EMAIL
    password = config.CUSTOMER_PASSWORD

    def on_start(self):
        self.token = None
        self.token_issued_at = 0.0
        self.login()

    def login(self):
        with self.client.post(
            "/users/login",
            json={"email": self.email, "password": self.password},
            name="POST /users/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login falhou: HTTP {response.status_code}")
                self.token = None
                return
            token = response.json().get("access_token")
            if not token:
                response.failure("login sem access_token no corpo")
                self.token = None
                return
            self.token = token
            self.token_issued_at = time.time()
            response.success()

    def auth_headers(self) -> dict[str, str]:
        """Devolve o header Authorization, renovando o token se necessario."""
        expired = time.time() - self.token_issued_at > config.TOKEN_TTL_SECONDS
        if self.token is None or expired:
            self.login()
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}
