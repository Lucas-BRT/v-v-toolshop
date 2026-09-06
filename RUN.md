# RUN — todos os comandos

Comandos prontos para copiar e colar. São a CLI original de cada ferramenta,
sem wrapper: o que você cola é exatamente o que a ferramenta recebe.

Só há dois scripts neste repositório, e nenhum deles roda teste — os dois
apenas preparam o ambiente: `locust/setup.sh` e `artillery/setup.sh`.

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

### Rampa escalonada — acha o joelho da curva

A carga vem de uma `LoadTestShape`, carregada como segundo locustfile.
`--users` e `--spawn-rate` não aparecem: quem controla os dois é a shape, e
passá-los não dá erro nem aviso — são silenciosamente ignorados.

```bash
# degraus 10 → 400 usuários, 60s cada (6 minutos no total)
locust -f locustfile.py,shapes/degraus.py --autostart AuthenticatedUser
```

```bash
# degraus mais curtos, para apresentar em ~2 minutos
STEP_SECONDS=20 locust -f locustfile.py,shapes/degraus.py --autostart AuthenticatedUser
```

```bash
# no carrinho, para contraste: não satura nem a 400 usuários
locust -f locustfile.py,shapes/degraus.py --autostart CartUser
```

### Sobrevenda de estoque — teste de concorrência

Não mede desempenho: usa a carga para provocar uma condição de corrida.
Vários clientes compram o mesmo produto ao mesmo tempo, somando mais
unidades do que existem. **Sai com exit code 1 quando há sobrevenda.**

```bash
locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --headless
echo "exit=$?"
```

O veredito aparece no log, no fim da execução. Para ver o estoque ficar
negativo de verdade, processe a fila depois (o `docker-compose` não sobe
worker, então os débitos ficam parados):

```bash
cd ../practice-software-testing
docker compose exec laravel-api php artisan queue:work --stop-when-empty
```

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

### Variações

```bash
# sem interface web (CI): troque --autostart por --headless
locust --users 50 --spawn-rate 5 --run-time 3m --headless CartUser

# outra porta, se a 8089 estiver presa
locust --users 5 --run-time 30s --autostart --web-port 8090

# encerra sozinho ao fim, sem esperar Ctrl+C
locust --users 5 --run-time 30s --autostart --autoquit 0

# distribui em processos, se o gerador saturar antes da API (experimental)
locust -f locustfile.py,shapes/degraus.py --headless --processes 4 AuthenticatedUser

# distribuído entre máquinas
locust --master
locust --worker --master-host 192.168.1.10

# apontar para outro ambiente
TOOLSHOP_API_HOST=http://staging.exemplo:8091 locust --users 5 --run-time 30s --headless
```

### Variáveis de ambiente lidas pela suite

| Variável | Default | Efeito |
|---|---|---|
| `TOOLSHOP_API_HOST` | `http://localhost:8091` | host da API |
| `STEP_SECONDS` | `60` | segundos em cada degrau da rampa |
| `TOOLSHOP_CUSTOMER_EMAIL` / `_PASSWORD` | usuário semeado | credenciais do cenário logado |
| `TOOLSHOP_CATALOG_PAGES` | `2` | páginas de produto pré-carregadas |
| `TOOLSHOP_STOCK_QTY` | `5` | unidades por pedido no teste de sobrevenda |
| `TOOLSHOP_STOCK_PRODUCT` | menor estoque positivo | produto alvo do teste de sobrevenda |
| `TOOLSHOP_ADMIN_EMAIL` / `_PASSWORD` | admin semeado | conta que enxerga o número do estoque |

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

### Variações

```bash
# só o resumo, sem o log fase a fase
npx artillery run --quiet scenarios/02-portao-ci.yml

# apontar para outro ambiente
npx artillery run --target http://staging.exemplo:8091 scenarios/02-portao-ci.yml

# sobrescrever as fases sem editar o arquivo
npx artillery run \
    --overrides '{"config":{"phases":[{"duration":10,"arrivalRate":5}]}}' \
    scenarios/01-pico-de-trafego.yml
```

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
# conta de cliente travada (HTTP 423) após 3 logins inválidos
cd artillery && ./setup.sh reset
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
