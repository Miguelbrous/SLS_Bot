#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

DIR="${NODE_EXPORTER_TEXTFILE_DIR:-$ROOT/tmp_metrics/textfile}"
MAX_AGE="${CEREBRO_SMOKE_MAX_AGE:-30}"
RUN_SUITE_BEFORE=1
RUN_SUITE_AFTER=1
RUN_INGEST=1
RUN_AUTOPILOT=1
EXTRA_METRICS=()

function usage() {
  cat <<EOF
Uso: $(basename "$0") [opciones]
  --dir PATH             Directorio del textfile collector (default: \$NODE_EXPORTER_TEXTFILE_DIR o tmp_metrics/textfile)
  --max-age MIN          Antigüedad máxima permitida para los .prom (default: \$CEREBRO_SMOKE_MAX_AGE o 30)
  --skip-suite-before    No ejecuta el textfile suite antes de las simulaciones
  --skip-suite-after     No ejecuta el textfile suite después de las simulaciones
  --skip-ingest          Omite la simulación de fallo de ingest
  --skip-autopilot       Omite la simulación de fallo de autopilot
  --require-metric NAME  Métrica extra que debe existir en ambos archivos (puede repetirse)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      DIR="$2"
      shift 2
      ;;
    --max-age)
      MAX_AGE="$2"
      shift 2
      ;;
    --skip-suite-before)
      RUN_SUITE_BEFORE=0
      shift
      ;;
    --skip-suite-after)
      RUN_SUITE_AFTER=0
      shift
      ;;
    --skip-ingest)
      RUN_INGEST=0
      shift
      ;;
    --skip-autopilot)
      RUN_AUTOPILOT=0
      shift
      ;;
    --require-metric)
      EXTRA_METRICS+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opción desconocida: $1" >&2
      usage
      exit 1
      ;;
  esac
done

DIR="$(cd "$DIR" && pwd)"
INGEST_PROM="${CEREBRO_SMOKE_INGEST_PROM:-$DIR/cerebro_ingest.prom}"
AUTOP_PROM="${CEREBRO_SMOKE_AUTOP_PROM:-$DIR/cerebro_autopilot.prom}"

read -r -a INGEST_EXTRA <<< "${CEREBRO_SMOKE_INGEST_ARGS:-}"
read -r -a AUTOP_EXTRA <<< "${CEREBRO_SMOKE_AUTOP_ARGS:-}"

function run_suite() {
  local stage="$1"
  echo "[cerebro-metrics-smoke] Ejecutando suite (${stage})..."
  local cmd=("$PYTHON_BIN" "$ROOT/scripts/tests/prometheus_textfile_suite.py" "--dir" "$DIR" "--max-age-minutes" "$MAX_AGE")
  for metric in "${EXTRA_METRICS[@]}"; do
    cmd+=("--require-metric" "$metric")
  done
  "${cmd[@]}"
}

function run_ingest_sim() {
  echo "[cerebro-metrics-smoke] Forzando fallo de ingest..."
  local cmd=("$PYTHON_BIN" "$ROOT/scripts/tests/cerebro_ingest_failure_sim.py" "--prometheus-file" "$INGEST_PROM")
  if [[ ${#INGEST_EXTRA[@]} -gt 0 ]]; then
    cmd+=("--extra-args")
    cmd+=("${INGEST_EXTRA[@]}")
  fi
  "${cmd[@]}"
}

function run_autopilot_sim() {
  echo "[cerebro-metrics-smoke] Forzando fallo de autopilot..."
  local cmd=("$PYTHON_BIN" "$ROOT/scripts/tests/cerebro_autopilot_failure_sim.py" "--prometheus-file" "$AUTOP_PROM")
  if [[ ${#AUTOP_EXTRA[@]} -gt 0 ]]; then
    cmd+=("--extra-args")
    cmd+=("${AUTOP_EXTRA[@]}")
  fi
  "${cmd[@]}"
}

[[ $RUN_SUITE_BEFORE -eq 1 ]] && run_suite "antes"
[[ $RUN_INGEST -eq 1 ]] && run_ingest_sim
[[ $RUN_AUTOPILOT -eq 1 ]] && run_autopilot_sim
[[ $RUN_SUITE_AFTER -eq 1 ]] && run_suite "después"

echo "[cerebro-metrics-smoke] Listo."
