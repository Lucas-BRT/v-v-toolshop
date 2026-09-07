#!/usr/bin/env bash
#
# Mostra o estoque pelas duas fontes, lado a lado.
#
# O banco tem o valor real. A API responde atraves de um cache de 300s que o
# job de debito nunca invalida, entao ela fica para tras depois de uma venda.
# A coluna "!" marca as linhas em que as duas discordam — e essa divergencia
# que o cenario de sobrevenda expoe.
#
#   ./conferir-estoque.sh                    # todos os produtos com estoque
#   ./conferir-estoque.sh <product_id>       # so um produto
#   ./conferir-estoque.sh --limpar-cache     # invalida o cache e le de novo
#
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK="$RAIZ/practice-software-testing"
API="${TOOLSHOP_API_HOST:-http://localhost:8091}"
ADMIN_EMAIL="${TOOLSHOP_ADMIN_EMAIL:-admin@practicesoftwaretesting.com}"
ADMIN_PASSWORD="${TOOLSHOP_ADMIN_PASSWORD:-welcome01}"

FILTRO=""
for arg in "$@"; do
    case "$arg" in
        --limpar-cache)
            echo "Limpando o cache da API..."
            docker compose --project-directory "$STACK" exec -T laravel-api \
                php artisan cache:clear >/dev/null 2>&1 \
                && echo "cache limpo" || echo "AVISO: nao consegui limpar o cache"
            ;;
        -h|--help) sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *) FILTRO="$arg" ;;
    esac
done

# ---------------------------------------------------------------- banco
# `stock IS NOT NULL` descarta os itens de aluguel (Excavator, Bulldozer,
# Crane), que nao tem estoque e ocupariam o topo do ORDER BY.
consulta="SELECT id, name, stock FROM products WHERE stock IS NOT NULL"
[ -n "$FILTRO" ] && consulta="$consulta AND id = '$FILTRO'"
consulta="$consulta ORDER BY stock;"

banco=$(docker compose --project-directory "$STACK" exec -T mariadb \
            mysql -uroot -proot toolshop -N -e "$consulta" 2>/dev/null)
if [ -z "$banco" ]; then
    echo "AVISO: nao consegui ler o banco (a stack esta no ar?). Seguindo so com a API." >&2
fi

# ------------------------------------------------------------------ API
# Token de admin: para os demais usuarios `in_stock` vem como booleano
# (Product::getInStockAttribute), nao como numero.
token=$(curl -s -H 'Content-Type: application/json' \
             -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
             "$API/users/login" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)

if [ -z "$token" ]; then
    echo "ERRO: login de admin falhou em $API — a API esta no ar?" >&2
    exit 1
fi

if [ -n "$FILTRO" ]; then
    api=$(curl -s -H "Authorization: Bearer $token" "$API/products/$FILTRO" \
          | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["id"], d["in_stock"], sep="\t")' 2>/dev/null)
else
    # Varre todas as paginas: o banco tem ~50 produtos e /products pagina de 9
    # em 9. Sem isso a coluna da API fica quase toda vazia.
    api=$(API="$API" TOKEN="$token" python3 <<'PY' 2>/dev/null
import json, os, urllib.request

api, token = os.environ["API"], os.environ["TOKEN"]

def pagina(n):
    req = urllib.request.Request(
        f"{api}/products?page={n}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

n, ultima = 1, 1
while n <= ultima:
    corpo = pagina(n)
    ultima = corpo.get("last_page", 1)
    for p in corpo["data"]:
        print(p["id"], p["in_stock"], sep="\t")
    n += 1
PY
)
fi

# ------------------------------------------------------------- comparacao
BANCO="$banco" API_ROWS="$api" python3 <<'PY'
import os

banco = {}
ordem = []
for linha in os.environ["BANCO"].splitlines():
    if not linha.strip():
        continue
    pid, nome, estoque = linha.split("\t")
    banco[pid] = (nome, int(estoque))
    ordem.append(pid)

api = {}
for linha in os.environ["API_ROWS"].splitlines():
    if not linha.strip():
        continue
    pid, valor = linha.split("\t")
    api[pid] = None if valor in ("None", "") else int(valor)

# O banco manda na ordem (ja vem por estoque crescente). Produtos que so a
# API conhece entram depois — acontece quando a stack nao respondeu.
for pid in api:
    if pid not in ordem:
        ordem.append(pid)

print()
print("FONTE 1 = banco (products.stock, valor real)")
print("FONTE 2 = API  (/products, atraves do cache de 300s)")
print()
print("%-28s %-40s %10s %10s  %s" % ("ID", "PRODUTO", "BANCO", "API", "!"))
print("-" * 96)
divergentes = 0
for pid in ordem:
    nome, real = banco.get(pid, ("(so na API)", None))
    cache = api.get(pid)
    marca = ""
    if real is not None and cache is not None and real != cache:
        marca = "<-- divergem"
        divergentes += 1
    print("%-28s %-40s %10s %10s  %s" % (
        pid, nome[:40],
        "-" if real is None else real,
        "-" if cache is None else cache,
        marca))
print()

negativos = [p for p, (_, e) in banco.items() if e < 0]
if negativos:
    print("%d produto(s) com estoque NEGATIVO no banco — a API vendeu o que nao tinha." % len(negativos))
if divergentes:
    print("%d linha(s) divergem: a API serve valor cacheado (TTL 300s) que o job de" % divergentes)
    print("debito nunca invalida. Use --limpar-cache para forcar, ou espere o TTL vencer.")
if not negativos and not divergentes:
    print("Estoque consistente entre banco e API, nada negativo.")
PY
