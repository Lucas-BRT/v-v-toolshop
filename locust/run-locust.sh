#!/usr/bin/env bash
#
# Runner dos testes de carga com Locust contra o Toolshop.
#
# Por padrao o teste e disparado pela CLI mas a interface web sobe junto,
# em http://localhost:8089, com as metricas ao vivo (graficos de RPS,
# tempo de resposta e usuarios). A UI continua no ar depois que o teste
# termina, entao da para navegar pelos numeros com calma.
#
#   ./run-locust.sh                      # UI vazia, teste disparado a mao
#   ./run-locust.sh smoke                # 5 usuarios, 30s, metricas na UI
#   ./run-locust.sh load                 # 50 usuarios, 3m
#   ./run-locust.sh stress               # 200 usuarios, 5m
#   ./run-locust.sh smoke browse         # so o cenario de navegacao
#   ./run-locust.sh load cart -- --csv-full-history
#
# Variaveis de ambiente uteis:
#   TOOLSHOP_API_HOST   host da API             (default http://localhost:8091)
#   WEB_PORT            porta da interface web  (default 8089)
#   HEADLESS=1          sem interface web, so terminal (uso em CI)
#   AUTOQUIT=<seg>      encerra o processo N segundos apos o teste acabar
#   USERS / SPAWN_RATE / RUN_TIME    sobrescrevem o perfil escolhido
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
REPORT_DIR="reports"
API_HOST="${TOOLSHOP_API_HOST:-http://localhost:8091}"
WEB_PORT="${WEB_PORT:-8089}"

profile="${1:-ui}"
scenario="${2:-all}"
# "./run-locust.sh smoke -- --flag" nao informa cenario: o "--" nao e um.
[[ "$scenario" == "--" ]] && scenario="all"

# Tudo depois de "--" vai direto para o locust.
extra_args=()
for arg in "$@"; do
  if [[ "${passthrough:-0}" == "1" ]]; then
    extra_args+=("$arg")
  elif [[ "$arg" == "--" ]]; then
    passthrough=1
  fi
done

die() { echo "erro: $*" >&2; exit 1; }

# --- ambiente Python ---------------------------------------------------------
setup_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    echo ">> criando virtualenv em $SCRIPT_DIR/$VENV_DIR"
    if command -v uv >/dev/null 2>&1; then
      uv venv "$VENV_DIR" >/dev/null
    else
      python3 -m venv "$VENV_DIR"
    fi
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  if ! python -c "import locust" >/dev/null 2>&1; then
    echo ">> instalando dependencias (requirements.txt)"
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "$VENV_DIR/bin/python" -r requirements.txt >/dev/null
    else
      pip install --quiet --upgrade pip
      pip install --quiet -r requirements.txt
    fi
  fi
}

# --- pre-flight --------------------------------------------------------------
check_api() {
  echo ">> checando API em $API_HOST"
  if ! curl -fsS -m 10 "$API_HOST/status" >/dev/null; then
    die "API nao respondeu em $API_HOST/status. Suba a stack:
       cd ../practice-software-testing && docker compose up -d"
  fi
}

# --- selecao de cenario ------------------------------------------------------
user_classes=()
case "$scenario" in
  all)     user_classes=() ;;
  browse)  user_classes=(BrowseUser) ;;
  cart)    user_classes=(CartUser) ;;
  auth)    user_classes=(AuthenticatedUser) ;;
  *)       die "cenario desconhecido: '$scenario' (use: all, browse, cart, auth)" ;;
esac

# --- perfis de carga ---------------------------------------------------------
case "$profile" in
  ui)
    users=""; spawn_rate=""; run_time="" ;;
  smoke)
    users=5;   spawn_rate=1;  run_time="30s" ;;
  load)
    users=50;  spawn_rate=5;  run_time="3m" ;;
  stress)
    users=500; spawn_rate=20; run_time="5m" ;;
  *)
    die "perfil desconhecido: '$profile' (use: ui, smoke, load, stress)" ;;
esac

# Sobrescritas explicitas por variavel de ambiente.
users="${USERS:-$users}"
spawn_rate="${SPAWN_RATE:-$spawn_rate}"
run_time="${RUN_TIME:-$run_time}"

setup_venv
check_api
mkdir -p "$REPORT_DIR"

cmd=(locust --host "$API_HOST")

if [[ "$profile" == "ui" ]]; then
  # Sem carga definida: a interface sobe vazia e o teste e configurado la.
  # O class-picker deixa escolher o cenario na propria tela.
  cmd+=(--web-port "$WEB_PORT" --class-picker)
  echo ">> interface web em http://localhost:$WEB_PORT (Ctrl+C para sair)"
  echo ">> escolha o cenario e a carga na propria tela"
else
  stamp="$(date +%Y%m%d-%H%M%S)"
  report_base="$REPORT_DIR/${profile}-${scenario}-${stamp}"

  cmd+=(
    --users "$users"
    --spawn-rate "$spawn_rate"
    --run-time "$run_time"
    --html "${report_base}.html"
    --csv "$report_base"
    --exit-code-on-error 1
  )

  if [[ "${HEADLESS:-0}" == "1" ]]; then
    # Modo CI: sem interface, so o resumo no terminal.
    cmd+=(--headless)
    echo ">> modo headless (sem interface web)"
  else
    # --autostart dispara o teste na hora, como o headless, mas mantem a
    # interface web no ar com as metricas ao vivo.
    cmd+=(--autostart --web-port "$WEB_PORT")
    echo ">> metricas ao vivo em http://localhost:$WEB_PORT"
    echo ">> a interface segue no ar apos o teste; Ctrl+C para encerrar"
  fi

  [[ -n "${AUTOQUIT:-}" ]] && cmd+=(--autoquit "$AUTOQUIT")

  echo ">> perfil=$profile cenario=$scenario usuarios=$users spawn=$spawn_rate duracao=$run_time"
  echo ">> relatorio: ${report_base}.html"
fi

# Arrays vazios precisam de guarda por causa do "set -u".
[[ ${#extra_args[@]} -gt 0 ]] && cmd+=("${extra_args[@]}")
[[ ${#user_classes[@]} -gt 0 ]] && cmd+=("${user_classes[@]}")

set -x
exec "${cmd[@]}"
