#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/SLS_Bot}"
SVC_USER="${SVC_USER:-sls}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
TEMPLATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/systemd"
SERVICE_NAME="sls-cerebro.service"
TARGET="${SYSTEMD_DIR}/${SERVICE_NAME}"

echo "[+] Instalando ${SERVICE_NAME} con APP_ROOT=${APP_ROOT} y usuario ${SVC_USER}"

if [[ ! -d "${APP_ROOT}" ]]; then
  echo "ERROR: APP_ROOT ${APP_ROOT} no existe." >&2
  exit 1
fi

if [[ ! -x "${APP_ROOT}/venv/bin/python" ]]; then
  echo "ERROR: No se encontró venv en ${APP_ROOT}/venv. Ejecuta scripts/deploy/bootstrap.sh primero." >&2
  exit 1
fi

mkdir -p "${SYSTEMD_DIR}"
sed \
  -e "s#{{APP_ROOT}}#${APP_ROOT}#g" \
  -e "s#{{SVC_USER}}#${SVC_USER}#g" \
  "${TEMPLATE_DIR}/sls-cerebro.service" \
  | sudo tee "${TARGET}" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now sls-cerebro.service

echo "[+] Servicio sls-cerebro.service instalado. Verifica salud con:"
echo "    curl -s http://localhost:${SLS_API_PORT:-8880}/cerebro/status | jq '.time, .decisions | length'"
