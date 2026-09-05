"""Cenario 1 - navegacao anonima na loja.

Reproduz o visitante que nao fez login: lista o catalogo, filtra, busca,
abre a pagina de um produto e olha os relacionados. E o perfil de maior
volume em uma loja real, por isso tem o maior peso.
"""

import random

from locust import HttpUser, between, task

from common import catalog, config


class BrowseUser(HttpUser):
    """Visitante anonimo folheando o catalogo."""

    host = config.API_HOST
    wait_time = between(1, 4)
    weight = 6

    @task(10)
    def list_products(self):
        page = random.randint(1, 3)
        self.client.get(f"/products?page={page}", name="GET /products?page=N")

    @task(6)
    def search_products(self):
        term = random.choice(config.SEARCH_TERMS)
        self.client.get(f"/products/search?q={term}", name="GET /products/search?q=N")

    @task(8)
    def product_detail(self):
        product_id = catalog.random_product_id()
        if not product_id:
            return
        self.client.get(f"/products/{product_id}", name="GET /products/{id}")

    @task(3)
    def related_products(self):
        product_id = catalog.random_product_id()
        if not product_id:
            return
        self.client.get(f"/products/{product_id}/related", name="GET /products/{id}/related")

    @task(2)
    def product_specs(self):
        product_id = catalog.random_product_id()
        if not product_id:
            return
        self.client.get(f"/products/{product_id}/specs", name="GET /products/{id}/specs")

    @task(3)
    def filter_by_category(self):
        slug = catalog.random_category_slug()
        if not slug:
            return
        self.client.get(
            f"/products?by_category_slug={slug}", name="GET /products?by_category_slug=N"
        )

    @task(2)
    def filter_by_brand(self):
        brand_id = catalog.random_brand_id()
        if not brand_id:
            return
        self.client.get(f"/products?by_brand={brand_id}", name="GET /products?by_brand=N")

    @task(2)
    def category_tree(self):
        self.client.get("/categories/tree", name="GET /categories/tree")

    @task(1)
    def brands(self):
        self.client.get("/brands", name="GET /brands")

    @task(1)
    def status(self):
        self.client.get("/status", name="GET /status")
