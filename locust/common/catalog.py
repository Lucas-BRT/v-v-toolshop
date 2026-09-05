"""Cache do catalogo compartilhado entre todos os usuarios virtuais.

Buscar ids de produto/categoria/marca dentro das tasks distorceria as
metricas (cada task faria uma requisicao extra so para descobrir um id).
Carregamos uma vez no inicio do teste e sorteamos daqui.
"""

import logging
import random

import requests
from locust import events

from common import config

logger = logging.getLogger(__name__)

product_ids: list[str] = []
category_slugs: list[str] = []
brand_ids: list[str] = []


def _get_json(path: str):
    response = requests.get(f"{config.API_HOST}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def _collect_category_slugs(nodes, acc):
    for node in nodes:
        slug = node.get("slug")
        if slug:
            acc.append(slug)
        _collect_category_slugs(node.get("sub_categories") or [], acc)


@events.test_start.add_listener
def load_catalog(environment, **kwargs):
    """Pre-carrega ids reais antes do teste comecar."""
    product_ids.clear()
    category_slugs.clear()
    brand_ids.clear()

    try:
        for page in range(1, config.CATALOG_PAGES + 1):
            payload = _get_json(f"/products?page={page}")
            product_ids.extend(item["id"] for item in payload.get("data", []))

        _collect_category_slugs(_get_json("/categories/tree"), category_slugs)
        brand_ids.extend(item["id"] for item in _get_json("/brands"))
    except Exception as exc:  # pragma: no cover - depende do ambiente
        logger.error("Falha ao carregar catalogo de %s: %s", config.API_HOST, exc)
        logger.error("A API esta no ar? Suba com: docker compose up -d")
        raise

    logger.info(
        "Catalogo carregado: %d produtos, %d categorias, %d marcas",
        len(product_ids),
        len(category_slugs),
        len(brand_ids),
    )


def random_product_id() -> str | None:
    return random.choice(product_ids) if product_ids else None


def random_category_slug() -> str | None:
    return random.choice(category_slugs) if category_slugs else None


def random_brand_id() -> str | None:
    return random.choice(brand_ids) if brand_ids else None
