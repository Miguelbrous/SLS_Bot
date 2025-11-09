#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

: "${RESTIC_REPOSITORY:?Define RESTIC_REPOSITORY}"
if [[ -z "${RESTIC_PASSWORD_FILE:-}" && -z "${RESTIC_PASSWORD:-}" ]]; then
  echo "[backup] Debes exportar RESTIC_PASSWORD o RESTIC_PASSWORD_FILE" >&2
  exit 1
fi

BACKUP_PATHS_DEFAULT=("$ROOT/logs" "$ROOT/models" "$ROOT/excel" "$ROOT/config")
IFS=' ' read -r -a BACKUP_PATHS <<< "${RESTIC_BACKUP_PATHS:-${BACKUP_PATHS_DEFAULT[*]}}"

run() {
  if [[ "${RESTIC_DRY_RUN:-0}" == "1" ]]; then
    echo "[backup] DRY RUN :: /usr/bin/restic $*"
  else
    /usr/bin/restic "$@"
  fi
}

echo "[backup] Iniciando backup..."
run backup "${BACKUP_PATHS[@]}" --tag "${RESTIC_TAGS:-sls-bot}"
if [[ -n "${RESTIC_FORGET_ARGS:-}" ]]; then
  echo "[backup] Applying forget policy: $RESTIC_FORGET_ARGS"
  run forget ${RESTIC_FORGET_ARGS} --prune --tag "${RESTIC_TAGS:-sls-bot}"
fi
if [[ "${RESTIC_CHECK:-0}" == "1" ]]; then
  echo "[backup] Running /usr/bin/restic check..."
  run check
fi
