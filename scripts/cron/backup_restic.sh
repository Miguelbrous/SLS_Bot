#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESTIC_BIN="${RESTIC_BIN:-$(command -v restic || true)}"

if [[ "${RESTIC_DRY_RUN:-0}" != "1" ]]; then
  if [[ -z "$RESTIC_BIN" ]]; then
    echo "[backup] restic no está instalado o no está en PATH. Exporta RESTIC_BIN=/ruta/restic" >&2
    exit 1
  fi
  export RESTIC_BIN
fi

log() { printf "[backup] %s\n" "$*"; }

: "${RESTIC_REPOSITORY:?Define RESTIC_REPOSITORY (s3://..., /backups/restic, etc.)}"

if [[ -z "${RESTIC_PASSWORD_FILE:-}" && -z "${RESTIC_PASSWORD:-}" ]]; then
  echo "[backup] Debes exportar RESTIC_PASSWORD o RESTIC_PASSWORD_FILE" >&2
  exit 1
fi

BACKUP_PATHS_DEFAULT=(
  "$ROOT/logs"
  "$ROOT/models"
  "$ROOT/config"
  "$ROOT/tmp_logs"
)
IFS=' ' read -r -a BACKUP_PATHS <<< "${RESTIC_BACKUP_PATHS:-${BACKUP_PATHS_DEFAULT[*]}}"

TAGS="${RESTIC_TAGS:-sls-bot,infra}"
EXTRA_ARGS=()
if [[ -n "${RESTIC_HOSTNAME:-}" ]]; then
  EXTRA_ARGS+=("--host" "$RESTIC_HOSTNAME")
fi
if [[ -n "${RESTIC_EXCLUDE_FILE:-}" ]]; then
  EXTRA_ARGS+=("--exclude-file" "$RESTIC_EXCLUDE_FILE")
fi

run_restic() {
  if [[ "${RESTIC_DRY_RUN:-0}" == "1" ]]; then
    log "DRY RUN :: restic $*"
  else
    "$RESTIC_BIN" "$@"
  fi
}

log "Iniciando backup a ${RESTIC_REPOSITORY}"
run_restic backup "${BACKUP_PATHS[@]}" --tag "$TAGS" "${EXTRA_ARGS[@]}"

FORGET_POLICY="${RESTIC_FORGET_ARGS:---keep-daily 7 --keep-weekly 4 --keep-monthly 6}"
log "Aplicando política de retención: $FORGET_POLICY"
run_restic forget $FORGET_POLICY --prune --tag "$TAGS"

if [[ -n "${RESTIC_CHECK:-}" ]]; then
  log "Ejecutando restic check"
  run_restic check
fi

log "Backup finalizado correctamente."
