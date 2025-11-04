#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT/tmp_logs"
mkdir -p "$LOG_DIR"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi

MODE="${CEREBRO_TRAIN_MODE:-${SLSBOT_MODE:-test}}"
EPOCHS="${CEREBRO_TRAIN_EPOCHS:-400}"
LR="${CEREBRO_TRAIN_LR:-0.05}"
TRAIN_RATIO="${CEREBRO_TRAIN_RATIO:-0.8}"
MIN_AUC="${CEREBRO_TRAIN_MIN_AUC:-0.58}"
MIN_WIN="${CEREBRO_TRAIN_MIN_WIN_RATE:-0.55}"
SEED="${CEREBRO_TRAIN_SEED:-42}"
DATASET="${CEREBRO_TRAIN_DATASET:-}"
OUTPUT_DIR="${CEREBRO_TRAIN_OUTPUT:-}"
DRY_RUN="${CEREBRO_TRAIN_DRY_RUN:-}"  # set to 1 to avoid promover

CMD=("python" "$ROOT/scripts/ops.py" "cerebro" "train" "--mode" "$MODE" "--epochs" "$EPOCHS" "--lr" "$LR" "--train-ratio" "$TRAIN_RATIO" "--min-auc" "$MIN_AUC" "--min-win-rate" "$MIN_WIN" "--seed" "$SEED")
if [[ -n "$DATASET" ]]; then
  CMD+=("--dataset" "$DATASET")
fi
if [[ -n "$OUTPUT_DIR" ]]; then
  CMD+=("--output-dir" "$OUTPUT_DIR")
fi
if [[ -n "$DRY_RUN" ]]; then
  CMD+=("--dry-run")
fi

SESSION_LOG="$LOG_DIR/cerebro_train.log"
echo "[cerebro-train] $(date --iso-8601=seconds) :: ${CMD[*]}" | tee -a "$SESSION_LOG"
"${CMD[@]}" | tee -a "$SESSION_LOG"
