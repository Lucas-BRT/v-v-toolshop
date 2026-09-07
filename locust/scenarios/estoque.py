"""Cenario de concorrencia: sobrevenda de estoque (oversell).

O QUE ESTE TESTE PROCURA
------------------------
Varios clientes comprando o MESMO produto ao mesmo tempo, somando mais
unidades do que existem em estoque. A pergunta e: a aplicacao recusa o
excedente?

Diferente dos outros cenarios da suite, este nao mede desempenho. Ele usa a
carga como *ferramenta* para provocar uma condicao de corrida e verificar
uma regra de negocio sob concorrencia. O tempo de resposta aqui e
irrelevante; o que importa e quantas unidades a API aceitou vender.

O ORACULO
---------
No fim da execucao comparamos:

    unidades aceitas em pedidos  x  estoque inicial do produto

Se a soma das compras aceitas passar do estoque que existia, a aplicacao
vendeu o que nao tinha. Repare que o criterio NAO depende de o estoque ser
efetivamente debitado: mesmo que o debito nunca aconteca, aceitar o pedido
ja e o defeito.

Um 422 recusando por falta de estoque e contado como SUCESSO — e o
comportamento correto, e e exatamente o que esperamos nao ver.

O QUE FOI ENCONTRADO NA APLICACAO
---------------------------------
1. Nao ha checagem de estoque em lugar nenhum do fluxo de compra. Nem no
   `POST /carts/{id}` (CartService valida a regra do Thor Hammer e a
   quantidade maxima de 99, mas nunca o estoque), nem no `POST /invoices`
   (InvoiceService monta a fatura sem consultar `products.stock`).

2. O debito de estoque acontece em `App\\Jobs\\UpdateProductInventory`:

       $product = Product::where('id', $this->productId)->first();
       $product->decrement('stock', $this->quantity);

   Sem `where('stock', '>=', $quantity)`, sem transacao e sem lock. O
   `decrement` e atomico no nivel do SQL, entao nao ha lost update — mas
   nada impede o estoque de ficar negativo.

3. O `ProductService` guarda os produtos em cache por 300s
   (`CACHE_TTL = 300`, `CACHE_DRIVER=file`) e o job de debito nunca invalida
   esse cache: so `ProductService::update()` chama `clearCache()`, e o job
   desconta direto via Eloquent, sem passar por la. Consequencia medida: com
   o banco ja em -75, a API respondeu 25 por cinco minutos, virando sozinha
   no vencimento do TTL. A loja anuncia estoque que nao existe — o que abre
   espaco para ainda mais sobrevenda.

4. O job e enfileirado (`QUEUE_CONNECTION=database`) e nao ha worker rodando
   no docker-compose. Este ultimo item e do ambiente, nao do codigo: o
   `.env.example` do projeto traz `QUEUE_CONNECTION=sync`, que roda o job
   inline. Com `database` e sem worker os jobs se acumulam na tabela `jobs` e
   o estoque nunca muda — o que esconde os defeitos acima de quem so olha o
   banco. Para processar a fila na mao:

       docker compose exec laravel-api php artisan queue:work --stop-when-empty

RESULTADO MEDIDO
----------------
20 usuarios comprando 5 unidades cada, produto com estoque inicial de 25:

    estoque inicial ................ 25
    unidades aceitas em pedidos .... 100
    pedidos aceitos / recusados .... 20 / 0
    estoque final na API ........... 25   (leitura cacheada)

Nenhum pedido recusado: sobrevenda de 75 unidades. Processando a fila em
seguida, o estoque no banco foi para **-75** — o valor exato previsto pelo
teste. A API continuou respondendo 25 por mais cinco minutos, ate o cache
vencer. O valor real esta sempre no banco:

    docker compose exec -T mariadb mysql -uroot -proot toolshop \
      -e "SELECT name, stock FROM products WHERE stock IS NOT NULL ORDER BY stock LIMIT 5;"

Uso
---
    locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 30s --headless
"""

import logging
import os

import requests
from gevent.lock import Semaphore
from locust import constant, events, task
from locust.exception import StopUser

from common import config
from common.auth import AuthMixin

logger = logging.getLogger(__name__)

# Quantidade que cada pedido tenta comprar. Com 20 usuarios comprando 5
# unidades cada, sao 100 unidades disputando um estoque que costuma ser 25.
QUANTIDADE = int(os.getenv("TOOLSHOP_STOCK_QTY", "5"))

# Produto alvo. Sem isso, escolhemos no test_start o de menor estoque, que e
# o que satura mais rapido.
PRODUTO_FIXO = os.getenv("TOOLSHOP_STOCK_PRODUCT")

# Conta de admin: e a unica que enxerga o numero do estoque. Para os demais,
# `in_stock` vem como booleano (Product::getInStockAttribute).
ADMIN_EMAIL = os.getenv("TOOLSHOP_ADMIN_EMAIL", "admin@practicesoftwaretesting.com")
ADMIN_PASSWORD = os.getenv("TOOLSHOP_ADMIN_PASSWORD", "welcome01")

# Endereco de cobranca sem CEP de proposito: `billing_postal_code` e opcional
# e a regra AddressMatchesCountry so valida quando ele esta presente. Como a
# validacao consulta um servico de CEP externo, incluir o campo tornaria o
# teste dependente de rede — e o assunto aqui e estoque, nao endereco.
COBRANCA = {
    "billing_street": "Teststraat 100",
    "billing_city": "Utrecht",
    "billing_state": "Utrecht",
    "billing_country": "The Netherlands",
}

alvo: dict = {}
_trava = Semaphore()
_contadores = {"unidades_aceitas": 0, "pedidos_aceitos": 0, "pedidos_recusados": 0}


def _token_admin() -> str:
    resposta = requests.post(
        f"{config.API_HOST}/users/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resposta.raise_for_status()
    return resposta.json()["access_token"]


def _estoque(product_id: str, token: str) -> int:
    """Le o estoque real. So funciona com token de admin."""
    resposta = requests.get(
        f"{config.API_HOST}/products/{product_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    resposta.raise_for_status()
    valor = resposta.json().get("in_stock")
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise RuntimeError(
            f"'in_stock' veio como {valor!r}, nao um numero — o token nao e de admin"
        )
    return valor


@events.test_start.add_listener
def preparar(environment, **kwargs):
    """Escolhe o produto alvo e registra o estoque de partida."""
    _contadores.update(unidades_aceitas=0, pedidos_aceitos=0, pedidos_recusados=0)

    try:
        token = _token_admin()

        if PRODUTO_FIXO:
            escolhido = PRODUTO_FIXO
        else:
            pagina = requests.get(
                f"{config.API_HOST}/products?page=1",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=30,
            )
            pagina.raise_for_status()
            # Menor estoque POSITIVO: o alvo precisa ter unidades de verdade
            # para que "vender alem do estoque" signifique alguma coisa. Ha
            # produtos semeados com estoque 0, e a API tambem os vende — use
            # TOOLSHOP_STOCK_PRODUCT para apontar para um deles se quiser ver
            # essa variante, ainda mais direta.
            candidatos = [
                (p["id"], p["name"], p["in_stock"])
                for p in pagina.json().get("data", [])
                if isinstance(p.get("in_stock"), int)
                and not isinstance(p["in_stock"], bool)
                and p["in_stock"] > 0
            ]
            if not candidatos:
                raise RuntimeError("nenhum produto com estoque positivo na pagina 1")
            escolhido = min(candidatos, key=lambda c: c[2])[0]

        alvo["id"] = escolhido
        alvo["estoque_inicial"] = _estoque(escolhido, token)
        alvo["token_admin"] = token
    except Exception as excecao:
        logger.error("Nao foi possivel preparar o cenario de estoque: %s", excecao)
        if environment.runner is not None:
            environment.runner.quit()
        raise

    logger.info(
        "Alvo: produto %s com estoque inicial de %d unidades. "
        "Cada pedido tenta comprar %d.",
        alvo["id"], alvo["estoque_inicial"], QUANTIDADE,
    )


@events.test_stop.add_listener
def verificar(environment, **kwargs):
    """Compara o que foi vendido com o que existia. Este e o teste."""
    if not alvo:
        return

    inicial = alvo["estoque_inicial"]
    vendidas = _contadores["unidades_aceitas"]

    try:
        final = _estoque(alvo["id"], alvo["token_admin"])
    except Exception:
        final = None

    logger.info("=" * 64)
    logger.info("VERIFICACAO DE ESTOQUE — produto %s", alvo["id"])
    logger.info("  estoque inicial ................ %d", inicial)
    logger.info("  unidades aceitas em pedidos .... %d", vendidas)
    logger.info("  pedidos aceitos / recusados .... %d / %d",
                _contadores["pedidos_aceitos"], _contadores["pedidos_recusados"])
    logger.info("  estoque final na API ........... %s  (leitura cacheada)", final)

    if final is not None and final == inicial and vendidas > 0:
        logger.info("  (valor inalterado — duas causas possiveis, as duas medidas:")
        logger.info("     1. os jobs de debito estao na fila, sem worker que os processe;")
        logger.info("     2. o cache de produtos da API guarda o valor antigo por 300s")
        logger.info("        e o job de debito nunca o invalida.")
        logger.info("   O valor real esta no banco: SELECT stock FROM products WHERE id=...)")

    if vendidas > inicial:
        logger.error("  RESULTADO: FALHA — sobrevenda de %d unidades", vendidas - inicial)
        logger.error("  A API aceitou vender %d unidades de um estoque de %d.", vendidas, inicial)
        logger.error("  Nenhum pedido foi recusado por falta de estoque.")
        environment.process_exit_code = 1
    else:
        logger.info("  RESULTADO: ok — nada foi vendido alem do estoque")
    logger.info("=" * 64)


def _registrar(aceito: bool, unidades: int = 0):
    with _trava:
        if aceito:
            _contadores["pedidos_aceitos"] += 1
            _contadores["unidades_aceitas"] += unidades
        else:
            _contadores["pedidos_recusados"] += 1


class EstoqueUser(AuthMixin):
    """Cliente logado tentando comprar o mesmo produto que todos os outros."""

    host = config.API_HOST

    # Sem espera: o objetivo e concentrar as compras na mesma janela de tempo,
    # que e o que provoca a corrida. `wait_time = None` NAO funciona: o Locust
    # trata o valor falsy como "nao definido" e levanta MissingWaitTimeError.
    wait_time = constant(0)

    email = config.CUSTOMER_EMAIL
    password = config.CUSTOMER_PASSWORD

    def on_start(self):
        # Sem o Accept o Laravel responde erro de validacao com um redirect
        # 302 em vez do JSON com o motivo — e o teste perderia a informacao
        # mais importante, que e *por que* o pedido foi recusado.
        self.client.headers.update({"Accept": "application/json"})
        super().on_start()

    @task
    def comprar(self):
        """Uma compra por usuario, e entao o usuario para.

        O oraculo compara unidades aceitas com o estoque inicial, entao a
        carga precisa ser deterministica: N usuarios x QUANTIDADE unidades.
        Sem o StopUser cada usuario ficaria comprando em loop ate o fim do
        --run-time e o total dependeria da duracao, nao do cenario.
        """
        self._comprar()
        raise StopUser()

    def _comprar(self):
        if not alvo:
            return

        with self.client.post("/carts", name="POST /carts", catch_response=True) as resposta:
            if resposta.status_code not in (200, 201):
                resposta.failure(f"criacao de carrinho falhou: HTTP {resposta.status_code}")
                return
            carrinho = resposta.json().get("id")

        with self.client.post(
            f"/carts/{carrinho}",
            json={"product_id": alvo["id"], "quantity": QUANTIDADE},
            name="POST /carts/{id} (add item)",
            catch_response=True,
        ) as resposta:
            if resposta.status_code == 422 and "stock" in resposta.text.lower():
                # Recusa por falta de estoque ja no carrinho: comportamento
                # correto, e o mais cedo possivel.
                resposta.success()
                _registrar(aceito=False)
                return
            if resposta.status_code != 200:
                resposta.failure(f"add item falhou: HTTP {resposta.status_code}")
                return

        with self.client.post(
            "/invoices",
            json={"cart_id": carrinho, "payment_method": "cash-on-delivery",
                  "payment_details": {}, **COBRANCA},
            headers=self.auth_headers(),
            name="POST /invoices (checkout)",
            catch_response=True,
        ) as resposta:
            if resposta.status_code in (200, 201):
                _registrar(aceito=True, unidades=QUANTIDADE)
                resposta.success()
                return
            if resposta.status_code == 422 and "stock" in resposta.text.lower():
                # Recusa por falta de estoque no checkout: tambem correto.
                _registrar(aceito=False)
                resposta.success()
                return
            resposta.failure(f"checkout falhou: HTTP {resposta.status_code} {resposta.text[:120]}")
