# Artillery

Ferramenta de teste de carga **declarativa**: o teste é um arquivo YAML, não
um programa. Roda em Node, mas escrever teste não exige escrever JavaScript.

Comandos para executar: [`../RUN.md`](../RUN.md).
Catálogo com durações e números esperados: [`../CENÁRIOS_DE_TESTE.md`](../CENÁRIOS_DE_TESTE.md).
Material de apresentação: [`APRESENTACAO.md`](APRESENTACAO.md).

---

## Para que serve

Responder **"o que acontece quando chega mais gente do que eu consigo
atender?"** — e transformar requisito de desempenho em portão automático de
pipeline.

A resposta vem do **modelo aberto**, que é a decisão de projeto da qual tudo
o mais decorre. Você configura chegadas por segundo, não usuários
simultâneos:

```
segundo 1: entram 150 usuários
segundo 2: entram mais 150   (mesmo que os primeiros não tenham terminado)
segundo 3: entram mais 150   (mesmo que já haja 300 esperando)
```

| | Consequência |
|---|---|
| Se a API desacelera | a taxa de chegada **não muda** |
| Fila | cresce a cada segundo de déficit |
| Latência | sobe **sem teto**, até estourar em timeout |
| O número que sai | é **o que o usuário sente** quando a capacidade é ultrapassada |

É o modelo da promoção, da citação em rede social, do link que viralizou.
Uma ferramenta de modelo fechado não consegue reproduzir isso: lá a carga se
autolimita e a fila nunca se forma.

O segundo eixo é o **teste como configuração**. SLA e asserções moram no
mesmo arquivo do cenário, então o teste devolve exit code e serve de portão
de deploy sem cola nenhuma em volta.

---

## Que problemas esta ferramenta procura

### Encontra

| Problema | Como aparece |
|---|---|
| **Formação de fila além da capacidade** | latência crescendo enquanto a taxa de chegada fica constante |
| **Tempo de recuperação** | o serviço continua ruim depois que o tráfego já normalizou |
| **Regressão de SLA entre releases** | `ensure` compara percentis e devolve exit code `!= 0` |
| **Quebra de contrato sob carga** | `expect` reprova resposta rápida com payload errado — um teste de performance puro deixaria passar |
| **Colapso: onde vira erro em vez de lentidão** | timeouts, ECONNRESET e HTTP 500 aparecem quando a fila estoura |

### Não encontra bem

| Problema | Por quê |
|---|---|
| **Capacidade do sistema** | o modelo aberto entope a fila; o número que sai é sintoma do excesso, não o teto |
| **Defeito de sessão longa** | `capture` encadeia passos dentro de um cenário, mas não há objeto de usuário vivendo o teste inteiro com lógica própria |
| **Qualquer coisa com lógica de verdade** | cai no `processor` JavaScript, e a vantagem declarativa evapora |

Essas lacunas são o que a suite `../locust` cobre.

---

## Os casos de teste

São três, de propósito. Cada um demonstra uma coisa que **só** o Artillery
faz nesta comparação; o resto do que a ferramenta oferece (escada de carga,
jornada encadeada, mistura por peso) ou já é coberto pelo Locust, ou não
acrescenta argumento novo.

### `01-pico-de-trafego` — o teste crítico

Spike no login: 5 chegadas/s de base, subida abrupta para 150, pico
sustentado, e volta ao normal.

**Que problema procura:** *formação de fila e tempo de recuperação.* O que
acontece quando a demanda passa a capacidade de repente — e, principalmente,
quanto tempo o serviço continua ruim **depois** que o tráfego já voltou ao
normal. É a metade da história que o modelo fechado não consegue contar.

Mira o login porque `/products` responde do cache (`max-age=120`): apontado
para o catálogo, o pico media o cache e ficava invisível. O spike só funciona
apontado para o que não escala.

Não declara `ensure`: deve terminar com métricas ruins, e esse é o resultado
esperado.

### `02-portao-ci` — o portão de deploy

Mistura de catálogo e autenticação, com `expect` validando as respostas e
`ensure` comparando percentis e taxa de erro contra o SLA.

**Que problema procura:** *deploy com regressão entrando em produção.* Junta
as duas coisas que um portão precisa — a resposta continua **correta** sob
carga, e continua **rápida** o bastante — e devolve exit code `!= 0` quando
qualquer limite estoura. É o cenário que mostra o teste como configuração:
o requisito mora no arquivo, não num script em volta.

Os limites são apertados de propósito (p95 120 ms sobre um baseline de
~62 ms). Para vê-lo fechar, dispare-o durante o `01-pico-de-trafego`.

### `03-comparativo-modelo-aberto` — a metade aberta do experimento

Jornada de login + leitura autenticada, a 150 chegadas/s.

**Que problema procura:** *confundir capacidade com resiliência.* É metade
de um experimento cuja outra metade é `../locust/locustfile-comparativo.py`.
Mesma carga oferecida, mesmas rotas, mesma duração — só o modelo muda. Existe
para mostrar, lado a lado, que os dois números respondem perguntas diferentes
e que nenhum substitui o outro.

## Decisões que afetam a validade da medição

| Decisão | Por quê |
|---|---|
| **O spike mira o login, não o catálogo** | `/products` responde do cache (`max-age=120`); apontado para lá, o pico media o cache e ficava invisível. O spike só funciona apontado para o que não escala |
| **Os limites do `ensure` são apertados** | calculados como baseline medido + ~2x. Um limite 13x acima da realidade é um portão que não tem como fechar, e não demonstra nada |
| **O spike usa a conta de admin** | o cliente trava após 3 logins inválidos (HTTP 423) e o admin é isento dessa checagem (`UserService::login`, linhas 61 e 70). Como aqui os logins são válidos, o bloqueio não entra em jogo — mas a conta de admin garante que uma rajada não suje o estado |
| **Timeout generoso no spike** | com timeout curto a fila vira "erro de rede" no relatório em vez de latência, e a latência era justamente o dado |
| **Fases sustentadas de 60s** | fases de 10s não alcançam regime permanente: opcache, pool de conexão e cache ainda aquecendo. Um p95 tirado de ~170 requisições é ruído |

---

## O ponto fraco que fica exposto de propósito

**Não há relatório HTML.** O subcomando `artillery report` foi
descontinuado na versão 2.x — é a própria ferramenta quem avisa:

```
$ npx artillery report
┌───────────────────────────────────────────────────────────────────────┐
|  The "report" command has been deprecated and is no longer supported  |
|                                                                       |
|  You can use Artillery Cloud (https://app.artillery.io) to visualize  |
|  test results, create custom reports, and share them with your team.  |
└───────────────────────────────────────────────────────────────────────┘
```

A saída gráfica passou a ser exclusiva do Artillery Cloud, serviço externo.
Sobra o resumo do terminal — que é onde as métricas são lidas — e,
opcionalmente, o JSON do `--output`.

Uma versão anterior desta pasta tinha um `tools/relatorio.py` que gerava o
HTML por conta própria a partir do JSON. Ele foi **removido**: como o
objetivo do repositório é comparar as ferramentas honestamente, escrever
código para tapar a lacuna de uma delas falsifica a comparação. O Locust
entrega `--html` nativo; o Artillery 2.x não entrega. Essa é a diferença, e
ela precisa aparecer.

---

## Estrutura

```
artillery/
├── setup.sh                # só preparo do ambiente e reset; não roda teste
├── package.json
└── scenarios/
    ├── 01-pico-de-trafego.yml            # o teste crítico
    ├── 02-portao-ci.yml                  # portão de deploy
    └── 03-comparativo-modelo-aberto.yml  # metade aberta do experimento
```

Tudo é YAML — não há uma linha de código de teste nesta pasta. É a diferença
mais visível em relação à `../locust`, onde o teste é Python.
