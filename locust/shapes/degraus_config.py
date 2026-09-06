"""Tabela de degraus da rampa, sem dependencia do Locust.

Fica separada de degraus.py para poder ser lida sem importar o Locust —
util para conferir a tabela de degraus a partir de qualquer script ou do
Python do sistema, fora do virtualenv.
"""

import os

# Cada degrau: (usuarios simultaneos, velocidade de entrada).
# Vao ate 400 porque o login desta stack so satura perto de 80 req/s, e com
# o tempo de leitura dos cenarios (between(1,4), ~2.5s em media) sao
# necessarios ~200 usuarios para chegar la.
DEGRAUS = [
    (10, 2),
    (25, 5),
    (50, 10),
    (100, 20),
    (200, 40),
    (400, 80),
]

# Segundos em cada degrau. Curto demais e o degrau mede o transiente da
# entrada dos usuarios, nao o regime permanente.
DURACAO_DEGRAU = int(os.getenv("STEP_SECONDS", "60"))
