SHELL := /bin/bash
ROOT := $(CURDIR)
VENV ?= $(ROOT)/.venv
PYTHON_BIN := $(VENV)/bin/python
PIP_BIN := $(VENV)/bin/pip
NPM_BIN ?= npm
ENV_FILE ?= $(ROOT)/.env
MANAGER := $(ROOT)/scripts/manage_bot.py
METRICS_OUTPUT ?= $(ROOT)/metrics/business.prom
METRICS_MODE ?= $(SLSBOT_MODE)
FAILOVER_SERVICES ?= sls-api.service,sls-cerebro.service,sls-bot.service
FAILOVER_LOG_DIR ?= $(ROOT)/logs/failover
FAILOVER_MAX_WAIT ?= 45
FAILOVER_JOURNAL_LINES ?= 50
FAILOVER_EXECUTE ?= $(EXECUTE)
AUTOPILOT_DATASET ?= $(ROOT)/logs/test/cerebro_experience.jsonl
AUTOPILOT_RUNS ?= $(ROOT)/arena/runs/*.jsonl
AUTOPILOT_OUTPUT_JSON ?= $(ROOT)/metrics/autopilot_summary.json
AUTOPILOT_MARKDOWN ?= $(ROOT)/metrics/autopilot_summary.md
AUTOPILOT_PROM_FILE ?= $(ROOT)/metrics/autopilot.prom

ifeq ($(wildcard $(PYTHON_BIN)),)
	PYTHON_BIN := python3
	PIP_BIN := pip3
endif

export PYTHONPATH := $(ROOT)/bot

.PHONY: bootstrap deps backend-deps panel-deps run-api run-bot run-panel panel-build test lint clean encender apagar reiniciar diagnostico metrics-business failover-sim autopilot-summary

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

metrics-business: ## Genera metrics/business.prom (usar METRICS_MODE y METRICS_OUTPUT si aplica).
	$(PYTHON_BIN) scripts/tools/metrics_business.py \
		$(if $(METRICS_MODE),--mode $(METRICS_MODE),) \
		--output $(METRICS_OUTPUT)

failover-sim: ## Ejecuta el simulador de failover (usar EXECUTE=1 para reiniciar realmente los servicios).
	$(PYTHON_BIN) scripts/tools/failover_sim.py \
		--services "$(FAILOVER_SERVICES)" \
		--log-dir $(FAILOVER_LOG_DIR) \
		--max-wait $(FAILOVER_MAX_WAIT) \
		--journal-lines $(FAILOVER_JOURNAL_LINES) \
		$(if $(filter 1 true yes on,$(FAILOVER_EXECUTE)),--execute)

autopilot-summary: ## Genera resumen Autopilot/Arena 2V (dataset+ranking). Ajusta AUTOPILOT_* vars.
	$(PYTHON_BIN) scripts/tools/autopilot_summary.py \
		--dataset $(AUTOPILOT_DATASET) \
		--runs $(AUTOPILOT_RUNS) \
		--output-json $(AUTOPILOT_OUTPUT_JSON) \
		--markdown $(AUTOPILOT_MARKDOWN) \
		--prometheus-file $(AUTOPILOT_PROM_FILE)
