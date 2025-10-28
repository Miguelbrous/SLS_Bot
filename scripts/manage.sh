#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/run"
LOG_DIR="${ROOT_DIR}/logs"
ENV_FILE="${ROOT_DIR}/.env"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"

PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    PYTHON_BIN="${VENV_DIR}/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="$(command -v python)"
  fi
fi

ensure_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
  mkdir -p "${RUN_DIR}" "${LOG_DIR}"
}

pythonpath_env() {
  PYTHONPATH="${PYTHONPATH:-${ROOT_DIR}/bot}"
  export PYTHONPATH
}

is_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" >/dev/null 2>&1
}

start_api() {
  ensure_env
  pythonpath_env
  local pid_file="${RUN_DIR}/api.pid"
  local log_file="${LOG_DIR}/api_server.log"

  if is_running "${pid_file}"; then
    echo "API ya está en ejecución (PID $(cat "${pid_file}"))."
    return 0
  fi

  echo "Iniciando API..."
  (
    cd "${ROOT_DIR}/bot"
    exec "${PYTHON_BIN}" -m uvicorn app.main:app \
      --host "${API_HOST:-0.0.0.0}" \
      --port "${API_PORT:-8880}" \
      >>"${log_file}" 2>&1
  ) &
  echo $! >"${pid_file}"
  echo "API levantada (PID $(cat "${pid_file}")). Logs: ${log_file}"
}

stop_api() {
  local pid_file="${RUN_DIR}/api.pid"
  if is_running "${pid_file}"; then
    echo "Deteniendo API (PID $(cat "${pid_file}"))..."
    kill "$(cat "${pid_file}")" || true
    rm -f "${pid_file}"
  else
    echo "API no está en ejecución."
  fi
}

start_bot() {
  ensure_env
  pythonpath_env
  local pid_file="${RUN_DIR}/bot.pid"
  local log_file="${LOG_DIR}/bot_worker.log"

  if is_running "${pid_file}"; then
    echo "Bot ya está en ejecución (PID $(cat "${pid_file}"))."
    return 0
  fi

  echo "Iniciando bot..."
  (
    cd "${ROOT_DIR}/bot"
    exec "${PYTHON_BIN}" -m uvicorn sls_bot.app:app \
      --host "${BOT_HOST:-0.0.0.0}" \
      --port "${BOT_PORT:-8080}" \
      >>"${log_file}" 2>&1
  ) &
  echo $! >"${pid_file}"
  echo "Bot levantado (PID $(cat "${pid_file}")). Logs: ${log_file}"
}

stop_bot() {
  local pid_file="${RUN_DIR}/bot.pid"
  if is_running "${pid_file}"; then
    echo "Deteniendo bot (PID $(cat "${pid_file}"))..."
    kill "$(cat "${pid_file}")" || true
    rm -f "${pid_file}"
  else
    echo "Bot no está en ejecución."
  fi
}

status() {
  local api_pid_file="${RUN_DIR}/api.pid"
  local bot_pid_file="${RUN_DIR}/bot.pid"
  echo "Estado servicios:"
  if is_running "${api_pid_file}"; then
    echo "  API    -> activa (PID $(cat "${api_pid_file}"))"
  else
    echo "  API    -> detenida"
  fi
  if is_running "${bot_pid_file}"; then
    echo "  Bot    -> activo (PID $(cat "${bot_pid_file}"))"
  else
    echo "  Bot    -> detenido"
  fi
}

tail_logs() {
  local target="$1"
  case "${target}" in
  api)
    touch "${LOG_DIR}/api_server.log"
    tail -n 100 -f "${LOG_DIR}/api_server.log"
    ;;
  bot)
    touch "${LOG_DIR}/bot_worker.log"
    tail -n 100 -f "${LOG_DIR}/bot_worker.log"
    ;;
  *)
    echo "Uso: $0 tail {api|bot}"
    exit 1
    ;;
  esac
}

usage() {
  cat <<EOF
Uso: $(basename "$0") comando

Comandos disponibles:
  encender-api      Inicia la API FastAPI (uvicorn app.main:app)
  apagar-api        Detiene la API
  encender-bot      Inicia el bot (uvicorn sls_bot.app:app)
  apagar-bot        Detiene el bot
  encender-todo     Inicia API y bot
  apagar-todo       Detiene ambos servicios
  estado            Muestra el estado de los procesos
  tail api|bot      Sigue los logs del servicio indicado
EOF
}

encender_todo() {
  start_api
  start_bot
}

apagar_todo() {
  stop_api || true
  stop_bot || true
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
  encender-api) start_api ;;
  apagar-api) stop_api ;;
  encender-bot) start_bot ;;
  apagar-bot) stop_bot ;;
  encender-todo) encender_todo ;;
  apagar-todo) apagar_todo ;;
  estado) status ;;
  tail) shift || true; tail_logs "${1:-}" ;;
  ""|-h|--help|help) usage ;;
  *)
    echo "Comando desconocido: ${cmd}" >&2
    usage
    exit 1
    ;;
  esac
}

main "$@"
