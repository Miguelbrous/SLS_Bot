#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/tmp_logs"
mkdir -p "$LOG_DIR"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi

export SLSBOT_MODE="${SLSBOT_MODE:-test}"
export STRATEGY_ID="${STRATEGY_ID:-scalp_rush_v1}"
export STRATEGY_INTERVAL_SECONDS="${STRATEGY_INTERVAL_SECONDS:-30}"
export STRATEGY_LEVERAGE="${STRATEGY_LEVERAGE:-20}"

SESSION_LOG="$LOG_DIR/testnet_session.log"
echo "[testnet] $(date --iso-8601=seconds) :: Iniciando servicios (modo=$SLSBOT_MODE, estrategia=$STRATEGY_ID)" | tee -a "$SESSION_LOG"
python "$ROOT/scripts/ops.py" up | tee -a "$SESSION_LOG"

echo "[testnet] $(date --iso-8601=seconds) :: Ejecuta 'python scripts/ops.py arena run --interval 300' en otra terminal si quieres la arena en vivo." | tee -a "$SESSION_LOG"
