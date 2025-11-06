#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

API_BASE="${MONITOR_API_BASE:-${SLS_API_BASE:-http://127.0.0.1:8880}}"
PANEL_TOKEN="${MONITOR_PANEL_TOKEN:-${PANEL_TOKEN:-}}"
SLACK_WEBHOOK="${MONITOR_SLACK_WEBHOOK:-${SLACK_WEBHOOK_MONITOR:-}}"
TELEGRAM_TOKEN="${MONITOR_TELEGRAM_TOKEN:-}"
TELEGRAM_CHAT_ID="${MONITOR_TELEGRAM_CHAT_ID:-}"
MAX_ARENA_LAG="${MONITOR_MAX_ARENA_LAG:-600}"
MAX_DRAWDOWN="${MONITOR_MAX_DRAWDOWN:-30}"
MAX_TICKS="${MONITOR_MAX_TICKS_SINCE_WIN:-20}"
MIN_SHARPE="${MONITOR_MIN_ARENA_SHARPE:-0.25}"
MIN_DECISIONS="${MONITOR_MIN_DECISIONS_PER_MIN:-0.3}"
DRY_RUN="${MONITOR_DRY_RUN:-}"

CMD=("$PYTHON_BIN" "$ROOT/scripts/tools/monitor_guard.py" "--api-base" "$API_BASE" "--max-arena-lag" "$MAX_ARENA_LAG" "--max-drawdown" "$MAX_DRAWDOWN" "--max-ticks-since-win" "$MAX_TICKS" "--min-arena-sharpe" "$MIN_SHARPE" "--min-decisions-per-min" "$MIN_DECISIONS")
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
