#!/usr/bin/env bash
#
# Devolve o banco da aplicacao ao estado logo apos o seed.
#
# Mora na raiz porque o estado sujo nao pertence a nenhuma suite: quem
# corrompe o banco e o Locust (sobrevenda de estoque, contas bloqueadas por
# login invalido) tanto quanto o Artillery, e o reset e o mesmo para os dois.
#
# Nao ha nada de teste aqui — e um POST em /refresh, que do lado da API faz:
#
#     Artisan::call('migrate:fresh', ['--seed' => null]);   # recria e semeia
#     Artisan::call('invoice:remove');                      # apaga as notas
#     Cache::flush();                                       # limpa o cache de 300s
#
# Efeito pratico: estoque volta a 25, a tabela `jobs` some com os debitos
# pendentes, as contas bloqueadas (HTTP 423) sao liberadas e a API para de
# servir valores cacheados de registros que nao existem mais.
#
#   ./reset.sh                  # reseta e confere
#   ./reset.sh --sem-conferir   # so reseta
#
# ATENCAO: apaga TODO o estado da aplicacao, inclusive as evidencias de uma
# execucao anterior (estoque negativo, notas emitidas). Rode depois de
# registrar o que precisa, nao antes.
#
set -euo pipefail
cd "$(dirname "$0")"

API="${TOOLSHOP_API_HOST:-http://localhost:8091}"

case "${1:-}" in
  -h|--help) sed -n '3,22p' "$0" | sed 's/^# \?//'; exit 0 ;;
esac

echo "Resetando $API — migrate:fresh --seed ..."
curl -fsS -X POST "$API/refresh" >/dev/null
echo "banco recriado e semeado"

# O 500 por permissao em storage/ nao e resolvido pelo refresh: ele recria o
# banco, nao os diretorios de cache em disco. Ver FIX-PERMISSOES.md.
codigo=$(curl -s -o /dev/null -w '%{http_code}' "$API/brands")
if [ "$codigo" != "200" ]; then
    echo
    echo "AVISO: GET /brands respondeu $codigo, nao 200." >&2
    echo "Provavelmente e o 500 de permissao em storage/ — o reset nao conserta." >&2
    echo "Ver FIX-PERMISSOES.md. Contorno:" >&2
    echo "  docker compose --project-directory practice-software-testing exec -u root \\" >&2
    echo "    laravel-api chown -R www-data:www-data storage/framework/cache" >&2
    exit 1
fi

if [ "${1:-}" != "--sem-conferir" ]; then
    echo
    ./locust/conferir-estoque.sh
fi
