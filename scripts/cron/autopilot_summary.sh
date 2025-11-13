#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

AUTOPILOT_DATASET="${AUTOPILOT_DATASET:-$ROOT/logs/test/cerebro_experience.jsonl}"
AUTOPILOT_RUNS="${AUTOPILOT_RUNS:-$ROOT/arena/runs/*.jsonl}"
AUTOPILOT_OUTPUT_JSON="${AUTOPILOT_OUTPUT_JSON:-$ROOT/metrics/autopilot_summary.json}"
AUTOPILOT_MARKDOWN="${AUTOPILOT_MARKDOWN:-$ROOT/metrics/autopilot_summary.md}"
AUTOPILOT_PROM_FILE="${AUTOPILOT_PROM_FILE:-$ROOT/metrics/autopilot.prom}"
SCALP_DAILY_JSON="${SCALP_DAILY_JSON:-$ROOT/logs/${SLSBOT_MODE:-test}/scalp_daily.jsonl}"
ALERTS_LOG_FILE="${ALERTS_LOG_FILE:-$ROOT/logs/${SLSBOT_MODE:-test}/alerts.log}"

if [[ ! -f "$AUTOPILOT_DATASET" ]]; then
  echo "[autopilot-summary] dataset no encontrado: $AUTOPILOT_DATASET" >&2
  exit 0
fi

mkdir -p "$(dirname "$AUTOPILOT_OUTPUT_JSON")"

python3 "$ROOT/scripts/tools/autopilot_summary.py" \
  --dataset "$AUTOPILOT_DATASET" \
  --runs $AUTOPILOT_RUNS \
  --output-json "$AUTOPILOT_OUTPUT_JSON" \
  --markdown "$AUTOPILOT_MARKDOWN" \
  --prometheus-file "$AUTOPILOT_PROM_FILE" \
  ${SLACK_WEBHOOK_AUTOPILOT:+--slack-webhook "$SLACK_WEBHOOK_AUTOPILOT"}

if [[ -f "$SCALP_DAILY_JSON" ]]; then
  echo "[autopilot-summary] Último scalp diario:"
  tail -n 1 "$SCALP_DAILY_JSON"
fi

if [[ -f "$ALERTS_LOG_FILE" ]]; then
  echo "[autopilot-summary] Alertas recientes:"
  tail -n 20 "$ALERTS_LOG_FILE"
fi
