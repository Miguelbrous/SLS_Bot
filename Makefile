SHELL := /bin/bash
ROOT := $(CURDIR)
VENV ?= $(ROOT)/.venv
PYTHON_BIN := $(VENV)/bin/python
PIP_BIN := $(VENV)/bin/pip
NPM_BIN ?= npm
ENV_FILE ?= $(ROOT)/.env
MANAGER := $(ROOT)/scripts/manage_bot.py

ifeq ($(wildcard $(PYTHON_BIN)),)
	PYTHON_BIN := python3
	PIP_BIN := pip3
endif

export PYTHONPATH := $(ROOT)/bot

.PHONY: bootstrap deps backend-deps run-api run-bot run-panel panel-build test lint clean encender apagar reiniciar diagnostico infra-check setup-dirs rotate-artifacts health smoke monitor-check observability-up observability-down observability-check textfile-smoke autopilot-ci

bootstrap: deps panel-deps ## Crea el entorno virtual, instala dependencias backend y frontend.

deps: ## Instala dependencias del backend en el venv (usa requirements-dev).
	python3 -m venv $(VENV)
	$(PYTHON_BIN) -m pip install --upgrade pip
	$(PYTHON_BIN) -m pip install -r bot/requirements-dev.txt

backend-deps: deps ## Alias histórico; mismo comportamiento que deps.

panel-deps: ## Instala dependencias del panel (npm install).
	cd panel && $(NPM_BIN) install

run-api: ## Arranca la API de control (uvicorn app.main:app).
	cd bot && SLSBOT_MODE?=$(SLSBOT_MODE) $(PYTHON_BIN) -m uvicorn app.main:app --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8880}

run-bot: ## Arranca el webhook/servicio principal (uvicorn sls_bot.app:app).
	cd bot && SLSBOT_MODE?=$(SLSBOT_MODE) $(PYTHON_BIN) -m uvicorn sls_bot.app:app --host $${BOT_HOST:-0.0.0.0} --port $${BOT_PORT:-8080}

run-panel: ## Arranca el panel Next.js en modo desarrollo.
	cd panel && $(NPM_BIN) run dev

panel-build: ## Genera build de producción del panel.
	cd panel && $(NPM_BIN) run build

test: ## Ejecuta pytest del backend.
	SLSBOT_MODE?=$(SLSBOT_MODE) $(PYTHON_BIN) -m pytest bot/tests -q

lint: ## Ejecuta lint del panel.
	cd panel && $(NPM_BIN) run lint

clean: ## Limpia artefactos (venv, node_modules, builds).
	rm -rf $(VENV)
	rm -rf panel/node_modules panel/.next panel/out panel/.turbo

encender: ## Enciende todos los servicios via systemd (requiere VPS). Usa .env si existe.
	@python3 $(MANAGER) encender $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)

apagar: ## Detiene todos los servicios via systemd (requiere VPS).
	@python3 $(MANAGER) apagar

reiniciar: ## Reinicia servicios y muestra diagnostico resumido (requiere VPS). Usa .env si existe.
	@python3 $(MANAGER) reiniciar $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)

diagnostico: ## Obtiene estado y ultimos logs de cada servicio (requiere VPS).
	@python3 $(MANAGER) diagnostico

infra-check: ## Valida .env/config y rutas; usa --ensure-dirs=1 para crear directorios que falten.
	@$(PYTHON_BIN) scripts/tools/infra_check.py $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),) $(if $(ENSURE_DIRS),--ensure-dirs,)

setup-dirs: ## Crea directorios (logs/excel/modelos) según config activa.
	@$(PYTHON_BIN) scripts/tools/infra_check.py $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),) --ensure-dirs

rotate-artifacts: ## Mueve artefactos antiguos a archive/ (usar DAYS=14 para personalizar).
	@$(PYTHON_BIN) scripts/tools/rotate_artifacts.py $(if $(MODE),--mode $(MODE),) $(foreach inc,$(INCLUDE),--include $(inc)) $(if $(DAYS),--days $(DAYS),) $(if $(DRY_RUN),--dry-run,)

health: ## Healthcheck HTTP rápido (pasa PANEL_TOKEN/CONTROL_* si corresponde).
	@$(PYTHON_BIN) scripts/tools/healthcheck.py --base-url $${API_BASE:-http://127.0.0.1:8880} $(if $(PANEL_TOKEN),--panel-token $(PANEL_TOKEN),) $(if $(CONTROL_USER),--control-user $(CONTROL_USER),) $(if $(CONTROL_PASSWORD),--control-password $(CONTROL_PASSWORD),)

smoke: ## Smoke test completo usando scripts/tests/e2e_smoke.py.
	@SLS_API_BASE=$${API_BASE:-http://127.0.0.1:8880} \
	 SLS_PANEL_TOKEN=$(PANEL_TOKEN) \
	 SLS_CONTROL_USER=$(CONTROL_USER) \
	 SLS_CONTROL_PASSWORD=$(CONTROL_PASSWORD) \
	 $(PYTHON_BIN) scripts/tests/e2e_smoke.py

monitor-check: ## Ejecuta el monitor de arena (/arena/state + /metrics). Pensado para cron/CI.
	@$(PYTHON_BIN) scripts/ops.py monitor check \
		--api-base $${API_BASE:-http://127.0.0.1:8880} \
		$(if $(PANEL_TOKEN),--panel-token $(PANEL_TOKEN),) \
		$(if $(SLACK_WEBHOOK),--slack-webhook $(SLACK_WEBHOOK),) \
		$(if $(and $(TELEGRAM_TOKEN),$(TELEGRAM_CHAT_ID)),--telegram-token $(TELEGRAM_TOKEN) --telegram-chat-id $(TELEGRAM_CHAT_ID),) \
		$(if $(MAX_ARENA_LAG),--max-arena-lag $(MAX_ARENA_LAG),) \
		$(if $(MAX_DRAWDOWN),--max-drawdown $(MAX_DRAWDOWN),) \
		$(if $(MAX_TICKS),--max-ticks-since-win $(MAX_TICKS),) \
		$(if $(DRY_RUN),--dry-run,)

observability-up: ## Levanta Prometheus+Grafana+Alertmanager locales usando docker compose.
	docker compose -f docs/observability/docker-compose.yml --project-name sls-observability up -d

observability-down: ## Apaga el stack local de observabilidad.
	docker compose -f docs/observability/docker-compose.yml --project-name sls-observability down

observability-check: ## Valida Prometheus/Grafana/Alertmanager (requiere PROM_BASE/GRAFANA_BASE/...)
	@$(PYTHON_BIN) scripts/ops.py observability check

textfile-smoke: ## Valida los archivos .prom y fuerza fallos controlados (usa DIR=/var/lib/node_exporter/textfile_collector).
	@bash scripts/tests/cerebro_metrics_smoke.sh $(if $(DIR),--dir $(DIR),) $(if $(MAX_AGE),--max-age $(MAX_AGE),)

autopilot-ci: ## Valida dataset + dry-run del autopilot (usa MODE=test, DATASET=logs/test/cerebro_experience.jsonl).
	@MODE=$${MODE:-test}; \
	 DATASET=$${DATASET:-logs/test/cerebro_experience.jsonl}; \
	 MIN_ROWS=$${MIN_ROWS:-200}; \
	 MIN_WIN=$${MIN_WIN_RATE:-0.3}; \
	 MAX_WIN=$${MAX_WIN_RATE:-0.8}; \
	 MIN_SYMBOLS=$${MIN_SYMBOLS:-1}; \
	 MAX_AGE=$${MAX_AGE_HOURS:-0}; \
	 MIN_AUC=$${MIN_CI_AUC:-0.52}; \
	 MIN_WIN_CI=$${MIN_CI_WIN_RATE:-0.5}; \
	 SLACK=$${SLACK_WEBHOOK:-}; \
	 SLACK_USER=$${SLACK_USER:-cerebro-autopilot-ci}; \
	 EXTRA=""; \
	 if [[ -n $$SLACK ]]; then EXTRA="--slack-webhook $$SLACK --slack-user $$SLACK_USER"; fi; \
	 $(PYTHON_BIN) scripts/tests/cerebro_autopilot_ci.py \
	 	--mode $$MODE \
	 	--dataset $$DATASET \
	 	--min-rows $$MIN_ROWS \
	 	--min-win-rate $$MIN_WIN \
	 	--max-win-rate $$MAX_WIN \
	 	--min-symbols $$MIN_SYMBOLS \
	 	--max-age-hours $$MAX_AGE \
	 	--min-ci-auc $$MIN_AUC \
	 	--min-ci-win-rate $$MIN_WIN_CI \
	 	$$EXTRA
