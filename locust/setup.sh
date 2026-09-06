#!/usr/bin/env bash
#
# Preparo do ambiente do Locust.
#
# E o unico script desta pasta, e ele nao roda teste nenhum: os comandos de
# execucao sao a CLI do Locust e ficam em ../RUN.md, prontos para copiar.
# Aqui nao ha nada nosso — sao os comandos padrao de qualquer projeto Python.

set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo
echo "pronto. os comandos de execucao estao em ../RUN.md, por exemplo:"
echo "  source .venv/bin/activate"
echo "  locust --users 5 --spawn-rate 1 --run-time 30s --autostart"
