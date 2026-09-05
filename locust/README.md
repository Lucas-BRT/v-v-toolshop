# Testes de carga — Locust

Suite de performance contra a API do Toolshop (`practice-software-testing`).

## Pre-requisitos

A stack precisa estar no ar:

```bash
cd ../practice-software-testing && docker compose up -d
```

A API responde em `http://localhost:8091` (o `web` do compose) e a UI Angular em `http://localhost:4200`.

O `run-locust.sh` cria o virtualenv e instala as dependencias sozinho na primeira execucao — nao ha passo manual de setup.

## Como rodar

O teste e disparado pela CLI, mas a interface web do Locust sobe junto em
`http://localhost:8089` com as metricas ao vivo — graficos de RPS, tempo de
resposta e usuarios ativos. A interface continua no ar depois que o teste
termina, entao da para navegar pelos numeros com calma (bom para apresentar).

```bash
./run-locust.sh smoke           # 5 usuarios, 30s
./run-locust.sh load            # 50 usuarios, 3m
./run-locust.sh stress          # 200 usuarios, 5m
```

Encerre com `Ctrl+C` quando terminar de olhar os graficos.

Segundo argumento escolhe o cenario:

```bash
./run-locust.sh smoke browse    # so navegacao
./run-locust.sh load cart       # so carrinho
./run-locust.sh load auth       # so area logada
./run-locust.sh load all        # mistura por peso (default)
```

Sem argumento nenhum, a interface sobe vazia e o teste e configurado na
propria tela — o `--class-picker` deixa escolher o cenario por la:

```bash
./run-locust.sh                 # UI em http://localhost:8089, disparo manual
```

Para CI ou terminal puro, sem interface:

```bash
HEADLESS=1 ./run-locust.sh load       # so o resumo no terminal
AUTOQUIT=0 ./run-locust.sh load       # com UI, mas encerra ao fim do teste
```

Tudo depois de `--` vai direto para o `locust`:

```bash
./run-locust.sh load all -- --csv-full-history
```

### Relatorios

Os CSVs em `reports/` sao escritos durante a execucao. O HTML e gravado no
momento em que o processo encerra — ou seja, depois do `Ctrl+C` (ou na hora,
se usar `HEADLESS=1` / `AUTOQUIT=0`). A pasta e ignorada pelo git.

### Variaveis de ambiente

| Variavel | Default | Para que serve |
|---|---|---|
| `TOOLSHOP_API_HOST` | `http://localhost:8091` | apontar para outro ambiente |
| `WEB_PORT` | `8089` | porta da interface web |
| `HEADLESS` | — | `1` roda sem interface (CI) |
| `AUTOQUIT` | — | segundos ate encerrar o processo apos o teste |
| `USERS` / `SPAWN_RATE` / `RUN_TIME` | vem do perfil | sobrescrever o perfil escolhido |
| `TOOLSHOP_CUSTOMER_EMAIL` / `_PASSWORD` | usuario semeado | trocar as credenciais do cenario logado |
| `TOOLSHOP_CATALOG_PAGES` | `2` | quantas paginas de produto pre-carregar |

## Cenarios

| Classe | Peso | O que exercita |
|---|---|---|
| `BrowseUser` | 6 | catalogo paginado, busca, detalhe do produto, relacionados, specs, filtro por categoria e marca, arvore de categorias, marcas |
| `CartUser` | 3 | criar carrinho, adicionar item, ler, alterar quantidade, remover item, descartar carrinho |
| `AuthenticatedUser` | 2 | login, `/users/me`, favoritos, faturas, relogin periodico |

Os pesos aproximam o trafego de uma loja: muita leitura anonima, menos escrita, minoria autenticada.

## Decisoes de implementacao

- **Catalogo pre-carregado** (`common/catalog.py`): ids reais de produto, categoria e marca sao buscados uma vez no `test_start`. Se cada task descobrisse o id na hora, cada acao custaria uma requisicao extra e as metricas ficariam infladas.
- **Nomes de request agrupados**: rotas com id usam `name="GET /products/{id}"`. Sem isso o relatorio viraria uma linha por id.
- **Token renovado sozinho** (`common/auth.py`): o JWT da API expira em 300s. O mixin renova aos 240s e tambem refaz login se o token sumir.
- **Regra do Thor Hammer tratada como esperada**: `POST /carts/{id}` devolve `400 You can only have one Thor Hammer in the cart.` — e regra de negocio da loja, nao falha de carga, entao e marcada como sucesso para nao poluir a taxa de erro.
- **Carrinho perdido e recriado**: um `404` no add item (restart da API, `POST /refresh` no banco) faz o usuario virtual criar outro carrinho em vez de falhar em cascata.

## Resultado da execucao inicial

Ambiente local, sprint5, stack em Docker.

`./run-locust.sh smoke` — 5 usuarios, 30s: 54 requisicoes, **0 falhas**, mediana 12 ms, p95 27 ms.

Mistura completa, 15 usuarios, 25s: 141 requisicoes, **0 falhas**, mediana 12 ms, p95 98 ms, max 134 ms.

Pontos mais caros ja nessa carga baixa:

- `POST /users/login` — p50 93 ms. Custo do bcrypt, esperado.
- `POST /carts` — p50 100 ms.
- `GET /products/{id}/related` e `GET /products?page=N` — p90 ~120 ms; o resto do catalogo fica em ~10 ms porque a API cacheia as listagens.

Ou seja: leitura de catalogo esta barata (cache), escrita e autenticacao sao as candidatas a gargalo. Subir para o perfil `stress` e o proximo passo para achar o joelho da curva.

## Estrutura

```
locust/
├── run-locust.sh          # runner (setup do venv + pre-flight + perfis)
├── locustfile.py          # entrypoint, importa os cenarios
├── locust.conf            # defaults de linha de comando
├── requirements.txt
├── common/
│   ├── config.py          # hosts, credenciais, constantes
│   ├── catalog.py         # cache de ids reais carregado no test_start
│   └── auth.py            # mixin de login com renovacao de token
├── scenarios/
│   ├── browse.py          # BrowseUser
│   ├── cart.py            # CartUser
│   └── authenticated.py   # AuthenticatedUser
└── reports/               # saida HTML/CSV (ignorada pelo git)
```
