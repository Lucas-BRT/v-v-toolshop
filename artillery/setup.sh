#!/usr/bin/env bash
#
# Preparo do ambiente do Artillery e reset do banco da aplicacao.
#
# E o unico script desta pasta, e ele nao roda teste nenhum: os comandos de
# execucao sao a CLI do Artillery e ficam em ../RUN.md, prontos para copiar.

set -euo pipefail
cd "$(dirname "$0")"

case "${1:-install}" in
  install)
    npm install
    echo
    echo "pronto. os comandos de execucao estao em ../RUN.md, por exemplo:"
    echo "  npx artillery run scenarios/01-pico-de-trafego.yml"
    ;;
  reset)
    # Recria o banco da aplicacao (migrate:fresh --seed). Util quando um
    # cenario sujou o estado — por exemplo uma conta bloqueada por
    # tentativas de login invalidas. E so um POST; nao ha nada do Artillery
    # envolvido, por isso mora aqui e nao no runner.
    curl -fsS -X POST "${TARGET:-http://localhost:8091}/refresh"
    echo
    ;;
  *)
    echo "uso: ./setup.sh [install|reset]" >&2
    exit 1
    ;;
esac
