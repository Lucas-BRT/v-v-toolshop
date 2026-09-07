#!/usr/bin/env bash
#
# Preparo do ambiente do Artillery.
#
# E o unico script desta pasta, e ele nao roda teste nenhum: os comandos de
# execucao sao a CLI do Artillery e ficam em ../RUN.md, prontos para copiar.
# O reset do banco mora em ../reset.sh, na raiz — ele serve as duas suites.

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
    # O reset saiu daqui: o estado sujo nao pertence a nenhuma suite.
    echo "o reset agora e ../reset.sh (na raiz do repositorio)" >&2
    exit 1
    ;;
  *)
    echo "uso: ./setup.sh [install]" >&2
    echo "para resetar o banco: ../reset.sh" >&2
    exit 1
    ;;
esac
