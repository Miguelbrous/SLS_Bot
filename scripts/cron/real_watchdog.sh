#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

MODE="${REAL_WATCHDOG_MODE:-real}"
LOGS_DIR="${REAL_WATCHDOG_LOGS_DIR:-}"
RISK_FILE="${REAL_WATCHDOG_RISK_FILE:-}"
PNL_FILE="${REAL_WATCHDOG_PNL_FILE:-}"
API_BASE="${REAL_WATCHDOG_API_BASE:-${SLS_API_BASE:-}}"
PANEL_TOKEN="${REAL_WATCHDOG_PANEL_TOKEN:-${PANEL_TOKEN:-}}"
SLACK_WEBHOOK="${REAL_WATCHDOG_SLACK_WEBHOOK:-}"
TELEGRAM_TOKEN="${REAL_WATCHDOG_TELEGRAM_TOKEN:-}"
TELEGRAM_CHAT_ID="${REAL_WATCHDOG_TELEGRAM_CHAT_ID:-}"
MAX_STALE="${REAL_WATCHDOG_MAX_PNL_STALE:-3600}"
MIN_TRADES="${REAL_WATCHDOG_MIN_TRADES:-5}"
DEADLINE="${REAL_WATCHDOG_DEADLINE:-22:00}"
BLOCK_GRACE="${REAL_WATCHDOG_BLOCK_GRACE_SEC:-900}"
DRY_RUN="${REAL_WATCHDOG_DRY_RUN:-}"

CMD=("$PYTHON_BIN" "$ROOT/scripts/real_watchdog.py" "--mode" "$MODE" "--max-pnl-stale-seconds" "$MAX_STALE" "--min-trades" "$MIN_TRADES" "--deadline" "$DEADLINE" "--block-grace-seconds" "$BLOCK_GRACE")
if [[ -n "$LOGS_DIR" ]]; then
  CMD+=("--logs-dir" "$LOGS_DIR")
fi
if [[ -n "$RISK_FILE" ]]; then
  CMD+=("--risk-file" "$RISK_FILE")
fi
if [[ -n "$PNL_FILE" ]]; then
  CMD+=("--pnl-file" "$PNL_FILE")
fi
if [[ -n "$API_BASE" ]]; then
  CMD+=("--api-base" "$API_BASE")
fi
if [[ -n "$PANEL_TOKEN" ]]; then
  CMD+=("--panel-token" "$PANEL_TOKEN")
fi
if [[ -n "$SLACK_WEBHOOK" ]]; then
  CMD+=("--slack-webhook" "$SLACK_WEBHOOK")
fi
if [[ -n "$TELEGRAM_TOKEN" && -n "$TELEGRAM_CHAT_ID" ]]; then
  CMD+=("--telegram-token" "$TELEGRAM_TOKEN" "--telegram-chat-id" "$TELEGRAM_CHAT_ID")
fi
if [[ -n "$DRY_RUN" ]]; then
  CMD+=("--dry-run")
fi

exec "${CMD[@]}"
