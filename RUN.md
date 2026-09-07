# RUN — todos os comandos

Comandos prontos para copiar e colar. São a CLI original de cada ferramenta,
sem wrapper: o que você cola é exatamente o que a ferramenta recebe.

Há quatro scripts no repositório, e nenhum deles roda teste:

| Script | O que faz |
|---|---|
| `locust/setup.sh` | prepara o ambiente (venv + dependências) |
| `artillery/setup.sh` | prepara o ambiente (`npm install`) |
| `locust/conferir-estoque.sh` | lê o estoque pelo banco e pela API, lado a lado |
| `reset.sh` | devolve o banco ao estado logo após o seed |

Os comandos são o mínimo necessário: **rode e observe as métricas na tela.**
Se quiser gravar o resultado em arquivo, veja a [seção 4](#4-se-quiser-gravar-o-resultado).

O que cada teste procura: [`CENÁRIOS_DE_TESTE.md`](CENÁRIOS_DE_TESTE.md).

---

## 0. Preparo

```bash
# a stack precisa estar no ar
cd practice-software-testing && docker compose up -d
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8091/status   # 200
```

```bash
# uma vez por suite
cd locust    && ./setup.sh      # python3 -m venv .venv + pip install -r requirements.txt
cd artillery && ./setup.sh      # npm install
```

---

## 1. Locust

A partir de `locust/`, com o virtualenv ativo:

```bash
cd locust
source .venv/bin/activate
```

> Sem ativar o virtualenv, troque `locust` por `.venv/bin/locust`.

O `locust.conf` desta pasta já define `locustfile` e `host`, por isso `-f` e
`--host` não aparecem. A interface web sobe em `http://localhost:8089` (porta
padrão) e continua no ar depois do teste — `Ctrl+C` encerra.

### Descobrir o que existe

```bash
locust -l                     # classes de usuário disponíveis
locust --show-task-ratio      # proporção entre as tasks de cada classe
```

### Interface web vazia — carga escolhida na tela

```bash
locust --class-picker
```

### Smoke — 5 usuários, 30s

```bash
locust --users 5 --run-time 30s --autostart
```

### Load — 50 usuários, 3 minutos

```bash
locust --users 50 --spawn-rate 5 --run-time 3m --autostart
```

### Stress — 200 usuários, 5 minutos

```bash
locust --users 200 --spawn-rate 20 --run-time 5m --autostart
```

### Escolher uma classe só

O nome vai no fim. Sem ele, roda a mistura por peso (6 navegação, 3
carrinho, 2 autenticado).

```bash
locust --users 50 --spawn-rate 5 --run-time 3m --autostart BrowseUser
locust --users 50 --spawn-rate 5 --run-time 3m --autostart CartUser
locust --users 50 --spawn-rate 5 --run-time 3m --autostart AuthenticatedUser
```

### Sobrevenda de estoque — teste de concorrência

Não mede desempenho: usa a carga para provocar uma condição de corrida.
Vários clientes compram o mesmo produto ao mesmo tempo, somando mais
unidades do que existem. **Sai com exit code 1 quando há sobrevenda.**

```bash
locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --autostart
echo "exit=$?"
```

O veredito aparece no log, no fim da execução. Para ver o estoque ficar
negativo de verdade, processe a fila depois (o `docker-compose` não sobe
worker, então os débitos ficam parados):

```bash
cd ../practice-software-testing
docker compose exec laravel-api php artisan queue:work --stop-when-empty
```

#### Conferir o estoque

As duas leituras **discordam**, e a discordância é um achado, não um erro de
comando. O banco mostra o valor real. A API responde através de um cache de
5 minutos (`ProductService::CACHE_TTL = 300`, `CACHE_DRIVER=file`) que o job
de débito nunca invalida — só `ProductService::update()` chama `clearCache()`,
e o `UpdateProductInventory` desconta direto via Eloquent, sem passar por lá.

Medido: banco em `-75` enquanto a API respondia `25` por 5 minutos seguidos,
virando para `-75` sozinha no vencimento do TTL. Ou seja, a loja anuncia
estoque que não existe pela duração do cache — o que permite ainda mais
sobrevenda.

Use o banco para o valor real; a API para mostrar o atraso. Para forçar a API
a concordar sem esperar: `docker compose exec laravel-api php artisan cache:clear`.

`conferir-estoque.sh` lê **as duas fontes numa única execução** — banco e API
lado a lado, uma coluna cada. A coluna `!` marca onde elas discordam:

```bash
cd locust
./conferir-estoque.sh                                 # todos os produtos
./conferir-estoque.sh 01M1WDNXEWY6TZ8JS4P6XTZR7N      # só um produto
./conferir-estoque.sh --limpar-cache                  # invalida o cache antes de ler
```

```
FONTE 1 = banco (products.stock, valor real)
FONTE 2 = API  (/products, atraves do cache de 300s)

ID                           PRODUTO                       BANCO        API  !
------------------------------------------------------------------------------
01M1WDNXEWY6TZ8JS4P6XTZR7M   Pliers                         -275       -275
01M1WDNXEWY6TZ8JS4P6XTZR7N   Bolt Cutters                   -999        -75  <-- divergem
01M1WDNXEWY6TZ8JS4P6XTZR7P   Long Nose Pliers                  0          0

2 produto(s) com estoque NEGATIVO no banco — a API vendeu o que nao tinha.
1 linha(s) divergem: a API serve valor cacheado (TTL 300s) que o job de
debito nunca invalida. Use --limpar-cache para forcar, ou espere o TTL vencer.
```

As duas consultas separadas, caso queira rodar uma de cada vez sem o script:

```bash
# banco — o valor real
cd ../practice-software-testing
docker compose exec -T mariadb mysql -uroot -proot toolshop -e "
  SELECT id, name, stock FROM products WHERE stock IS NOT NULL ORDER BY stock LIMIT 10;
  SELECT COUNT(*) AS jobs_na_fila FROM jobs;"
```

```bash
# API — através do cache; precisa de token de admin, porque para os demais
# `in_stock` vem como booleano (`Product::getInStockAttribute`)
API=${TOOLSHOP_API_HOST:-http://localhost:8091}
TOKEN=$(curl -s -H 'Content-Type: application/json' \
    -d '{"email":"admin@practicesoftwaretesting.com","password":"welcome01"}' \
    "$API/users/login" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -s -H "Authorization: Bearer $TOKEN" "$API/products?page=1" | python3 -c '
import json, sys
for p in sorted(json.load(sys.stdin)["data"], key=lambda p: p["in_stock"]):
    print("%6s  %-40s %s" % (p["in_stock"], p["name"], p["id"]))
'
```

`stock IS NOT NULL` porque os itens de aluguel (Excavator, Bulldozer, Crane)
não têm estoque — sem o filtro eles ocupam o topo da lista ordenada.

#### Os quatro defeitos que este cenário expõe

| #   | Defeito                                                                                                              | Onde                                     | Código ou ambiente |
| --- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ------------------ |
| 1   | Nenhuma checagem de estoque no fluxo de compra: a API aceita o pedido e emite a nota                                 | `CartService`, `InvoiceService.php:60`   | código             |
| 2   | `decrement` sem `where('stock','>=',$q)`, sem transação e sem lock — estoque vai a negativo                          | `Jobs/UpdateProductInventory.php`        | código             |
| 3   | Cache de produtos de 300s que o job de débito nunca invalida — a loja anuncia estoque que não existe                 | `ProductService.php:19`                  | código             |
| 4   | `QUEUE_CONNECTION=database` sem worker no `docker-compose` — jobs se acumulam e escondem 1–3 de quem só olha o banco | `docker-compose.yml`, `sprint5/API/.env` | ambiente           |

O item 4 é o único que não é defeito da aplicação: o `.env.example` do projeto
traz `QUEUE_CONNECTION=sync`, que roda o job inline e dispensa worker. Quem
montou este ambiente trocou para `database`. Ele não _cria_ os defeitos 1–3 —
apenas os esconde.

Medição que separa os três primeiros: 20 pedidos de 5 unidades sobre estoque 25. Todos aceitos (defeito 1). Depois do `queue:work`, banco em `-75`
(defeito 2). A API continuou respondendo `25` por cinco minutos, virando
sozinha às 08:04:20 quando o TTL venceu (defeito 3).

Sequência que fecha o argumento:

```bash
cd locust

# 1. estado inicial — tudo em 25, banco e API de acordo
./conferir-estoque.sh

# 2. o teste — 20 pedidos de 5 unidades sobre um estoque de 25.
#    Sai com exit code 1: todos aceitos, nenhum recusado.
locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --headless

# 3. logo depois: banco e API ainda em 25, porque os jobs estão parados na fila
./conferir-estoque.sh

# 4. processa a fila na mão — é o worker que o docker-compose não sobe
cd ../practice-software-testing
docker compose exec laravel-api php artisan queue:work --stop-when-empty

# 5. agora o banco mostra -75, e a API ainda mostra 25: a coluna `!` acusa
cd ../locust
./conferir-estoque.sh

# 6. cinco minutos depois (ou com --limpar-cache) a API finalmente concorda
./conferir-estoque.sh --limpar-cache
```

Para voltar ao estado semeado, da raiz do repositório: `./reset.sh`. Ele
recria o banco, esvazia a fila `jobs`, apaga as notas e limpa o cache — e
com isso apaga também as evidências desta execução, então registre o que
precisa antes.

Ajustes:

```bash
# quantas unidades cada pedido tenta comprar (default 5)
TOOLSHOP_STOCK_QTY=10 locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --headless

# apontar para um produto específico — inclusive um com estoque 0,
# que a API também vende
TOOLSHOP_STOCK_PRODUCT=<id> locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --headless
```

### Experimento pareado — lado fechado

Locustfile próprio: o `ComparativoUser` não faz parte da mistura da suite.
150 usuários com `constant_throughput(1)` oferecem 150 jornadas/s — a mesma
carga que o Artillery oferece com `arrivalRate: 150`.

```bash
locust -f locustfile-comparativo.py --users 150 --spawn-rate 150 --run-time 60s --headless
```

---

## 2. Artillery

A partir de `artillery/`:

```bash
cd artillery
```

Cada cenário já traz o próprio `target` no YAML. As métricas saem no
terminal, fase a fase e no resumo final.

### Descobrir o que existe

```bash
ls scenarios/
head -3 scenarios/*.yml       # a primeira linha de comentário descreve cada um
```

### Os três cenários

```bash
# 1) spike no login: fila e recuperação — o teste crítico (105s)
npx artillery run scenarios/01-pico-de-trafego.yml

# 2) portão de deploy: expect + ensure com exit code (75s)
npx artillery run scenarios/02-portao-ci.yml ; echo "exit=$?"

# 3) metade aberta do experimento pareado com o Locust (75s)
npx artillery run scenarios/03-comparativo-modelo-aberto.yml
```

### Os três, em sequência

```bash
for f in scenarios/*.yml; do npx artillery run "$f"; done
```

Leva cerca de 4 minutos. Não para no primeiro que falhar.

---

## 3. Combinações que precisam de dois terminais

### O portão de CI fechando

Sozinho o `02-portao-ci` passa. Para vê-lo **falhar**, dispare durante o
pico:

```bash
# terminal 1 — pico no login
cd artillery
npx artillery run scenarios/01-pico-de-trafego.yml
```

```bash
# terminal 2 — logo em seguida
cd artillery
npx artillery run scenarios/02-portao-ci.yml ; echo "exit=$?"
```

Esperado: `exit=1`, p95 de ~6300 ms contra o limite de 120 ms.

### O experimento pareado

Mesma carga oferecida (150 jornadas/s), mesmas rotas, 60s. Única variável: o
modelo de carga.

```bash
# lado FECHADO — RPS estabiliza em ~156/s, p50 plano em ~940 ms, 0 falhas
cd locust && source .venv/bin/activate
locust -f locustfile-comparativo.py --users 150 --spawn-rate 150 --run-time 60s --headless
```

```bash
# lado ABERTO — p50 sobe de 1901 ms até ~29 s, ~40% de timeouts
cd artillery
npx artillery run scenarios/03-comparativo-modelo-aberto.yml
```

---

## 4. Se quiser gravar o resultado

Os comandos acima não escrevem arquivo nenhum — as métricas aparecem no
terminal e, no caso do Locust, também na interface web. Não existe pasta de
relatórios no repositório: se quiser guardar, aponte para onde preferir.

```bash
# Locust: HTML (gravado no encerramento) e CSV (gravado durante a execução)
locust --users 50 --spawn-rate 5 --run-time 3m --headless CartUser \
       --html /tmp/load-cart.html --csv /tmp/load-cart

# Artillery: JSON com as métricas
npx artillery run --output /tmp/portao-ci.json scenarios/02-portao-ci.yml
npx artillery run --output /tmp/pico.json scenarios/01-pico-de-trafego.yml
```

Útil quando você precisa comparar duas execuções — grave as duas com nomes
diferentes:

```bash
npx artillery run --output /tmp/antes.json scenarios/02-portao-ci.yml
npx artillery run --output /tmp/depois.json scenarios/02-portao-ci.yml
```

### Ler o que foi gravado

```bash
xdg-open /tmp/load-cart.html            # relatório do Locust
cat /tmp/load-cart_failures.csv         # só as falhas
```

```bash
# Artillery: resumo agregado
python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))["aggregate"]
s = d["summaries"]["http.response_time"]
print("req", d["counters"].get("http.requests"), "p50", s["median"], "p95", s["p95"])
print({k: v for k, v in d["counters"].items() if "http.codes" in k or k.startswith("errors.")})
' /tmp/portao-ci.json
```

```bash
# Artillery: janela a janela — é onde a fila do spike aparece
python3 -c '
import json, sys
for i in json.load(open(sys.argv[1]))["intermediate"]:
    s = i["summaries"].get("http.response_time") or {}
    rps = i["rates"].get("http.request_rate") or 0
    print("rps=%5s  p50=%9s  p95=%9s" % (rps, s.get("median"), s.get("p95")))
' /tmp/pico.json
```

## 5. Operação e problemas conhecidos

```bash
# devolve o banco ao estado logo após o seed — estoque em 25, fila `jobs`
# vazia, notas apagadas, contas destravadas (HTTP 423 após 3 logins inválidos)
./reset.sh
# equivalente: curl -X POST http://localhost:8091/refresh
```

```bash
# /products devolvendo 500 permanente após sobrecarga sustentada.
# O reset NÃO conserta: ele recria o banco, não o cache em disco.
cd practice-software-testing
docker compose exec -u root laravel-api \
  chown -R www-data:www-data storage/framework/cache
```

```bash
# porta 8089 presa por uma interface do Locust deixada aberta
ss -ltnp | grep 8089
pkill -INT -f '.venv/bin/locust'
```

```bash
# o RPS não sobe mesmo aumentando usuários?
# pode ser o gerador saturado, não a API — confirme antes de concluir
locust -f locustfile.py,shapes/degraus.py --headless --processes 4 AuthenticatedUser
```
