"""Rampa escalonada — o recurso que so o modelo fechado oferece.

Este arquivo existe para responder a pergunta que o Locust responde melhor
que o Artillery: *quantos usuarios simultaneos a API aguenta antes de
degradar?*

Como se le o resultado
----------------------
A cada degrau o numero de usuarios simultaneos sobe e o degrau e mantido
tempo suficiente para estabilizar. Enquanto a API tem folga, dobrar os
usuarios dobra o RPS e o tempo de resposta quase nao muda. A partir do
joelho da curva o RPS para de subir e o tempo de resposta passa a crescer
no lugar dele — o sistema saturou.

Esse formato de grafico (RPS achatando enquanto a latencia sobe) e o que
identifica a capacidade. Ele nao aparece no modelo aberto do Artillery, onde
a fila cresce sem limite e a latencia dispara direto para segundos.

Por que nao da para fazer isso com --users
------------------------------------------
`--users` e `--spawn-rate` definem um unico patamar. Para varrer varios
patamares na mesma execucao — e com o mesmo processo, o mesmo pool de
conexoes e o mesmo estado de usuario virtual — e preciso uma LoadTestShape.

Uso
---
    locust -f locustfile.py,shapes/degraus.py --autostart CartUser
    STEP_SECONDS=20 locust -f locustfile.py,shapes/degraus.py --headless CartUser

Carregado a parte (`-f locustfile.py,shapes/degraus.py`) porque uma
LoadTestShape presente no locustfile assume o controle de --users e
--spawn-rate, ignorando os dois em silencio (nem erro, nem aviso).
Mantendo-a fora do arquivo base, os perfis de patamar fixo (smoke, load,
stress) continuam funcionando. O --run-time nao e afetado: ele segue valendo
como corte duro por cima do fim natural da rampa.
"""

from locust import LoadTestShape
from shapes.degraus_config import DEGRAUS, DURACAO_DEGRAU


class RampaEscalonada(LoadTestShape):
    """Sobe os usuarios simultaneos em degraus e encerra no fim do ultimo."""

    use_common_options = True

    def tick(self):
        decorrido = self.get_run_time()
        indice = int(decorrido // DURACAO_DEGRAU)

        if indice >= len(DEGRAUS):
            return None  # fim dos degraus: encerra o teste

        usuarios, entrada = DEGRAUS[indice]
        return usuarios, entrada
