"""Carga pareada com o cenario `comparativo-modelo-aberto` do Artillery.

Lado FECHADO do experimento.

Este arquivo e metade de um experimento. A outra metade e
`../artillery/scenarios/03-comparativo-modelo-aberto.yml`. Os dois aplicam
EXATAMENTE a mesma carga oferecida sobre EXATAMENTE as mesmas rotas, pela
mesma duracao. A unica diferenca e o modelo de carga.

O que e "a mesma carga oferecida"
---------------------------------
As duas ferramentas medem coisas com unidades diferentes: o Artillery
configura chegadas por segundo, o Locust configura usuarios simultaneos.
Comparar "150 chegadas/s" com "150 usuarios" seria comparar unidades
distintas e a demonstracao nao provaria nada.

O ajuste esta no `constant_throughput(1)`: cada usuario virtual tenta
executar 1 jornada por segundo. Com 150 usuarios, a carga OFERECIDA e de
150 jornadas/s — o mesmo numero que o Artillery oferece com
`arrivalRate: 150`. Agora as duas pontas partem do mesmo pedido.

O que observar
--------------
A jornada faz um login (bcrypt, nao cacheavel) e uma leitura autenticada.
A API satura o login perto de 80 req/s, entao 150 jornadas/s e quase o
dobro da capacidade. Sob esse mesmo excesso:

  MODELO FECHADO (aqui)
    Cada usuario espera a resposta antes da proxima jornada. Se a API
    demora, o usuario simplesmente demora tambem — e a taxa real cai
    sozinha. O `constant_throughput` pede 150/s, mas a suite entrega o que
    a API consegue absorver. O RPS achata num teto e o tempo de resposta
    para de crescer. Nao ha fila: existem 150 requisicoes em voo no maximo,
    porque existem 150 usuarios.

  MODELO ABERTO (Artillery, cenario `comparativo-modelo-aberto`)
    As 150 chegadas/s entram sendo a API capaz ou nao. O excedente vira
    fila, a fila cresce a cada segundo e o tempo de resposta sobe sem teto
    ate estourar em timeout.

Conclusao pratica: o numero do modelo fechado responde "qual e a minha
capacidade"; o do modelo aberto responde "o que o usuario sente quando a
demanda passa da capacidade". Nenhum dos dois substitui o outro.

Uso
---
    locust -f locustfile-comparativo.py \
           --users 150 --spawn-rate 150 --run-time 60s --headless
"""

from locust import HttpUser, constant_throughput, task

from common import config

# Contas isentas do bloqueio por tentativas invalidas (UserService::login
# checa role != "admin"), entao a carga repetida nao suja o estado.
EMAIL = "admin@practicesoftwaretesting.com"
SENHA = "welcome01"

# Jornadas por segundo que CADA usuario virtual tenta executar. Multiplicado
# pelo numero de usuarios, da a carga oferecida total.
JORNADAS_POR_USUARIO = 1


class ComparativoUser(HttpUser):
    """Jornada identica a do `comparativo-modelo-aberto` do Artillery."""

    host = config.API_HOST

    # A peca central do experimento: fixa a carga OFERECIDA por usuario, o
    # que torna o numero comparavel com o arrivalRate do Artillery. Com
    # between()/constant() a carga oferecida dependeria do tempo de resposta
    # da propria API, e nao haveria como parear os dois lados.
    wait_time = constant_throughput(JORNADAS_POR_USUARIO)

    @task
    def jornada(self):
        with self.client.post(
            "/users/login",
            json={"email": EMAIL, "password": SENHA},
            name="POST /users/login",
            catch_response=True,
        ) as resposta:
            if resposta.status_code != 200:
                resposta.failure(f"login falhou: HTTP {resposta.status_code}")
                return
            token = resposta.json().get("access_token")
            if not token:
                resposta.failure("login sem access_token")
                return
            resposta.success()

        self.client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
            name="GET /users/me",
        )
