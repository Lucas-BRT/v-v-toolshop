"""Cenario 2 - carrinho de compras (visitante nao logado).

Fluxo de escrita: cria carrinho, adiciona itens, ajusta quantidade, le o
carrinho e remove um item. E o caminho que mais toca o banco, entao e
aqui que a degradacao sob carga costuma aparecer primeiro.
"""

import random

from locust import HttpUser, between, task

from common import catalog, config


class CartUser(HttpUser):
    """Visitante montando um carrinho."""

    host = config.API_HOST
    wait_time = between(2, 5)
    weight = 3

    def on_start(self):
        self.cart_id = None
        # Conjunto, nao lista: sortear o mesmo produto duas vezes empilhava
        # uma duplicata, e o remove_item seguinte apagava o item do carrinho
        # deixando a copia aqui — o update_quantity depois batia em 400 num
        # produto que ja nao existia mais no carrinho.
        self.items: set[str] = set()
        self.create_cart()

    def create_cart(self):
        with self.client.post("/carts", name="POST /carts", catch_response=True) as response:
            if response.status_code not in (200, 201):
                response.failure(f"criacao de carrinho falhou: HTTP {response.status_code}")
                return
            self.cart_id = response.json().get("id")
            self.items = set()
            if not self.cart_id:
                response.failure("resposta de /carts sem id")

    @task(6)
    def add_item(self):
        product_id = catalog.random_product_id()
        if not self.cart_id or not product_id:
            return
        payload = {"product_id": product_id, "quantity": random.randint(1, 3)}
        with self.client.post(
            f"/carts/{self.cart_id}",
            json=payload,
            name="POST /carts/{id} (add item)",
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                # Carrinho sumiu (restart da API / refresh do banco): recria.
                response.success()
                self.create_cart()
                return
            if response.status_code == 400 and "Thor Hammer" in response.text:
                # Regra de negocio da loja: no maximo um Thor Hammer por
                # carrinho. E resposta esperada, nao falha de carga.
                response.success()
                return
            if response.status_code != 200:
                response.failure(f"add item falhou: HTTP {response.status_code}")
                return
            self.items.add(product_id)

    @task(4)
    def read_cart(self):
        if not self.cart_id:
            return
        self.client.get(f"/carts/{self.cart_id}", name="GET /carts/{id}")

    @task(2)
    def update_quantity(self):
        if not self.cart_id or not self.items:
            return
        payload = {
            "product_id": random.choice(sorted(self.items)),
            "quantity": random.randint(1, 5),
        }
        with self.client.put(
            f"/carts/{self.cart_id}/product/quantity",
            json=payload,
            name="PUT /carts/{id}/product/quantity",
            catch_response=True,
        ) as response:
            if response.status_code == 400 and "Thor Hammer" in response.text:
                # Mesma regra de negocio ja tratada no add_item: no maximo um
                # Thor Hammer por carrinho, entao quantity > 1 e recusada
                # (CartService.php:117). E resposta esperada, nao falha de
                # carga. Sem isso o cenario acusava ~0,3% de erro que nao
                # existia.
                response.success()
                return
            if response.status_code != 200:
                response.failure(f"update quantity falhou: HTTP {response.status_code}")

    @task(1)
    def remove_item(self):
        if not self.cart_id or not self.items:
            return
        product_id = self.items.pop()  # set.pop(): remove um elemento qualquer
        self.client.delete(
            f"/carts/{self.cart_id}/product/{product_id}",
            name="DELETE /carts/{id}/product/{productId}",
        )

    @task(1)
    def start_over(self):
        """Simula um novo visitante: descarta o carrinho e cria outro."""
        if self.cart_id:
            self.client.delete(f"/carts/{self.cart_id}", name="DELETE /carts/{id}")
        self.create_cart()
