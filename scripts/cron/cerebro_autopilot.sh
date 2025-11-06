#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT/tmp_logs"
mkdir -p "$LOG_DIR"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

MODE="${CEREBRO_AUTO_MODE:-${SLSBOT_MODE:-test}}"
MIN_ROWS="${CEREBRO_AUTO_MIN_ROWS:-200}"
BACKFILL_ROWS="${CEREBRO_AUTO_BACKFILL:-400}"
EPOCHS="${CEREBRO_AUTO_EPOCHS:-400}"
LR="${CEREBRO_AUTO_LR:-0.05}"
TRAIN_RATIO="${CEREBRO_AUTO_TRAIN_RATIO:-0.8}"
MIN_AUC="${CEREBRO_AUTO_MIN_AUC:-0.6}"
MIN_WIN_RATE="${CEREBRO_AUTO_MIN_WIN_RATE:-0.55}"
DATASET="${CEREBRO_AUTO_DATASET:-}"
OUTPUT_DIR="${CEREBRO_AUTO_OUTPUT:-}"
LOG_FILE="${CEREBRO_AUTO_LOG_FILE:-$LOG_DIR/cerebro_autopilot_runner.log}"
DRY_RUN="${CEREBRO_AUTO_DRY_RUN:-}"
NO_PROMOTE="${CEREBRO_AUTO_NO_PROMOTE:-}"
SLACK_WEBHOOK="${CEREBRO_AUTO_SLACK_WEBHOOK:-}"
SLACK_USER="${CEREBRO_AUTO_SLACK_USER:-}"
TEXTFILE_DIR="${NODE_EXPORTER_TEXTFILE_DIR:-}"
PROM_FILE="${CEREBRO_AUTO_PROM_FILE:-}"
if [[ -z "$PROM_FILE" && -n "$TEXTFILE_DIR" ]]; then
  PROM_FILE="$TEXTFILE_DIR/cerebro_autopilot.prom"
fi
REQUIRE_PROMOTE="${CEREBRO_AUTO_REQUIRE_PROMOTE:-}"
MAX_DATASET_AGE="${CEREBRO_AUTO_MAX_DATASET_AGE_MIN:-}"
DATASET_MIN_WIN_RATE="${CEREBRO_AUTO_DATASET_MIN_WIN_RATE:-}"
DATASET_MAX_WIN_RATE="${CEREBRO_AUTO_DATASET_MAX_WIN_RATE:-}"
DATASET_MIN_SYMBOLS="${CEREBRO_AUTO_DATASET_MIN_SYMBOLS:-}"
DATASET_MAX_AGE_HOURS="${CEREBRO_AUTO_DATASET_MAX_AGE_HOURS:-}"
SKIP_DATASET_CHECK="${CEREBRO_AUTO_SKIP_DATASET_CHECK:-}"
DATASET_MIN_ROWS_PER_SYMBOL="${CEREBRO_AUTO_DATASET_MIN_ROWS_PER_SYMBOL:-}"
DATASET_MAX_SYMBOL_SHARE="${CEREBRO_AUTO_DATASET_MAX_SYMBOL_SHARE:-}"
DATASET_MIN_LONG_RATE="${CEREBRO_AUTO_DATASET_MIN_LONG_RATE:-}"
DATASET_MIN_SHORT_RATE="${CEREBRO_AUTO_DATASET_MIN_SHORT_RATE:-}"
DATASET_MAX_INVALID_LINES="${CEREBRO_AUTO_DATASET_MAX_INVALID_LINES:-}"
DATASET_MAX_ZERO_RATE="${CEREBRO_AUTO_DATASET_MAX_ZERO_RATE:-}"
DATASET_MAX_LOSS_RATE="${CEREBRO_AUTO_DATASET_MAX_LOSS_RATE:-}"
SUMMARY_FILE="${CEREBRO_AUTO_SUMMARY_FILE:-}"
SUMMARY_APPEND="${CEREBRO_AUTO_SUMMARY_APPEND:-}"
SUMMARY_COMPARE_FILE="${CEREBRO_AUTO_SUMMARY_COMPARE:-}"
SUMMARY_MAX_WIN_DELTA="${CEREBRO_AUTO_SUMMARY_MAX_WIN_DELTA:-}"
SUMMARY_MAX_LOSS_DELTA="${CEREBRO_AUTO_SUMMARY_MAX_LOSS_DELTA:-}"
SUMMARY_MAX_ROWS_DROP="${CEREBRO_AUTO_SUMMARY_MAX_ROWS_DROP:-}"

CMD=("${PYTHON_BIN:-python}" "$ROOT/scripts/ops.py" "cerebro" "autopilot" "--mode" "$MODE" "--min-rows" "$MIN_ROWS" "--backfill-rows" "$BACKFILL_ROWS" "--epochs" "$EPOCHS" "--lr" "$LR" "--train-ratio" "$TRAIN_RATIO" "--min-auc" "$MIN_AUC" "--min-win-rate" "$MIN_WIN_RATE" "--log-file" "$LOG_FILE")
if [[ -n "$DATASET" ]]; then
  CMD+=("--dataset" "$DATASET")
fi
if [[ -n "$OUTPUT_DIR" ]]; then
  CMD+=("--output-dir" "$OUTPUT_DIR")
fi
if [[ -n "$DRY_RUN" ]]; then
  CMD+=("--dry-run")
fi
if [[ -n "$NO_PROMOTE" ]]; then
  CMD+=("--no-promote")
fi
if [[ -n "$PROM_FILE" ]]; then
  CMD+=("--prometheus-file" "$PROM_FILE")
fi
if [[ -n "$SLACK_WEBHOOK" ]]; then
  CMD+=("--slack-webhook" "$SLACK_WEBHOOK")
fi
if [[ -n "$SLACK_USER" ]]; then
  CMD+=("--slack-user" "$SLACK_USER")
fi
if [[ -n "$REQUIRE_PROMOTE" ]]; then
  CMD+=("--require-promote")
fi
if [[ -n "$MAX_DATASET_AGE" ]]; then
  CMD+=("--max-dataset-age-minutes" "$MAX_DATASET_AGE")
fi
if [[ -n "$DATASET_MIN_WIN_RATE" ]]; then
  CMD+=("--dataset-min-win-rate" "$DATASET_MIN_WIN_RATE")
fi
if [[ -n "$DATASET_MAX_WIN_RATE" ]]; then
  CMD+=("--dataset-max-win-rate" "$DATASET_MAX_WIN_RATE")
fi
if [[ -n "$DATASET_MIN_SYMBOLS" ]]; then
  CMD+=("--dataset-min-symbols" "$DATASET_MIN_SYMBOLS")
fi
if [[ -n "$DATASET_MAX_AGE_HOURS" ]]; then
  CMD+=("--dataset-max-age-hours" "$DATASET_MAX_AGE_HOURS")
fi
if [[ -n "$SKIP_DATASET_CHECK" ]]; then
  CMD+=("--skip-dataset-check")
fi
if [[ -n "$DATASET_MIN_ROWS_PER_SYMBOL" ]]; then
  CMD+=("--dataset-min-rows-per-symbol" "$DATASET_MIN_ROWS_PER_SYMBOL")
fi
if [[ -n "$DATASET_MAX_SYMBOL_SHARE" ]]; then
  CMD+=("--dataset-max-symbol-share" "$DATASET_MAX_SYMBOL_SHARE")
fi
if [[ -n "$DATASET_MIN_LONG_RATE" ]]; then
  CMD+=("--dataset-min-long-rate" "$DATASET_MIN_LONG_RATE")
fi
if [[ -n "$DATASET_MIN_SHORT_RATE" ]]; then
  CMD+=("--dataset-min-short-rate" "$DATASET_MIN_SHORT_RATE")
fi
if [[ -n "$DATASET_MAX_INVALID_LINES" ]]; then
  CMD+=("--dataset-max-invalid-lines" "$DATASET_MAX_INVALID_LINES")
fi
if [[ -n "$DATASET_MAX_ZERO_RATE" ]]; then
  CMD+=("--dataset-max-zero-rate" "$DATASET_MAX_ZERO_RATE")
fi
if [[ -n "$DATASET_MAX_LOSS_RATE" ]]; then
  CMD+=("--dataset-max-loss-rate" "$DATASET_MAX_LOSS_RATE")
fi
if [[ -n "$SUMMARY_FILE" ]]; then
  CMD+=("--summary-json" "$SUMMARY_FILE")
fi
if [[ -n "$SUMMARY_APPEND" ]]; then
  CMD+=("--summary-append")
fi
if [[ -n "$SUMMARY_COMPARE_FILE" ]]; then
  CMD+=("--summary-compare-file" "$SUMMARY_COMPARE_FILE")
fi
if [[ -n "$SUMMARY_MAX_WIN_DELTA" ]]; then
  CMD+=("--summary-max-win-rate-delta" "$SUMMARY_MAX_WIN_DELTA")
fi
if [[ -n "$SUMMARY_MAX_LOSS_DELTA" ]]; then
  CMD+=("--summary-max-loss-rate-delta" "$SUMMARY_MAX_LOSS_DELTA")
fi
if [[ -n "$SUMMARY_MAX_ROWS_DROP" ]]; then
  CMD+=("--summary-max-rows-drop" "$SUMMARY_MAX_ROWS_DROP")
fi

echo "[cerebro-autopilot] $(date --iso-8601=seconds) :: ${CMD[*]}" | tee -a "$LOG_FILE"
"${CMD[@]}" | tee -a "$LOG_FILE"
