# Locust — guia de apresentação

Documento de apoio para apresentar a ferramenta. O `README.md` ao lado
explica *como rodar*; este explica *o que é, por que existe e o que ela
prova*.

---

## 1. O que é

Ferramenta de teste de carga **escrita em Python, onde o teste também é
Python**. Não há DSL, nem YAML, nem gravador de tráfego: um usuário virtual
é uma classe, e cada ação dele é um método decorado com `@task`.

```python
class BrowseUser(HttpUser):
    weight = 6
    wait_time = between(1, 4)

    @task(10)
    def list_products(self):
        self.client.get("/products?page=1")
```

Três consequências práticas dessa escolha:

- **Estado por usuário virtual é trivial.** O objeto vive durante todo o
  teste, então ele guarda carrinho, token, histórico — como uma sessão real.
- **Qualquer lógica cabe.** `if`, `try`, biblioteca externa, leitura de
  banco. Nada precisa ser previsto pela ferramenta.
- **Você escreve código de verdade.** Com todos os bugs que isso implica —
  dois deles aparecem na seção 7.

---

## 2. O conceito central: modelo fechado

**Este é o slide mais importante da apresentação.** Tudo o que o Locust faz
bem e tudo o que ele não consegue fazer vem daqui.

No Locust você configura **usuários simultâneos**, não requisições por
segundo. Cada usuário virtual é um laço:

```
faz requisição → ESPERA A RESPOSTA → pensa um pouco → repete
```

O "espera a resposta" é a peça toda. Se a API fica lenta, o usuário
simplesmente demora mais para dar a volta no laço. Ninguém empurra
requisições novas enquanto isso.

**Consequências que valem dizer em voz alta:**

| | Modelo fechado |
|---|---|
| Requisições em voo | no máximo N (o número de usuários) |
| Se a API desacelera | a taxa de requisições **cai sozinha** |
| Fila | não se forma — não há como |
| Latência | encontra um teto |
| Pergunta que responde | *"qual é a minha capacidade?"* |

É o modelo certo para medir capacidade, e é **estruturalmente incapaz** de
simular uma promoção ou uma citação viral, onde a gente chega
independentemente de você conseguir atender. Essa metade é do Artillery.

---

## 3. Como está sendo usada aqui

Alvo: a API do Toolshop (`practice-software-testing`) em
`http://localhost:8091`. A UI Angular não é exercitada — ela só serve
arquivos estáticos, o gargalo está na API.

### Três perfis de usuário, com peso

| Classe | Peso | O que faz | Por que existe |
|---|---|---|---|
| `BrowseUser` | 6 | catálogo, busca, detalhe, relacionados, specs, filtros | maior volume de uma loja real; leitura cacheada |
| `CartUser` | 3 | cria carrinho, adiciona, altera quantidade, remove, descarta | caminho de **escrita**, toca o banco |
| `AuthenticatedUser` | 2 | login, `/users/me`, favoritos, faturas, relogin | custo do **bcrypt** e das rotas com JWT |

Os pesos (6/3/2) aproximam o tráfego de uma loja: muita leitura anônima,
menos escrita, minoria autenticada.

### Decisões que valem explicar nos slides

**Catálogo pré-carregado** (`common/catalog.py`). Os ids reais de produto,
categoria e marca são buscados **uma vez**, no `test_start`. Se cada task
descobrisse o id na hora, toda ação custaria uma requisição extra e as
métricas ficariam infladas — você estaria medindo o teste, não a API.

**Nomes de request agrupados.** Rotas com id usam
`name="GET /products/{id}"`. Sem isso o relatório vira uma linha por id e
não há percentil que faça sentido.

**Token renovado sozinho** (`common/auth.py`). O JWT expira em 300s; o mixin
renova aos 240s. Num teste de 5 minutos, sem isso, metade das requisições
autenticadas viraria 401 e o relatório culparia a API.

**Falha no pré-carregamento encerra o teste.** Detalhe não óbvio e ótimo
para slide: um `raise` no handler de `test_start` **não basta** — o Locust
captura, registra e continua. O teste seguiria com o catálogo vazio, as
tasks fariam `return` cedo, e o relatório sairia com menos requisições e
**zero falhas**: um resultado bonito e completamente falso. Por isso o
handler chama `environment.runner.quit()`.

---

## 4. Tipos de teste que estão sendo executados

| Perfil | Tipo | Configuração | O que procura |
|---|---|---|---|
| `smoke` | *smoke test* | 5u / 30s | a suite roda? a API responde? — não mede nada |
| `load` | *load test* | 50u / 3m | comportamento na carga esperada; base de comparação antes/depois |
| `stress` | *stress test* | 200u / 5m | degradação e vazamento sob patamar alto sustentado |
| `ramp` | *capacity test* | degraus 10→400 | **o joelho da curva** — a capacidade real |
| `comp` | *experimento pareado* | 150u / 60s | isolar a diferença entre modelo aberto e fechado |

### A rampa escalonada é o diferencial

`--users` define **um** patamar. Para varrer vários na mesma execução — com
o mesmo processo, o mesmo pool de conexões e o mesmo estado de usuário
virtual — é preciso uma `LoadTestShape` (`shapes/degraus.py`).

**Como se lê o gráfico** (vale desenhar no slide):

```
RPS  ^                    ___________   <- achatou: este é o teto
     |               ____/
     |          ____/
     |     ____/
     +----------------------------> usuários

p95  ^                        /
     |                    ___/          <- começa a subir aqui
     |  _________________/
     +----------------------------> usuários
```

Enquanto há folga, dobrar os usuários dobra o RPS e a latência quase não se
move. **O joelho é onde o RPS achata e a latência assume o crescimento.**
Esse teto é a capacidade.

Detalhe de implementação que costuma ser perguntado: a shape é carregada à
parte (`-f locustfile.py,shapes/degraus.py`) porque uma `LoadTestShape`
presente no locustfile **assume o controle** e passa a ignorar `--users` e
`--run-time`, o que quebraria os perfis de patamar fixo.

---

## 5. O teste crítico

Entre os cinco tipos acima, um se destaca: **é o único que encontra um
defeito funcional, e o único cuja carga não é o objeto da medição, mas o
instrumento.**

### `EstoqueUser` — sobrevenda sob concorrência

Vários clientes compram o **mesmo** produto na mesma janela de tempo,
somando mais unidades do que existem em estoque. A pergunta não é "quanto
tempo demora", é **"a aplicação recusa o excedente?"**.

```bash
locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --headless
echo "exit=$?"
```

### O resultado

```
estoque inicial ................ 25
unidades aceitas em pedidos .... 100
pedidos aceitos / recusados .... 20 / 0
```

Nenhum pedido recusado: **sobrevenda de 75 unidades**. Processando a fila de
jobs em seguida, o estoque do produto foi para **−75** — exatamente o
excedente que o teste previu.

### Por que ele é o crítico

| | O resto da suite | Este teste |
|---|---|---|
| Mede | tempo de resposta, vazão | **correção de uma regra de negócio** |
| A carga é | o objeto da medição | o **instrumento** que cria a condição |
| Falha quando | o percentil passa de um limite | a API **vende o que não tem** |
| Severidade | degradação: o cliente espera | **prejuízo: o pedido não pode ser cumprido** |

Um teste funcional compra uma vez, recebe `200 OK` e passa. O defeito só tem
consequência quando muita gente compra o mesmo item ao mesmo tempo — que é a
definição de uma promoção. É por isso que ele precisa de uma ferramenta de
carga para aparecer.

### O oráculo

Compara **unidades aceitas em pedidos** com o **estoque inicial**, lido pela
API com token de admin (só o admin enxerga o número; para os demais
`in_stock` vem como booleano).

O critério **não depende de o estoque ser debitado** — aceitar o pedido já é
o defeito. Um `422` recusando por falta de estoque é contado como *sucesso*:
é o comportamento correto, e é justamente o que não acontece.

O teste sai com **exit code 1** quando detecta sobrevenda, então serve de
portão de pipeline tanto quanto os cenários `ensure` do Artillery — com a
diferença de que aqui o portão é sobre correção, não sobre latência.

As causas no código estão na seção 7.

---

## 6. Que problemas esta ferramenta encontra

### Encontra bem

- **Capacidade** — quantos usuários simultâneos antes de degradar.
- **Bugs que dependem de estado de sessão.** Carrinho perdido, token
  expirado no meio, sequência inválida de operações. Um teste sem estado
  não chega perto disso.
- **Regras de negócio disparadas sob carga.** Precisam de código para serem
  tratadas corretamente (seção 7).
- **Degradação lenta.** Patamar alto e sustentado revela vazamento de
  memória, pool de conexões esgotando, cache envenenando.

### Não encontra — por construção

- **Comportamento de fila.** Impossível no modelo fechado. É a razão de o
  Artillery existir neste repositório.
- **Regressão de SLA em pipeline.** O Locust tem `--exit-code-on-error`, que
  reage a *erros*, não a *latência*. Não há `assert p95 < 200ms` pronto —
  daria para escrever um listener de `test_stop`, mas é código seu, não
  recurso da ferramenta.
- **Quebra de contrato sob carga.** `catch_response` permite validar corpo
  de resposta, mas é manual. Não existe um "valide este schema" declarativo.

---

## 7. Achados reais desta suite

### O carrinho não é o gargalo

`ramp cart`, degraus até 400 usuários:

| usuários | RPS | p50 | p95 | falhas |
|---|---|---|---|---|
| 50 | 14,5 | 15 ms | 35 ms | 0 |
| 100 | 29,8 | 15 ms | 44 ms | 0 |
| 200 | 59,2 | 16 ms | 82 ms | 0 |
| 400 | 117,0 | 16 ms | 160 ms | 0 |

O RPS continua dobrando junto com os usuários e o p50 fica **cravado em 16
ms**. Não há joelho: a escrita no carrinho é barata. O gargalo é o login,
onde o bcrypt satura perto de 80 req/s.

Conclusão para o slide: **a intuição estava errada.** "Escrita no banco é o
gargalo" é o palpite natural, e o teste mostra o contrário — quem trava é a
CPU do hash de senha, não o disco.

### Por que a loja vende o que não tem

O resultado do teste crítico está na [seção 5](#5-o-teste-crítico). Aqui
ficam as causas no código — são três, e vale mostrar as três.

**1. Não existe checagem de estoque no fluxo de compra.** O `CartService`
valida a regra do Thor Hammer e o teto de 99 unidades por requisição, mas
nunca o estoque. O `InvoiceService` monta a fatura sem consultar
`products.stock`.

**2. O débito não tem guarda.** Em `App\Jobs\UpdateProductInventory`:

```php
$product = Product::where('id', $this->productId)->first();
$product->decrement('stock', $this->quantity);
```

Sem `where('stock', '>=', $quantity)`, sem transação, sem lock.

Nuance que vale dizer em voz alta, porque a plateia técnica vai perguntar:
o `decrement` gera `UPDATE ... SET stock = stock - N`, que é **atômico no
SQL**. Então isto **não é um lost update** — os débitos concorrentes não se
sobrescrevem. O defeito é a ausência de qualquer validação antes deles; a
concorrência só torna o problema trivial de provocar.

**3. O defeito fica escondido.** O job é enfileirado
(`QUEUE_CONNECTION=database`) e o `docker-compose` não sobe worker nenhum.
Os débitos se acumulam na tabela `jobs` e o estoque parece intacto — quem
auditar só o banco não vê nada de errado. Para revelar:

```bash
docker compose exec laravel-api php artisan queue:work --stop-when-empty
```

### Dois bugs no próprio teste — e por que isso é conteúdo bom

Os dois vinham de escrever código de verdade, que é justamente o preço do
modelo do Locust.

**1. Regra de negócio tratada em um lugar só.** A loja aceita no máximo um
Thor Hammer por carrinho. O `CartService.php` recusa nas **duas** rotas: no
`POST /carts/{id}` (linha 43) e no `PUT .../product/quantity` (linha 117).
O teste tratava só a primeira. Resultado: **7 falhas em 2630 requisições**
que não eram falhas de carga, e sim a aplicação funcionando corretamente.

Lição: **um teste de carga que reporta erro de regra de negócio como falha
de performance leva o time a caçar o problema errado.**

**2. Estado divergindo da realidade.** A lista de itens do carrinho era uma
`list`. Sortear o mesmo produto duas vezes empilhava uma duplicata; o
`remove_item` seguinte apagava o item da API e deixava a cópia na lista; o
`update_quantity` depois batia em 400 num produto que não existia mais.

Lição: **o estado do usuário virtual precisa espelhar o estado do servidor,
ou o teste começa a testar o próprio bug.** Virou `set`.

### O gerador pode ser o gargalo

Python executa um thread por vez. Em carga alta, o limite pode ser o
**Locust**, não a API — e o relatório não avisa. Se o RPS parar de subir mas
a CPU do processo estiver no teto, distribua:

```bash
locust -f locustfile.py,shapes/degraus.py --headless --processes 4 CartUser
```

Vale conferir isso **antes** de concluir que a API saturou. O Locust também
tem `--master` / `--worker` para distribuir entre máquinas. Nota honesta:
`--processes` é marcado como *Experimental* na saída do `--help`.

---

## 8. Pontos fortes e fracos — sem maquiar

### Fortes

- **Estado por usuário virtual sem esforço.** É o recurso decisivo.
- **Poder total do Python.** Qualquer lógica, qualquer biblioteca.
- **Interface web ao vivo.** Gráficos de RPS, latência e usuários ativos
  enquanto o teste roda. Excelente para apresentar.
- **Relatório HTML nativo** (`--html`), offline, sem serviço externo.
- **Distribuição embutida** — `--processes` e `--master`/`--worker`.
- **Modelo fechado é o certo para medir capacidade.**

### Fracos

- **Nenhum portão de SLA pronto.** Sem `assert p95 < X` declarativo.
- **Modelo aberto impossível.** Não simula fila, nem pico, nem recuperação.
- **Tudo é código.** Mais poder e mais superfície para bug — como os dois
  acima.
- **Limite do processo Python.** Exige atenção ao gerador em carga alta.
- **Validação de contrato é manual.** Não há plugin declarativo de schema.

---

## 9. Roteiro de demonstração

Pré-requisito: `cd ../practice-software-testing && docker compose up -d`

Os comandos completos estão em [`../RUN.md`](../RUN.md).

**Passo 0 — preparo** (uma vez, antes da apresentação)

```bash
cd locust && ./setup.sh && source .venv/bin/activate
```

**Passo 1 — mostrar as classes** (5s)

```bash
locust -l                  # BrowseUser, CartUser, AuthenticatedUser
locust --show-task-ratio   # a proporção entre as tasks de cada uma
```
Introduz o vocabulário sem abrir código, e o `--show-task-ratio` já explica
os pesos 6/3/2.

**Passo 2 — smoke com interface ao vivo** (~40s)

```bash
locust --users 5 --run-time 30s --autostart
```
Abrir `http://localhost:8089`. Mostrar os gráficos se desenhando. É o
momento "olha que bonito" — e o argumento honesto de apresentabilidade.

**Passo 3 — o joelho da curva** (~6 min, ou `STEP_SECONDS=20` para ~2 min)

```bash
STEP_SECONDS=20 locust -f locustfile.py,shapes/degraus.py --autostart AuthenticatedUser
```
Deixar na aba de gráficos. Narrar: *"cada degrau dobra os usuários; olhem o
RPS achatando enquanto a latência assume o crescimento — ali é a
capacidade."* O `auth` satura; o `cart` não.

**Passo 4 — o teste crítico** (~20s) — **o momento alto**

```bash
locust -f locustfile-estoque.py --users 20 --spawn-rate 20 --run-time 20s --headless
echo "exit=$?"
```

O veredito sai no log, no fim. Narrar: *"20 clientes, 5 unidades cada, contra
um estoque de 25. Nenhum pedido recusado."* Terminar mostrando o `exit=1`.

Para fechar o argumento, processe a fila e mostre o estoque negativo:

```bash
cd ../practice-software-testing
docker compose exec laravel-api php artisan queue:work --stop-when-empty
```

**Passo 5 — o experimento pareado** (~1 min)

```bash
locust -f locustfile-comparativo.py --users 150 --spawn-rate 150 --run-time 60s --headless
```
Guardar o número: **RPS estabiliza em ~156/s, p50 plano em 940 ms, zero
falhas.** Em seguida rodar o lado aberto no Artillery e comparar. Esse par
é o encerramento natural da apresentação.

---

## 10. Perguntas prováveis

**"Por que não usar JMeter / k6?"**
Recorte diferente. JMeter é GUI e XML; k6 é JavaScript e também fechado por
padrão. O ponto aqui não é eleger a melhor ferramenta, é mostrar que
**modelo de carga** é uma decisão de projeto, e que fechado e aberto
respondem perguntas diferentes.

**"150 usuários é pouco."**
É, para produção. O objetivo aqui é **achar o joelho**, e nesta stack ele
aparece bem antes disso. Número absoluto de usuários só significa alguma
coisa junto com o hardware.

**"O teste não bate na interface. Não deveria?"**
A UI Angular serve arquivos estáticos; o custo está na API. Testar carga
pelo navegador mediria renderização, não backend. Para jornada real de
navegador a ferramenta seria outra (Playwright, Selenium) e o objetivo
também.

**"Zero falhas significa que está tudo bem?"**
Não. Significa que nada quebrou **naquela carga**. E, como a seção 3 mostra,
um relatório limpo pode inclusive indicar que o teste não rodou de verdade.
