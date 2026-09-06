"""Configuracao central dos testes de carga do Toolshop.

Todos os valores podem ser sobrescritos por variavel de ambiente, o que
permite apontar a mesma suite para outro ambiente sem editar codigo.
"""

import os

# Host padrao da API (docker-compose expoe o web server em 8091).
API_HOST = os.getenv("TOOLSHOP_API_HOST", "http://localhost:8091")

# Usuarios semeados por database/seeders/UserSeeder.php.
CUSTOMER_EMAIL = os.getenv(
    "TOOLSHOP_CUSTOMER_EMAIL", "customer@practicesoftwaretesting.com"
)
CUSTOMER_PASSWORD = os.getenv("TOOLSHOP_CUSTOMER_PASSWORD", "welcome01")

# O JWT emitido pela API expira em 300s; renovamos antes disso.
TOKEN_TTL_SECONDS = int(os.getenv("TOOLSHOP_TOKEN_TTL", "240"))

# Quantas paginas do catalogo pre-carregar para sortear ids reais.
CATALOG_PAGES = int(os.getenv("TOOLSHOP_CATALOG_PAGES", "2"))

# Termos usados no cenario de busca.
SEARCH_TERMS = [
    "hammer",
    "pliers",
    "saw",
    "screwdriver",
    "wrench",
    "drill",
    "sander",
    "chisel",
]
