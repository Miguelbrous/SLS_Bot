#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

AUTOPILOT_DATASET="${AUTOPILOT_DATASET:-$ROOT/logs/test/cerebro_experience.jsonl}"
AUTOPILOT_RUNS="${AUTOPILOT_RUNS:-$ROOT/arena/runs/*.jsonl}"
AUTOPILOT_OUTPUT_JSON="${AUTOPILOT_OUTPUT_JSON:-$ROOT/metrics/autopilot_summary.json}"
AUTOPILOT_MARKDOWN="${AUTOPILOT_MARKDOWN:-$ROOT/metrics/autopilot_summary.md}"
AUTOPILOT_PROM_FILE="${AUTOPILOT_PROM_FILE:-$ROOT/metrics/autopilot.prom}"

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
