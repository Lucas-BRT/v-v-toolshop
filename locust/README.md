# Locust

Ferramenta de teste de carga onde **o teste é código Python**. Não há DSL,
nem YAML, nem gravador de tráfego: um usuário virtual é uma classe, e cada
ação dele é um método decorado com `@task`.

Comandos para executar: [`../RUN.md`](../RUN.md).
Catálogo com durações e números esperados: [`../CENÁRIOS_DE_TESTE.md`](../CENÁRIOS_DE_TESTE.md).
Material de apresentação: [`APRESENTACAO.md`](APRESENTACAO.md).

---

## Para que serve

Responder **"quantos usuários simultâneos o sistema aguenta antes de
degradar?"** — e, no caminho, expor defeitos que só aparecem quando muita
gente usa o sistema ao mesmo tempo.

A resposta vem do **modelo fechado**, que é a decisão de projeto da qual
tudo o mais decorre. Você configura usuários simultâneos, não requisições
por segundo. Cada usuário virtual é um laço:

```
faz requisição → ESPERA A RESPOSTA → pensa um pouco → repete
```

O "espera a resposta" é a peça toda. Se a API fica lenta, o usuário demora
mais para dar a volta no laço, e ninguém empurra requisições novas enquanto
isso. Existem no máximo N requisições em voo, porque existem N usuários.

| | Consequência |
|---|---|
| Se a API desacelera | a taxa de requisições **cai sozinha** |
| Fila | não se forma — não há como |
| Latência | encontra um teto |
| O número que sai | é a **capacidade** do sistema |

Como o teste é código, o usuário virtual carrega **estado**: o objeto vive
durante toda a execução e guarda carrinho, token, histórico — como uma
sessão real. É o que permite caçar defeitos de sequência, não só de volume.

---

## Que problemas esta ferramenta procura

### Encontra

| Problema | Como aparece |
|---|---|
| **Capacidade desconhecida** | o RPS achata num teto enquanto a latência assume o crescimento |
| **Defeito de estado de sessão** | carrinho perdido, token expirado no meio, sequência inválida de operações |
| **Regra de negócio disparando sob concorrência** | erro que o teste sem estado nunca provoca |
| **Degradação lenta** | patamar alto sustentado revela vazamento de memória, pool esgotando, cache envenenando |
| **Rota cara escondida na média** | agrupar requisições por nome expõe qual endpoint carrega o percentil alto |
| **Regra de negócio que só quebra sob concorrência** | vários usuários disputando o mesmo recurso expõem a falta de checagem, transação ou lock |

### Não encontra — por construção

| Problema | Por quê |
|---|---|
| **Formação de fila** | impossível no modelo fechado: a carga se autolimita |
| **Tempo de recuperação após pico** | idem — nunca há fila para drenar |
| **Regressão de SLA em pipeline** | `--exit-code-on-error` reage a *erros*, não a *latência*; não existe `assert p95 < X` pronto |
| **Quebra de contrato sob carga** | `catch_response` permite validar corpo, mas é manual — não há validação declarativa de schema |

Essas quatro lacunas são exatamente o que a suite `../artillery` cobre.

---

## Os casos de teste

### `BrowseUser` — leitura anônima (peso 6)

Catálogo paginado, busca, detalhe do produto, relacionados, specs, filtro
por categoria e por marca, árvore de categorias, marcas.

**Que problema procura:** o caminho de maior volume de uma loja é leitura
anônima. Se o cache não estiver absorvendo, se a paginação fizer varredura,
se um filtro estiver sem índice ou se a árvore de categorias montar em N+1
consultas, é aqui que aparece — e aparece cedo, porque este perfil concentra
a maior parte do tráfego.

### `CartUser` — escrita com estado (peso 3)

Cria carrinho, adiciona item, lê, altera quantidade, remove item, descarta e
recomeça.

**Que problema procura:** é o caminho que mais toca o banco e o único com
estado de verdade. Procura corrupção de estado sob concorrência, carrinho
perdido entre operações, regra de negócio recusando o que deveria aceitar, e
degradação de escrita que a leitura cacheada esconderia.

### `AuthenticatedUser` — área logada (peso 2)

Login, `/users/me`, favoritos, faturas, e relogin periódico.

**Que problema procura:** o login roda bcrypt, que é caro **de propósito** —
é assim que ele protege a senha. Não é cacheável e consome CPU por
requisição. Este perfil procura o ponto em que o hash de senha satura o
processador antes de qualquer outra coisa, e verifica se as rotas
autenticadas continuam respondendo quando isso acontece.

O peso 2 é deliberado: em uma loja, a fatia logada é minoria do tráfego. Os
pesos 6/3/2 aproximam essa proporção — confira com `locust --show-task-ratio`.

### Rampa escalonada (`shapes/degraus.py`)

Sobe os usuários simultâneos em degraus de 10 a 400, mantendo cada degrau
tempo suficiente para estabilizar.

**Que problema procura:** *não saber a capacidade*. Um patamar fixo diz se
o sistema aguenta aquele patamar; não diz onde ele para de aguentar.
Enquanto há folga, dobrar os usuários dobra o RPS e a latência quase não se
move. **O joelho é onde o RPS achata e a latência assume o crescimento** —
esse teto é a capacidade, e é o número que dimensiona infraestrutura.

Precisa de uma `LoadTestShape` porque `--users` define um único patamar;
varrer vários na mesma execução, com o mesmo processo e o mesmo estado de
usuário virtual, não tem outro jeito.

### `EstoqueUser` — sobrevenda sob concorrência

Vários clientes comprando o **mesmo** produto ao mesmo tempo, somando mais
unidades do que existem em estoque.

**Que problema procura:** *a aplicação aceitar vender o que não tem.* É o
único caso da suite que não mede desempenho — ele usa a carga como
ferramenta para provocar uma condição de corrida e verificar uma regra de
negócio sob concorrência. O tempo de resposta é irrelevante aqui; o que
importa é quantas unidades a API aceitou.

O oráculo compara **unidades aceitas em pedidos** com o **estoque inicial**.
O critério não depende de o estoque ser debitado: aceitar o pedido já é o
defeito. Um 422 recusando por falta de estoque conta como sucesso — é o
comportamento correto, e é justamente o que não acontece.

**Defeito confirmado.** 20 usuários × 5 unidades contra um estoque de 25:
os 20 pedidos foram aceitos, nenhum recusado, sobrevenda de 75 unidades.
Processando a fila em seguida, o estoque foi para **−75**. Causas:

- não há checagem de estoque em lugar nenhum do fluxo. O `CartService`
  valida a regra do Thor Hammer e o teto de 99 por requisição, mas nunca o
  estoque; o `InvoiceService` monta a fatura sem consultar `products.stock`;
- o débito vive em `App\Jobs\UpdateProductInventory`, que faz
  `$product->decrement('stock', $quantity)` sem `where('stock', '>=', ...)`,
  sem transação e sem lock. O `decrement` é atômico no SQL, então não há
  *lost update* — mas nada impede o estoque de ficar negativo;
- o job é enfileirado e o `docker-compose` não sobe worker nenhum, então os
  débitos se acumulam na tabela `jobs` e o estoque parece intacto. Isso
  **esconde o defeito** de quem só olha o banco.

### `locustfile-comparativo.py` — lado fechado do experimento pareado

Jornada de login + leitura autenticada, com `constant_throughput(1)` para
fixar a carga oferecida.

**Que problema procura:** *confundir capacidade com resiliência*. É a metade
fechada de um experimento cuja outra metade é
`../artillery/scenarios/03-comparativo-modelo-aberto.yml`. Mesma carga
oferecida, mesmas rotas, mesma duração — só o modelo muda. Serve para
mostrar que os dois números respondem perguntas diferentes e que nenhum
substitui o outro.

---

## Armadilhas de medição que a suite evita

Cada uma destas é um jeito de o teste medir a coisa errada e reportar um
resultado bonito e falso.

| Armadilha | Como é evitada |
|---|---|
| **Descobrir id dentro da task** infla toda ação com uma requisição extra | ids reais de produto, categoria e marca são pré-carregados uma vez no `test_start` (`common/catalog.py`) |
| **Relatório com uma linha por id** torna qualquer percentil inútil | rotas com id usam `name="GET /products/{id}"` |
| **Token expirando no meio** faz metade das requisições virar 401 e culpar a API | o JWT expira em 300s; o mixin renova aos 240s (`common/auth.py`) |
| **Regra de negócio contada como falha de carga** leva o time a caçar o problema errado | a loja aceita um Thor Hammer por carrinho, e o `CartService.php` recusa nas duas rotas (linhas 43 e 117); as duas são tratadas como resposta esperada |
| **Estado do teste divergindo do servidor** faz o teste medir o próprio defeito | `items` é um conjunto: com lista, uma duplicata sobrevivia ao `remove_item` e a operação seguinte batia em 400 |
| **Pré-carregamento falhando em silêncio** produz relatório limpo com menos requisições | um `raise` no handler de `test_start` não basta (o Locust captura e continua), então o handler chama `environment.runner.quit()` |
| **O gerador saturar antes da API** faz você medir o Locust, não o sistema | Python executa um thread por vez; se o RPS parar de subir com a CPU do processo no teto, distribua com `--processes` |

---

## Estrutura

```
locust/
├── setup.sh                 # só preparo do ambiente; não roda teste
├── locustfile.py            # entrypoint da suite
├── locustfile-comparativo.py# entrypoint do experimento pareado
├── locustfile-estoque.py    # entrypoint do teste de sobrevenda
├── locust.conf              # defaults de linha de comando
├── common/
│   ├── config.py            # hosts, credenciais, constantes
│   ├── catalog.py           # cache de ids reais carregado no test_start
│   └── auth.py              # mixin de login com renovação de token
├── scenarios/
│   ├── browse.py            # BrowseUser
│   ├── cart.py              # CartUser
│   ├── authenticated.py     # AuthenticatedUser
│   ├── comparativo.py       # ComparativoUser
│   └── estoque.py           # EstoqueUser (sobrevenda sob concorrência)
└── shapes/
    ├── degraus.py           # LoadTestShape da rampa escalonada
    └── degraus_config.py    # tabela de degraus, sem dependência do Locust
```

A suite bate direto na API (`http://localhost:8091`). A UI Angular não é
exercitada: ela serve arquivos estáticos, e o gargalo está na API.
