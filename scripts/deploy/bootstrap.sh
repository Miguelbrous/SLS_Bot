#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(pwd)}"
SVC_USER="${SVC_USER:-sls}"
INSTALL_SYSTEMD="${INSTALL_SYSTEMD:-0}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NPM_BIN="${NPM_BIN:-npm}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

info() {
  echo "[bootstrap] $*"
}

info "Usando APP_ROOT=${APP_ROOT}"

if [ ! -d "${APP_ROOT}/venv" ]; then
  info "Creando entorno virtual (venv)"
  "${PYTHON_BIN}" -m venv "${APP_ROOT}/venv"
fi

source "${APP_ROOT}/venv/bin/activate"

info "Instalando dependencias Python"
pip install --upgrade pip >/dev/null
pip install -r "${APP_ROOT}/bot/requirements.txt"
if [ -f "${APP_ROOT}/bot/requirements-dev.txt" ]; then
  pip install -r "${APP_ROOT}/bot/requirements-dev.txt"
fi

info "Ejecutando pytest"
pytest "${APP_ROOT}/bot/tests" -q

info "Instalando dependencias del panel"
pushd "${APP_ROOT}/panel" >/dev/null
if [ -f package-lock.json ]; then
  ${NPM_BIN} ci
else
  ${NPM_BIN} install
fi
${NPM_BIN} run lint
${NPM_BIN} run build
popd >/dev/null

if [ -n "${SLS_API_BASE:-}" ] && [ -n "${SLS_PANEL_TOKEN:-}" ]; then
  info "Smoke test scripts/tests/e2e_smoke.py"
  python "${APP_ROOT}/scripts/tests/e2e_smoke.py"
else
  info "Omitiendo smoke test: define SLS_API_BASE y SLS_PANEL_TOKEN para habilitarlo"
fi

install_unit() {
  local template="$1"
  local target="${SYSTEMD_DIR}/$(basename "$template")"
  info "Instalando $(basename "$template") en ${target}"
  sudo tee "${target}" >/dev/null <<EOF
$(sed -e "s|{{APP_ROOT}}|${APP_ROOT}|g" -e "s|{{SVC_USER}}|${SVC_USER}|g" "$template")
EOF
  sudo chmod 644 "${target}"
}

if [ "${INSTALL_SYSTEMD}" = "1" ]; then
  install_unit "${APP_ROOT}/scripts/deploy/systemd/sls-api.service"
  install_unit "${APP_ROOT}/scripts/deploy/systemd/sls-bot.service"
  install_unit "${APP_ROOT}/scripts/deploy/systemd/sls-panel.service"
  sudo systemctl daemon-reload
  sudo systemctl enable --now sls-api.service sls-bot.service
  sudo systemctl enable sls-panel.service
  info "Servicios systemd instalados. Revisa /etc/sls_bot.env antes de reiniciar."
else
  info "INSTALL_SYSTEMD=0, no se instalaron unidades systemd."
fi
