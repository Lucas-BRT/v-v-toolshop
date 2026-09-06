# Artillery — guia de apresentação

Documento de apoio para apresentar a ferramenta. O `README.md` ao lado
explica _como rodar_; este explica _o que é, por que existe e o que ela
prova_.

---

## 1. O que é

Ferramenta de teste de carga **declarativa**: o teste é um arquivo YAML, não
um programa. Roda em Node, mas escrever teste não exige escrever JavaScript.

```yaml
config:
  target: "http://localhost:8091"
  phases:
    - duration: 60
      arrivalRate: 5

scenarios:
  - flow:
      - get:
          url: "/products"
```

Três consequências práticas:

- **O teste é configuração, não código.** Legível por quem não programa,
  versionável, revisável em pull request como qualquer arquivo de infra.
- **SLA e asserções moram no mesmo arquivo.** É o que transforma o teste em
  portão de pipeline em vez de relatório para alguém ler depois.
- **Lógica complexa é desconfortável.** Quando o YAML não dá conta, você
  desce para um `processor` em JavaScript — e aí perde a vantagem.

---

## 2. O conceito central: modelo aberto

**Este é o slide mais importante da apresentação.** Tudo o que o Artillery
faz bem vem daqui.

No Artillery você configura **chegadas por segundo**, não usuários
simultâneos. A cada segundo entram N usuários virtuais novos — a API estando
dando conta ou não.

```
segundo 1: entram 150 usuários
segundo 2: entram mais 150   (mesmo que os primeiros ainda não terminaram)
segundo 3: entram mais 150   (mesmo que já haja 300 esperando)
```

**Consequências que valem dizer em voz alta:**

|                       | Modelo aberto                                                |
| --------------------- | ------------------------------------------------------------ |
| Requisições em voo    | **ilimitadas** — dependem só da chegada                      |
| Se a API desacelera   | a taxa de chegada **não muda**                               |
| Fila                  | cresce a cada segundo de déficit                             |
| Latência              | sobe **sem teto**, até estourar em timeout                   |
| Pergunta que responde | _"o que acontece quando chega mais gente do que eu atendo?"_ |

É o modelo da promoção, da citação em rede social, do link que viralizou. E
é **estruturalmente impossível** de reproduzir com uma ferramenta de modelo
fechado, onde a carga se autolimita.

---

## 3. Como está sendo usada aqui

Alvo: a API do Toolshop (`practice-software-testing`) em
`http://localhost:8091`. 15 cenários, numerados em ordem didática.

Os arquivos em `scenarios/` têm prefixo numérico só para ordenar a leitura.
Quem identifica o cenário é o nome depois dele — é ele que aparece nas
tabelas abaixo, e o arquivo correspondente está em `scenarios/`.

São **três**, de propósito. Cada um demonstra algo que só o Artillery faz
nesta comparação; escada de carga, jornada encadeada e mistura por peso ou já
são cobertas pelo Locust, ou não acrescentam argumento novo.

| Cenário | Duração | O que demonstra |
|---|---|---|
| `01-pico-de-trafego` | 105s | **o teste crítico** — `rampTo`, fila e recuperação |
| `02-portao-ci` | 75s | `expect` + `ensure` com exit code: o teste como portão |
| `03-comparativo-modelo-aberto` | 75s | metade aberta do experimento pareado com o Locust |

### Decisões que valem explicar nos slides

**Cada cenário demonstra uma coisa.** A suite já teve 15 cenários, e o
`expect` aparecia em cinco deles — a ponto de o recurso deixar de ser o
assunto de nenhum. Três cenários, três argumentos.

**Os limites do `ensure` são apertados de propósito.** Em `02-portao-ci`,
calculados como baseline medido + ~2x:

| baseline medido | limite p95 | limite p99 |
| --------------- | ---------- | ---------- |
| p95 62,2 ms     | 120 ms     | 200 ms     |

Uma versão anterior exigia p95 < 300 ms numa rota que mede 23 ms: folga de
13x, ou seja, **um portão que não tinha como fechar**. Vale como lição de
slide: _um `ensure` que não pode falhar não demonstra nada — é decoração._

**O cenário `01-pico-de-trafego` mira o login, não o catálogo.** A versão anterior batia em
`/products` e media p95 estável de ~27 ms de 8 a 80 chegadas/s, com zero
falhas. O catálogo responde do cache (`Cache-Control: max-age=120`), então o
teste media o cache e o pico era invisível. **O spike test só funciona
apontado para o que não escala.**

---

## 4. Tipos de teste que estão sendo executados

| Tipo | Cenário | O que procura |
|---|---|---|
| *spike / recovery* | `01-pico-de-trafego` | fila, e quanto tempo leva para drenar |
| *SLA gate* | `02-portao-ci` | regressão de latência barrando o deploy |
| *contract under load* | `02-portao-ci` | a resposta continua **correta** enquanto está lenta? |
| *experimento pareado* | `03-comparativo-modelo-aberto` | isolar a variável "modelo de carga" |

Repare que `02-portao-ci` aparece duas vezes: é de propósito. Juntar contrato
e SLA num run só é exatamente o que faz dele um portão — não adianta o
serviço estar rápido se a resposta está errada, nem correta se está lenta.

## 5. Que problemas esta ferramenta encontra

### Encontra bem

- **Comportamento de fila além da capacidade.** Exclusivo do modelo aberto.
- **Tempo de recuperação.** Quanto tempo o serviço continua ruim _depois_
  que o tráfego normalizou (seção 6 — é o achado mais forte da suite).
- **Regressão de SLA em pipeline.** `ensure` + exit code, sem código extra.
- **Quebra de contrato sob carga.** Um endpoint que responde rápido mas
  devolve o payload errado passa despercebido num teste de performance puro.
  O `expect` reprova.

### Não encontra bem

- **Capacidade.** O modelo aberto entope a fila; o número que sai não é o
  teto do sistema, é o sintoma do excesso. Capacidade se mede no fechado.
- **Bugs de estado de sessão longa.** `capture` encadeia passos dentro de um
  cenário, mas não há objeto de usuário vivendo o teste inteiro com lógica
  própria.
- **Qualquer coisa que precise de lógica de verdade.** Cai no `processor`
  JavaScript, e a vantagem declarativa evapora.

---

## 6. Achados reais desta suite

### O joelho está no login — e o catálogo nem se mexe

Varredura de taxa de chegada em `/users/login`:

| chegadas/s | p50     | p95     | erros                                      |
| ---------- | ------- | ------- | ------------------------------------------ |
| 60         | 66 ms   | 86 ms   | 0                                          |
| 100        | 963 ms  | 1686 ms | 0                                          |
| 200        | 6702 ms | 9230 ms | 0                                          |
| 400        | 18,2 s  | 19,7 s  | 1008 timeouts, 25 ECONNRESET, 38× HTTP 500 |

Capacidade perto de **80 req/s**. O catálogo, no mesmo intervalo, mantém p95
de ~27 ms de 8 a 80 chegadas/s: `/products` responde do cache
(`Cache-Control: max-age=120`).

É por isso que `01-pico-de-trafego` mira o login: apontado para o catálogo, o
pico media o cache e ficava invisível.

**Frase para o slide:** o bcrypt é caro **de propósito** — é assim que ele
protege senha. O problema não é ele ser lento, é ele ser a única coisa que
não escala.

### A fila continua cobrando depois que o tráfego passa

Cenário `pico-de-trafego`. A parte importante **não é o pico, é a recuperação**:

| fase            | chegadas/s | p50                         |
| --------------- | ---------- | --------------------------- |
| linha de base   | 5          | 51 ms                       |
| pico            | 150        | 4403 ms                     |
| pico            | 150        | 9047 ms                     |
| pico            | 150        | 14332 ms                    |
| **recuperação** | **5**      | **19346 ms**                |
| **recuperação** | **5**      | **28290 ms** + 370 timeouts |
| recuperação     | 2          | 53 ms                       |

A carga já tinha voltado a 5/s e a latência **continuou subindo por mais ~40
segundos**, até a fila drenar.

**Frase para o slide:** _"o site ficou fora do ar por um minuto depois que a
promoção acabou"_ — todo mundo já viu isso acontecer, e este é o gráfico que
explica por quê. Nenhuma ferramenta de modelo fechado produz esse gráfico.

### O portão realmente fecha

Rodando o cenário `portao-ci` **durante** o pico do `pico-de-trafego`:

```
14 sob pico -> exit=1
p95 6312 ms (limite 120)   p99 7407 ms (limite 200)
```

Exit code 1 quebra o build. É a demonstração de que o `ensure` não é
enfeite. Comando na seção 8.

### A conta de cliente trava após 3 logins inválidos

Achado da investigação, medido antes de a suite ser enxugada para três
cenários: **3× HTTP 401, depois 7× HTTP 423**. Não há mais um cenário
dedicado a isso, mas o achado continua valendo o slide.

Dois desdobramentos, e os dois rendem slide:

**Achado de segurança.** A proteção contra força bruta **não cobre a conta
de admin**. `UserService::login` (linhas 61 e 70) pula tanto a checagem de
bloqueio quanto o `incrementLoginAttempts` quando `role == "admin"`.
Justamente a conta mais valiosa fica sem proteção.

**Achado de testabilidade.** Não dá para medir o custo do caminho de erro
sob carga sem que a própria proteção corrompa o teste. A distribuição
401/423 no relatório **é** o resultado.

Nota metodológica que vale contar: uma versão anterior deste cenário usava o
admin justamente para não travar nada. Só que isso media um caminho **mais
barato** do que o de produção — sem a checagem e sem o UPDATE no banco.
O número saía otimista e a conclusão, errada. Lição: _escolher o dado de
teste que não quebra o ambiente pode silenciosamente medir outra coisa._

### Sobrecarga sustentada corrompe o cache em arquivo do Laravel

Depois da varredura a 400 chegadas/s, `/products` e `/categories/tree`
passaram a devolver **HTTP 500 permanente**:

```
file_put_contents(/var/www/storage/framework/cache/data/99/08/...):
Failed to open stream: Permission denied
```

O `POST /refresh` (o `./setup.sh reset`) **não conserta** — ele
recria o banco, não o cache em disco. Reparo:

```bash
docker compose exec -u root laravel-api \
  chown -R www-data:www-data storage/framework/cache
```

**Frase para o slide:** a aplicação não se recupera sozinha de uma
sobrecarga, e o procedimento de reset documentado não cobre o estado que
quebra. Isso é um achado operacional legítimo, encontrado por acidente — e
teste de carga costuma achar coisa assim.

---

## 7. Pontos fortes e fracos — sem maquiar

### Fortes

- **Modelo aberto.** O recurso decisivo; nada mais nesta comparação faz isso.
- **SLA no arquivo de teste.** `ensure` + exit code = portão de CI sem cola.
- **Contrato durante a carga.** `expect` junta teste funcional e de
  performance num run só.
- **Data-driven sem código.** `payload` lê CSV direto.
- **Fases expressivas.** `rampTo`, degraus e pesos, tudo declarativo.
- **Legível por não-programador.** YAML revisável em pull request.

### Fracos

- **Não gera relatório HTML.** O subcomando `artillery report` virou
  **no-op na versão 2.x**; a saída gráfica passou a ser exclusiva do
  Artillery Cloud, serviço pago e externo. Sobra o resumo do terminal e o
  JSON. O Locust entrega `--html` nativo.

- **Não mede capacidade.** O número que sai da fila não é o teto do sistema.
- **Sem estado de usuário rico.** `capture` encadeia; não simula sessão com
  lógica.
- **Lógica de verdade exige JavaScript.** No `processor`, e aí a vantagem
  declarativa acaba.
- **Precisa de timeout generoso.** Com `http.timeout` curto a fila vira
  "erro de rede" no relatório em vez de latência — e a latência era o dado.

---

## 8. Roteiro de demonstração

Pré-requisito: `cd ../practice-software-testing && docker compose up -d`

Os comandos completos estão em [`../RUN.md`](../RUN.md).

**Passo 0 — preparo** (uma vez, antes da apresentação)

```bash
cd artillery && ./setup.sh
```

**Passo 1 — mostrar o catálogo de cenários** (5s)

```bash
head -3 scenarios/*.yml
```

A primeira linha de comentário de cada YAML descreve o cenário. Introduz o
vocabulário sem abrir código.

**Passo 2 — o spike** (~2 min) — **o teste crítico**

```bash
npx artillery run scenarios/01-pico-de-trafego.yml
```
Narrar durante a execução: *"a carga já voltou ao normal... e olhem a
latência ainda subindo."* Números esperados na seção 6.

**Passo 3 — o portão fechando** (~3 min)

Dois terminais:

```bash
# terminal 1: pico no login
npx artillery run scenarios/01-pico-de-trafego.yml

# terminal 2: dispare durante o pico
npx artillery run scenarios/02-portao-ci.yml ; echo "exit=$?"
```
Terminar mostrando o `exit=1`. Build quebrado por latência, sem uma linha de
código.

**Passo 4 — o experimento pareado** (~1 min)

```bash
npx artillery run scenarios/03-comparativo-modelo-aberto.yml
```

Comparar com o lado fechado do Locust (`locustfile-comparativo.py`). Fecha a
apresentação com a tabela da seção 9.

---

## 9. O experimento pareado — o slide de encerramento

O cenário `comparativo-modelo-aberto` (aqui) e o `locustfile-comparativo.py`
(Locust) aplicam **a mesma carga
oferecida**, nas **mesmas rotas**, pela **mesma duração**. Única variável: o
modelo.

O pareamento das unidades é o detalhe que faz o experimento valer. Artillery
configura chegadas/s; Locust configura usuários simultâneos. Comparar "150
chegadas/s" com "150 usuários" seria comparar coisas diferentes. O ajuste
está no `constant_throughput(1)` do lado do Locust: 150 usuários tentando 1
jornada/s cada oferecem 150 jornadas/s — o mesmo que `arrivalRate: 150`.

Jornada = `POST /users/login` + `GET /users/me`. 60 segundos. Capacidade da
API ≈ 80 jornadas/s, então os dois recebem quase o dobro do que aguentam.

|                       | Fechado (Locust)              | Aberto (Artillery)                                 |
| --------------------- | ----------------------------- | -------------------------------------------------- |
| RPS entregue          | **156/s, estável**            | 228/s aceitos, não atendidos                       |
| p50 ao longo do teste | **940 ms, plano**             | 1901 → 6312 → 11050 → 15839 → 20958 → **29445 ms** |
| p95                   | 1500 ms, plano                | 29445 ms                                           |
| Erros                 | **0**                         | 5712 timeouts (40% das requisições)                |
| O que o número diz    | a capacidade é ~78 jornadas/s | o usuário espera 30 s e desiste                    |

**Mesma carga. Mesmas rotas. Mesmo tempo. Resultados opostos.**

Nenhum dos dois está errado, e nenhum substitui o outro:

- o **fechado** responde _"qual é a minha capacidade"_ → dimensionamento;
- o **aberto** responde _"o que o usuário sente quando ela é ultrapassada"_
  → resiliência.

Um time que só roda o fechado dimensiona bem e é surpreendido pela primeira
promoção. Um time que só roda o aberto sabe que quebra, mas não sabe onde
começar a otimizar.

---

## 10. Perguntas prováveis

**"Modelo aberto não é irreal? Usuário de verdade desiste."**
Boa objeção, e a resposta está no gráfico do `pico-de-trafego`: a latência bate
30 s e vira timeout — que **é** o usuário desistindo. O modelo aberto não
finge que ninguém desiste; ele mostra a fila que se forma antes disso. Para
modelar desistência explícita, existem ferramentas com esse recurso.

**"Por que não medir tudo com uma ferramenta só?"**
Porque a escolha do modelo é uma decisão de projeto, não um detalhe de
implementação, e nenhuma das duas faz as duas coisas bem. A seção 9 é
exatamente a prova disso.

**"Esses milissegundos valem alguma coisa? É Docker num notebook."**
Os números absolutos, não. O que vale é a **forma da curva** e a
**comparação relativa** — catálogo plano contra login saturando, fechado
plano contra aberto explodindo. Isso se mantém em qualquer hardware; só o
eixo muda de escala.

**"400 chegadas/s quebrou a aplicação. Não é excesso?"**
Foi de propósito: era a varredura para achar o joelho. E o resultado gerou o
achado do cache corrompido (seção 6), que só aparece quando você passa do
ponto.
