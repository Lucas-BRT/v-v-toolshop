# Cenários de teste — catálogo

O que cada teste exercita, quanto tempo leva e que número esperar.

**Os comandos para rodar estão em [`RUN.md`](RUN.md)**, prontos para copiar.
Este arquivo é a referência de *conteúdo*: use-o para escolher o que rodar e
para saber se um resultado estranho é achado ou ambiente quebrado.

Aprofundamento por ferramenta: `locust/APRESENTACAO.md` e
`artillery/APRESENTACAO.md`.

---

## Locust — modelo fechado

Você define **usuários simultâneos**. Cada um espera a resposta antes da
próxima ação, então a taxa de requisições se autolimita e a fila nunca
cresce. Responde *"qual é a minha capacidade?"*.

### Classes de usuário

O nome da classe vai no fim do comando; sem ele, roda a mistura por peso.

| Classe | Peso | O que exercita |
|---|---|---|
| `BrowseUser` | 6 | catálogo, busca, detalhe, relacionados, specs, filtros — leitura cacheada |
| `CartUser` | 3 | criar/ler/alterar/remover itens do carrinho — escrita, toca o banco |
| `AuthenticatedUser` | 2 | login com bcrypt, `/users/me`, favoritos, faturas |

### Configurações de carga

| Nome | Configuração | Duração | Para que serve |
|---|---|---|---|
| interface vazia | `--class-picker` | manual | carga e classe escolhidas na tela |
| smoke | 5 usuários | 30s | confere que a suite roda e a API responde |
| load | 50 usuários | 3m | carga de referência; comparar antes/depois |
| stress | 200 usuários | 5m | patamar alto sustentado; degradação e vazamento |
| rampa | degraus 10→400 | 6m | **acha o joelho da curva** |
| pareado | 150 usuários | 60s | lado fechado do experimento |
| sobrevenda | 20 usuários | 20s | **provoca corrida de estoque; falha com exit code 1** |

### Combinações que valem a pena

| O quê | Por quê |
|---|---|
| sobrevenda de estoque | **o único que encontra defeito funcional**: a API vende além do estoque |
| rampa + `AuthenticatedUser` | onde o joelho **aparece** — o login satura perto de 80 req/s |
| rampa + `CartUser` | onde o joelho **não aparece** — a escrita é barata |
| `STEP_SECONDS=20` na rampa | mesma curva em 2 minutos, bom para apresentar |

---

## Artillery — modelo aberto

Você define **chegadas por segundo**. Elas entram sendo a API capaz ou não,
então o excedente vira fila e a latência sobe sem teto. Responde *"o que
acontece quando chega mais gente do que eu atendo?"*.

São três, de propósito: cada um demonstra algo que só o Artillery faz nesta
comparação.

| Cenário | Duração | Que problema procura |
|---|---|---|
| `01-pico-de-trafego` | 105s | **o teste crítico** — formação de fila e tempo de recuperação: quanto tempo o serviço continua ruim depois que o tráfego já normalizou |
| `02-portao-ci` | 75s | deploy com regressão entrando em produção; `expect` + `ensure` com exit code |
| `03-comparativo-modelo-aberto` | 75s | confundir capacidade com resiliência; metade aberta do experimento pareado |

Rodar os três leva cerca de **4 minutos**.

---

## As duas combinações que precisam de dois terminais

### O portão de CI fechando

`02-portao-ci` sozinho passa. Para vê-lo **falhar**, dispare durante o
`01-pico-de-trafego`. Esperado: `exit=1`, p95 de ~6300 ms contra o limite de
120 ms.

### O experimento pareado

Mesma carga oferecida (150 jornadas/s), mesmas rotas, 60s. Única variável: o
modelo de carga.

| | Fechado (Locust) | Aberto (Artillery) |
|---|---|---|
| RPS entregue | 156/s, estável | 228/s aceitos, não atendidos |
| p50 ao longo do teste | **940 ms, plano** | 1901 → 6312 → … → **29445 ms** |
| Erros | 0 | 5712 timeouts (40%) |
| O que o número diz | a capacidade é ~78 jornadas/s | o usuário espera 30 s e desiste |

O pareamento das unidades é o que faz o experimento valer: o lado do Locust
usa `constant_throughput(1)`, então 150 usuários oferecem 150 jornadas/s —
o mesmo que `arrivalRate: 150` do lado do Artillery.

---

## Roteiro sugerido de apresentação

Cerca de 20 minutos de execução, sem contar a fala. Os passos 4 e 5 são
os testes críticos de cada ferramenta — se o tempo apertar, são os dois que
não podem cair. Comandos em
[`RUN.md`](RUN.md).

| # | O quê | Duração | O que dizer |
|---|---|---|---|
| 1 | `locust -l` e `head -3 scenarios/*.yml` | — | apresentar o vocabulário sem abrir código |
| 2 | Locust smoke | 30s | gráficos ao vivo; "assim é apresentar com Locust" |
| 3 | rampa + `AuthenticatedUser`, `STEP_SECONDS=20` | 2m | o joelho: RPS achata, latência assume |
| 4 | **sobrevenda de estoque** | 20s | **o teste crítico do Locust**: a API vende 100 unidades de um estoque de 25, `exit=1` |
| 5 | `01-pico-de-trafego` | 105s | **o teste crítico do Artillery**: a fila cobra depois do pico |
| 6 | pico + `02-portao-ci` em 2 terminais | 3m | `exit=1` quebra o build |
| 7 | pareado, lado fechado | 60s | p50 plano |
| 8 | pareado, lado aberto | 75s | p50 explode. Fecha a apresentação |

---

## Números de referência

Se um resultado sair muito longe destes, desconfie do ambiente antes de
desconfiar do achado. Medidos em stack local, Docker.

| Medida | Valor esperado |
|---|---|
| Capacidade do login | satura entre 60 e 100 chegadas/s |
| `/products` (cacheado) | p95 ~27 ms, estável de 8 a 80 chegadas/s |
| `02-portao-ci` (normal) | p95 ~62 ms — limite do `ensure` é 120 ms |
| `02-portao-ci` (sob pico) | p95 ~6300 ms, `exit=1` |
| rampa + `CartUser` a 400 usuários | RPS ~117, p50 16 ms, sem saturar |
| pareado fechado | RPS ~156/s, p50 ~940 ms, 0 falhas |
| pareado aberto | p50 chega a ~29 s, ~40% de timeouts |
| sobrevenda | 20 pedidos aceitos, 0 recusados, estoque 25 → **−75** após a fila |

### O spike, fase a fase

O dado mais forte da suite. A carga volta ao normal e a latência **continua
subindo** por mais ~40 s, até a fila drenar.

| fase | chegadas/s | p50 |
|---|---|---|
| linha de base | 5 | 51 ms |
| pico | 150 | 4403 ms |
| pico | 150 | 9047 ms |
| pico | 150 | 14332 ms |
| **recuperação** | **5** | **19346 ms** |
| **recuperação** | **5** | **28290 ms** + 370 timeouts |
| recuperação | 2 | 53 ms |

---

## Onde aparecem os resultados

**Só na tela.** O Artillery imprime as métricas fase a fase e no resumo
final; o Locust mostra a tabela no terminal e os gráficos ao vivo em
`http://localhost:8089`, que continua no ar depois que o teste termina.

Não há pasta de relatórios no repositório. Gravar em arquivo é opcional e
serve para comparar duas execuções — as flags estão na seção 4 do
[`RUN.md`](RUN.md).

Problemas conhecidos (conta travada, cache corrompido, porta presa):
seção 5 do [`RUN.md`](RUN.md).
