# SLS_Bot

Panel (Next.js 14 + TS) nativo en Windows y API FastAPI que corre en VPS Linux. El repo tambien incluye stubs y utilidades IA para generar decisiones desde Bybit.

## Arquitectura
- `bot/` FastAPI + PyBit, maneja webhooks, control de riesgo, escritura en Excel y endpoints IA.
- `panel/` Next.js 14 (app router) que consume la API via `NEXT_PUBLIC_API_BASE` y `X-Panel-Token`.
- `config/` plantillas y secretos locales (no subir `config.json`).
- `logs/`, `excel/`, `models/` contienen datos generados en tiempo real y no se versionan.
- `bot/arena/` concentra la **Arena de estrategias** con 5 000 perfiles simulados, registro, ranking y
  orquestador para la “carrera” test → real (usa `bot/arena/arena.db` para ledger/state además de los JSON históricos).
- `bot/core/settings.py` centraliza la lectura de `.env`/config para compartir defaults entre CLI, loop y servicios.
- `docs/cerebro.md` describe el nuevo **Cerebro IA**, un servicio que observa al bot,
  genera features y aprende de los resultados para proponer mejoras. Act?valo
  habilitando `cerebro.enabled` en `config/config.json`; el Cerebro propondr?
  `risk_pct`, `leverage` y SL/TP din?micos, puede descartar operaciones (`NO_TRADE`)
  y ahora integra un guardia de sesiones (Asia/Europa/USA) con sentimiento NLP,
  logging/auditor?a (`/cerebro/decisions`) y un modelo ligero entrenado con tus
  propias operaciones (`bot/cerebro/train.py`) que ajusta la confianza/riesgo solo
  cuando supera los umbrales de AUC/win-rate.

## Variables de entorno
1. Copia `.env.example` como `.env` en la raiz (Terminal Windows PC) y ajusta:
   - `ALLOWED_ORIGINS`: dominios autorizados para el panel.
   - `CONTROL_USER` / `CONTROL_PASSWORD`: credenciales Basic para `/control/*` cuando trabajes en local.
   - `PANEL_API_TOKENS`: lista separada por comas en formato `token@YYYY-MM-DD`. Puedes dejar un token sin fecha para la rotación actual y mantener el anterior hasta su caducidad. La API acepta cualquiera que no haya expirado.
   - `PANEL_API_TOKEN`: compatibilidad hacia atrás si aún manejas un solo token.
   - `TRUST_PROXY_BASIC` / `PROXY_BASIC_HEADER`: activa (`1`) cuando Nginx ya protege `/control/*` con Basic Auth y reenvía el usuario en `X-Forwarded-User`.
   - `SLSBOT_MODE`: `test` o `real`. Define qu� perfil del `config.json` se aplica y habilita directorios independientes (`logs/{mode}`, `excel/{mode}`, `models/{mode}`...).
   - Variables Bybit (`BYBIT_*`) para el bot real y rutas (`SLSBOT_CONFIG`).
   - Si activas el Cerebro (`cerebro.enabled=true`), define `cerebro.symbols/timeframes`, los multiplicadores `sl_atr_multiple` / `tp_atr_multiple`, la confianza mínima y sus límites (`min_confidence`, `confidence_min`, `confidence_max`), el TTL de cache (`data_cache_ttl`), los parámetros de anomalías (`anomaly_*`), el horizonte de noticias (`news_ttl_minutes`), los bloques `funding_feeds` (sesgo de funding), `orderflow_feeds` (profundidad `/v5/market/orderbook`) y `onchain_feeds` (mempool/hash rate vía Blockchair), y al menos una entrada en `session_guards`. El bot usará esas salidas para ajustar riesgo, leverage, stop-loss/take-profit y bloquear entradas cuando el guardia de sesión esté activo. Exporta `SLS_CEREBRO_AUTO_TRAIN=1` si quieres disparar entrenamientos automáticos cada `auto_train_interval` trades.
2. Copia `panel/.env.example` como `panel/.env` (Terminal VS Code local) y define `NEXT_PUBLIC_PANEL_API_TOKEN` con el token activo. Ajusta `NEXT_PUBLIC_CONTROL_AUTH_MODE` a `browser` si desarrollarás sin Nginx (pide credenciales desde la UI) o `proxy` para delegar en el reverse proxy. Si ya tienes Grafana/Prometheus expuestos, completa `NEXT_PUBLIC_GRAFANA_BASE_URL`, los UIDs `NEXT_PUBLIC_GRAFANA_ARENA_UID` / `NEXT_PUBLIC_GRAFANA_BOT_UID` y (opcional) `NEXT_PUBLIC_PROMETHEUS_BASE_URL` para que la tarjeta de Observabilidad muestre sparklines reales y enlaces directos a tus dashboards.
3. Copia `config/config.sample.json` a `config/config.json`. El archivo ya trae un bloque `shared` y dos perfiles (`modes.test`/`modes.real`); personaliza tus llaves Bybit, rutas (`logs/{mode}`, `excel/{mode}`), `default_mode` y cualquier override por modo. Usa `SLSBOT_MODE` para alternar sin tocar el archivo (ideal para levantar simult�neamente el bot de pruebas y el real). Si trabajas en el VPS, mant�n la versi�n cifrada.
4. Ajusta el bloque `risk` dentro de `shared` para valores comunes o sobrescribe `modes.*.risk` cuando quieras reglas distintas por modo:
   - `daily_max_dd_pct` / `dd_cooldown_minutes`: pausan el bot cuando la caída diaria supera el límite.
   - `cooldown_after_losses` / `cooldown_minutes`: lógica tradicional por pérdidas consecutivas.
   - `cooldown_loss_streak` / `cooldown_loss_window_minutes` / `cooldown_loss_minutes`: nuevo cooldown inteligente que cuenta las pérdidas de la ventana móvil y detiene el bot durante `cooldown_loss_minutes` si se supera la racha.
   - `pnl_epsilon`: umbral mínimo para considerar una operación como ganadora/perdedora (evita que resultados muy pequeños rompan la racha).
   - `dynamic_risk`: habilita multiplicadores autom?ticos seg?n drawdown/equity (define `drawdown_tiers`, `min_multiplier`, `max_multiplier`, `equity_ceiling_pct`).

## Modos prueba vs real
- Define `SLSBOT_MODE` (`test` o `real`) en cada servicio. Ambos procesos pueden ejecutarse en paralelo usando el mismo `config.json` gracias a los perfiles (`modes.*`).
- Ejecuta `python scripts/tools/infra_check.py --env-file .env` antes de desplegar para validar que las credenciales, rutas (`logs/{mode}`/`excel/{mode}`) y tokens est�n completos.
- El modo prueba usa claves y balances de testnet; apunta sus rutas a `logs/test`, `excel/test` y `models/cerebro/test` para que el aprendizaje y los reportes no se mezclen con producci�n.
- El modo real consume solo modelos promovidos. Puedes copiar artefactos manualmente o usar `python scripts/tools/promote_strategy.py --source-mode test --target-mode real` para mover `active_model.json`, validar m�tricas y rotar el dataset de prueba en un paso.
- Tras cada promoci�n, entrena un nuevo candidato en prueba (`python -m cerebro.train --mode test ...`) para que siempre haya una estrategia lista para subir a real.
- Los logs (`logs/{mode}`) y Excel (`excel/{mode}`) quedan aislados, as� que revisa el panel apuntando al API correspondiente si quieres observar cada modo por separado.

## Requisitos
- Python 3.11+ (evita problemas con dependencias cientificas).
- Node.js 20 LTS para el panel.
- `pip` y `npm` disponibles en las terminales que uses.

## Backend FastAPI (API de control + bot)
### Instalar dependencias (Terminal Windows PC)
```
cd C:\Users\migue\Desktop\SLS_Bot
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r bot/requirements-dev.txt
```
`bot/requirements-ia.txt` agrega numpy/pandas/sklearn/xgboost si necesitas entrenar IA.

### API de control (panel) - local
```
cd C:\Users\migue\Desktop\SLS_Bot\bot
set ALLOWED_ORIGINS=http://localhost:3000
set CONTROL_USER=panel
set CONTROL_PASSWORD=cambia_est0
set PANEL_API_TOKENS=panel_token@2099-12-31
set TRUST_PROXY_BASIC=0
..\venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8880
```
Con `NEXT_PUBLIC_CONTROL_AUTH_MODE=browser` el panel seguirá solicitando usuario/contraseña para `/control/*`. En producción cambia a `proxy` y deja que Nginx firme las peticiones con `X-Forwarded-User`.

### Bot trading (`sls_bot.app`) - local
```
cd C:\Users\migue\Desktop\SLS_Bot\bot
set PYTHONPATH=%cd%
set SLSBOT_CONFIG=..\config\config.json
set PORT=8080
..\venv\Scripts\uvicorn sls_bot.app:app --host 127.0.0.1 --port %PORT%
```

### Despliegue en VPS (Terminal VS Code remoto)
```
cd ~/SLS_Bot/bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SLSBOT_CONFIG=/root/SLS_Bot/config/config.json
export CONTROL_USER=panel
export CONTROL_PASSWORD='super-seguro'
export PANEL_API_TOKENS='token_prod@2025-12-31,token_backup'
export TRUST_PROXY_BASIC=1
uvicorn app.main:app --host 0.0.0.0 --port 8880
```
Integra con systemd y Nginx siguiendo `scripts/deploy/README.md` para que el proxy maneje Basic Auth y rote tokens sin reiniciar la API.

### Pruebas automatizadas
```
cd C:\Users\migue\Desktop\SLS_Bot
venv\Scripts\python -m pytest bot/tests
SLS_API_BASE=http://127.0.0.1:8880 ^
SLS_PANEL_TOKEN=panel_token ^
SLS_CONTROL_USER=panel ^
SLS_CONTROL_PASSWORD=cambia_est0 ^
venv\Scripts\python scripts/tests/e2e_smoke.py
```
Las pruebas de pytest usan `config/config.sample.json`, escriben `logs/test_pnl.jsonl` y fijan `SLS_SKIP_TIME_SYNC=1`. El script `scripts/tests/e2e_smoke.py` realiza un smoke test end-to-end contra una API en ejecución verificando `/health`, `/pnl/diario` y `/control`.

## Modelo Cerebro (entrenamiento y despliegue)
```
cd C:/Users/migue/Desktop/SLS_Bot/bot
set SLSBOT_MODE=test
python -m cerebro.train --mode test --min-auc 0.55 --min-win-rate 0.55
```
El script detecta el modo y usa `logs/<mode>/cerebro_experience.jsonl` junto con `models/cerebro/<mode>` por defecto, por lo que no necesitas pasar rutas cuando sigues la convenci�n de carpetas. Solo promueve `active_model.json` si supera los umbrales y mejora la m�trica previa; al terminar puedes ejecutar `scripts/tools/promote_strategy.py` para copiar el modelo al modo real y reiniciar el dataset de pruebas.

## Servicio Cerebro IA (systemd)
```
bash APP_ROOT=/opt/SLS_Bot SVC_USER=sls ./scripts/deploy/install_cerebro_service.sh
```
El script copia `scripts/deploy/systemd/sls-cerebro.service`, reemplaza `{{APP_ROOT}}/{{SVC_USER}}`, recarga systemd y deja ejecut�ndose `python -m cerebro.service --loop`. Tras habilitarlo valida el estado con:
```
curl -fsS http://127.0.0.1:${SLS_API_PORT:-8880}/cerebro/status | jq '.time'
```


## Automatización de despliegue
- `scripts/deploy/bootstrap.sh` prepara el entorno Python/Node, ejecuta `pytest`, `npm run lint`/`build` y opcionalmente instala los servicios systemd si exportas `INSTALL_SYSTEMD=1 APP_ROOT=/opt/SLS_Bot SVC_USER=sls`.
- `scripts/deploy/systemd/*.service` incluyen plantillas para `sls-api`, `sls-bot` y `sls-panel`. El script reemplaza `{{APP_ROOT}}` y `{{SVC_USER}}` automáticamente; si lo haces a mano, ajusta esas cadenas y copia los archivos a `/etc/systemd/system/`.
- `scripts/deploy/README.md` describe cómo generar `/etc/sls_bot.env`, configurar Nginx (Basic Auth + cabecera `X-Forwarded-User`) y rotar tokens sin downtime.

## Panel Next.js
### Instalar deps (Terminal VS Code local)
```
cd C:\Users\migue\Desktop\SLS_Bot\panel
npm install
```
### Ejecutar
```
npm run dev
```
El panel leerá `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_PANEL_API_TOKEN` y `NEXT_PUBLIC_CONTROL_AUTH_MODE` desde `panel/.env`. La tarjeta **Cerebro IA** permite filtrar por s�mbolo/timeframe, forzar una decisi�n (POST `/cerebro/decide`) y graficar la confianza usando el historial expuesto por `/cerebro/status`.
### Lint / Build
```
npm run lint
npm run build
```
`lint` usa `eslint-config-next` (core-web-vitals) y `build` valida tipos antes de generar el bundle.

## Docker (opcional)
`docker-compose.yml` levanta solo el panel en modo host. Ajusta el archivo si quieres incluir la API/control.

## Comandos utiles
- `python scripts/ops.py up` enciende API, bot, Cerebro y la estrategia (`down`, `status`, `logs`, `arena tick/run/promote/ranking/state/ledger`, `qa` funcionan igual). El CLI usa los mismos scripts internos, pero unifica el flujo operativo.
- `python scripts/ops.py qa` corre pytest y `npm run lint` (agrega `--skip-panel` si no quieres correr el lint del panel).
- `python scripts/ops.py infra --env-file .env.local --ensure-dirs` corre `infra_check.py`, valida tokens/credenciales y opcionalmente crea los directorios faltantes por modo.
- `python scripts/ops.py cerebro dataset --mode test --rows 300 --overwrite` genera datasets sintéticos para reentrenar el Cerebro sin depender de fills reales; `--bias` ajusta el sesgo de PnL.
- `python scripts/ops.py cerebro promote --mode real --metric auc --min-value 0.65` promueve el mejor modelo registrado a `active_model.json` sin buscar el script manualmente.
- `python scripts/ops.py cerebro train --mode test --epochs 300 --min-auc 0.6 --dry-run` entrena/evalúa el modelo ligero (usa `--no-promote` para solo guardar artefactos o `--dataset`/`--output-dir` para rutas personalizadas).
- `python scripts/ops.py deploy bootstrap --install-systemd` corre `scripts/deploy/bootstrap.sh` con las variables apropiadas (`APP_ROOT`, `SVC_USER`) y recompila backend + panel en un solo paso.
- `python scripts/ops.py deploy rollout --restart --services sls-api.service sls-bot.service` reinicia las unidades systemd clave (opcionalmente con `--daemon-reload`).
- `python scripts/ops.py monitor check --api-base https://api --panel-token XXX --slack-webhook https://hooks.slack...` ejecuta el monitor que valida `/arena/state` + `/metrics` y envía alertas (Slack o Telegram) cuando hay drawdown o ticks pegados. Puedes ajustar los nuevos umbrales `--min-arena-sharpe` y `--min-decisions-per-min` para monitorear también la salud del panel/Cerebro.
- `make monitor-check PANEL_TOKEN=token SLACK_WEBHOOK=...` sirve como wrapper listo para cron/CI; reutiliza `python scripts/ops.py monitor check` respetando los umbrales (`MAX_ARENA_LAG`, `MAX_DRAWDOWN`, `MAX_TICKS`).
- `python scripts/ops.py arena promote strat_42 --min-trades 80 --min-sharpe 0.4 --max-drawdown 25` exporta ganadores solo si superan las validaciones de Sharpe/drawdown/trades (usa `--force` para ignorarlas).
- `python scripts/ops.py arena promote-real strat_42 --min-trades 80 --min-sharpe 0.4 --max-drawdown 25 --source-mode test --target-mode real` genera el paquete de revisión y, si pasa las validaciones, promueve el modelo de Cerebro a real (usa `--skip-dataset-rotation` cuando no quieras archivar el dataset de test).
- `python scripts/ops.py arena notes add strat_42 --message "Afinar TP a 1.5R"` registra notas de experimento (usa `arena notes list` para consultarlas desde CLI sin abrir la DB).
- `python scripts/ops.py arena ledger strat_42 --limit 200 --csv tmp_logs/ledger.csv` lista el ledger directo desde `arena.db` y opcionalmente lo exporta a CSV, alineado con el filtro/export que ahora ofrece el panel `/arena`.
- `python scripts/ops.py arena stats strat_42 --json` devuelve un resumen estadístico (trades, wins/losses, win rate, PnL, max DD) del ledger local; útil para comparar contra los agregados del panel o automatizar reportes.
- `/metrics` expone métricas Prometheus de la API (instrumentadas con `prometheus-fastapi-instrumentator`).
- `venv\Scripts\python -m uvicorn sls_bot.app:app --reload` para desarrollo rapido.
- `npm run build && npm run start` para revisar el bundle productivo.
- `npm run lint` para validar el panel antes de publicar.
- `venv\Scripts\python -m pip install -r bot/requirements-ia.txt` para habilitar el motor IA.
- El bot escribe datos reales en `logs/decisions.jsonl`, `logs/bridge.log` y `logs/pnl.jsonl`, que el panel consume en vivo.
- `make infra-check` valida `.env`/`config` y muestra rutas por modo (`make infra-check ENSURE_DIRS=1` también crea los directorios faltantes).
- `python scripts/tools/generate_cerebro_dataset.py --mode test --rows 200 --overwrite` crea un dataset sintético para entrenar el Cerebro en local.
- `python scripts/tools/promote_best_cerebro_model.py --mode test --metric auc --min-value 0.6` promueve el mejor artefacto a `active_model.json`.
- Panel `/alerts` resume `order_error`, bloqueos y heartbeats; requiere `X-Panel-Token`.

## Arena de estrategias y scalper vivo
- `bot/arena/registry.json` contiene 5 000 estrategias simuladas (scalp/intra/swing/macro/quant) que compiten
  por alcanzar la meta actual (100 € iniciales +50 € por victoria). Ejecuta `PYTHONPATH=. python scripts/arena_bootstrap.py`
  para regenerar o ampliar el registro.
- `bot/arena/league_manager.py` + `bot/arena/simulator.py` permiten correr “ticks” de simulación y actualizar
  `bot/arena/ranking_latest.json` mediante `python -m bot.arena` o `scripts/run_arena_tick.sh`.
- Endpoints nuevos del panel: `GET /arena/ranking` y `GET /arena/state` (requieren token del panel) leen esos
  archivos para mostrar el leaderboard y el estado de la meta actual.
- `bot/strategies/scalp_rush.py` es la nueva estrategia agresiva para testnet (1m). Actívala exportando
  `STRATEGY_ID=scalp_rush_v1` y `STRATEGY_INTERVAL_SECONDS=30` en tu `.env` (el gestor los toma como default) o usando
  `scripts/manage.sh encender-estrategia`.
- `micro_scalp_v1` redujo los filtros (EMA ≥3 bps, RSI 40-60) para registrar experiencias más rápido en testnet
  mientras la Arena sigue aprendiendo en paralelo.
- `python scripts/ops.py arena run --interval 300` ejecuta el servicio de arena embebido en loop (ya no dependes de cron) y actualiza `ranking_latest.json` tras cada tick.
- `cup_state.json` guarda ahora `last_tick_ts`, `ticks_since_win`, `drawdown_pct` y alimenta las métricas `sls_arena_*`, `sls_bot_drawdown_pct` y `sls_cerebro_decisions_per_min`, útiles para Grafana o para el monitor (`make monitor-check`).

### Tips operativos rápidos
- Añade en `.env`:
  ```
  STRATEGY_ID=scalp_rush_v1
  STRATEGY_INTERVAL_SECONDS=30
  ```
  para que el loop cargue el scalper tras cada `run SLS_Bot start`.
- Programa `scripts/run_arena_tick.sh` (cron/systemd) para refrescar `bot/arena/cup_state.json` y `ranking_latest.json`,
  que consumen los endpoints `/arena/state` y `/arena/ranking`.
- Promueve ganadores con `python scripts/promote_arena_strategy.py <strategy_id> --min-trades 60 --min-sharpe 0.4 --max-drawdown 25`; la exportación se bloquea si no pasa los umbrales (usa `--force` para omitirlos). El paquete incluye `validation.json` con los métricos usados.
- Registra bitácoras rápidas con `python scripts/ops.py arena notes add <id> --message "..."` o vía `POST /arena/notes`; consúltalas con `arena notes list` o `GET /arena/notes?strategy_id=<id>`.
- Panel `/arena` muestra ranking completo (incluye Sharpe/MaxDD), ledger, notas y expone acciones rápidas para forzar ticks (`POST /arena/tick`) y exportar paquetes (`POST /arena/promote`).
- El detalle del ledger dentro del panel permite filtrar operaciones (todo/ganadoras/perdedoras), exportar el histórico a CSV con un clic y buscar notas por autor o texto, así puedes documentar hallazgos antes de promover. El ranking incluye filtros adicionales (categoría, búsqueda por ID/nombre, mínimos de trades/score) y muestra agregados (Sharpe/score promedio, wins del top 10).

## Operación controlada y automatizaciones
- `scripts/run_testnet_session.sh` levanta el stack completo en modo testnet (`SLSBOT_MODE=test`, `STRATEGY_ID=scalp_rush_v1`) y deja log en `tmp_logs/testnet_session.log`. Ideal para sesiones de recolección de datos antes de usar capital real.
- `scripts/cron/cerebro_train.sh` es un hook para cron/systemd: lee variables `CEREBRO_TRAIN_*` y ejecuta `python scripts/ops.py cerebro train ...`, registrando la salida en `tmp_logs/cerebro_train.log`.
- `scripts/cron/cerebro_ingest.sh` ejecuta `python scripts/ops.py cerebro ingest` con las variables `CEREBRO_INGEST_*` (símbolos, timeframes, límites, flags `include_*`) y deja el JSON en `tmp_logs/` para auditar la ingesta sin levantar todo el servicio.
- `python scripts/tools/arena_candidate_report.py --min-sharpe 0.4 --min-trades 80 --top 5` genera un informe (tabla) con las estrategias más sanas para mover a testnet antes de promoverlas.
- `python scripts/ops.py cerebro ingest --symbols BTCUSDT,ETHUSDT --include-news --include-orderflow --include-funding --include-onchain --output tmp_logs/cerebro_ingestion.json` calienta los data sources del Cerebro (market/news/macro/orderflow/funding/on-chain) y guarda un snapshot JSON listo para auditar la ingesta sin encender el servicio completo. Usa `--funding-symbols` / `--onchain-symbols` para subconjuntos específicos y combina `--require-sources market,funding,onchain` + `--min-market-rows <n>` para fallar en cron/CI cuando falte una fuente crítica. Con `--prometheus-file /var/lib/node_exporter/cerebro_ingest.prom` generas métricas (`cerebro_ingest_success`, `..._rows{source="market"}`) y con `--slack-webhook ... --slack-user cerebro-ingest --slack-timeout 8 --slack-proxy http://proxy:8080` notificas el resultado incluso detrás de proxys corporativos.
- `python scripts/tools/setup_textfile_collector.py --dir /var/lib/node_exporter/textfile_collector` crea los placeholders `cerebro_ingest.prom` / `cerebro_autopilot.prom` y te recuerda exportar `NODE_EXPORTER_TEXTFILE_DIR` para que los cronjobs usen el textfile collector real de Node Exporter. Luego ejecuta `python scripts/tests/prometheus_textfile_check.py --file /var/lib/node_exporter/textfile_collector/cerebro_ingest.prom --require-metric cerebro_ingest_success` para validar permisos y frescura de los archivos.
- ¿Quieres probar las alertas? Usa `python scripts/tests/cerebro_ingest_failure_sim.py --prometheus-file /var/lib/node_exporter/textfile_collector/cerebro_ingest.prom --extra-args --slack-webhook https://hooks.slack...` para forzar una ingesta fallida (se usa `--require-sources fake_source`). Deberías ver `cerebro_ingest_success 0` en el `.prom` y una alerta en Slack.
- Para el autopilot tienes un simulador equivalente: `python scripts/tests/cerebro_autopilot_failure_sim.py --prometheus-file /var/lib/node_exporter/textfile_collector/cerebro_autopilot.prom --extra-args --slack-webhook https://hooks.slack... --slack-user cerebro-autopilot` fuerza un error antes de entrenar (usa `--min-rows 999999`). Úsalo tras setear cron o después de rotar accesos a Slack para confirmar que las métricas/reportes siguen vivos.
- Cuando quieras validar ambos textfiles de una sola vez (ideal para cron/CI) ejecuta `python scripts/tests/prometheus_textfile_suite.py --dir /var/lib/node_exporter/textfile_collector --max-age-minutes 20`. Internamente reusa el verificador granular pero asegura que tanto `cerebro_ingest.prom` como `cerebro_autopilot.prom` estén presentes y frescos.
- `bash scripts/tests/cerebro_metrics_smoke.sh --dir /var/lib/node_exporter/textfile_collector --max-age 30` (o `make textfile-smoke DIR=/var/lib/node_exporter/textfile_collector`) ejecuta todo el pipeline: valida los `.prom`, fuerza fallos en ingest/autopilot y vuelve a chequear que Node Exporter pueda leerlos. Si necesitas pasar flags adicionales a los simuladores (por ejemplo Slack), exporta `CEREBRO_SMOKE_INGEST_ARGS="--slack-webhook https://hooks.slack... --slack-user cerebro-ingest"` y `CEREBRO_SMOKE_AUTOP_ARGS="--slack-webhook ... --slack-user cerebro-autopilot"` antes de ejecutar el smoke.
- `python scripts/tests/cerebro_autopilot_dataset_check.py --dataset logs/test/cerebro_experience.jsonl --min-rows 200 --min-win-rate 0.3 --max-win-rate 0.8` analiza el dataset del Cerebro antes de entrenar (filas, balance de pnl, symbols únicos, antigüedad). Puedes integrarlo en cron/CI para asegurarte de no entrenar con datos sesgados.
- `python scripts/tests/cerebro_autopilot_ci.py --mode test --dataset logs/test/cerebro_experience.jsonl --min-rows 200 --min-ci-auc 0.52 --min-ci-win-rate 0.5 --summary-json tmp_logs/cerebro_autopilot_ci.json` ejecuta el pipeline completo (dataset check + `bot.cerebro.train --dry-run`) y opcionalmente notifica a Slack. El Makefile expone `make autopilot-ci` para correrlo localmente con overrides (`SLACK_WEBHOOK`, `MODE`, `DATASET`, etc.).
- El workflow `ci.yml` ya incluye un step “Cerebro autopilot dataset + dry-run” que llama a ese script. Si añades el secreto `SLACK_WEBHOOK_CEREBRO` en GitHub, recibirás una alerta automática cuando falle la validación de dataset o cuando `auc`/`win_rate` se salgan de los umbrales definidos.
- `python scripts/ops.py cerebro autopilot --mode test --dataset logs/cerebro_experience.jsonl --min-rows 300 --backfill-rows 400` valida que el dataset tenga suficientes filas (genera sintéticos si falta) y luego lanza `bot.cerebro.train` con los parámetros deseados. Ahora, por defecto, corre un sanity check del dataset (`--dataset-min-win-rate`, `--dataset-max-win-rate`, `--dataset-min-symbols`, `--dataset-max-age-hours`); usa `--skip-dataset-check` si necesitas omitirlo puntualmente.
- Añade `--summary-json tmp_logs/cerebro_autopilot_summary.jsonl --summary-append` (o exporta `CEREBRO_AUTO_SUMMARY_FILE`/`CEREBRO_AUTO_SUMMARY_APPEND`) para guardar un histórico JSONL de cada corrida con métricas y dataset stats; los textos de Slack y el `.prom` ahora incluyen win rate y edad del dataset.
- `python scripts/ops.py cerebro autopilot ... --prometheus-file /var/lib/node_exporter/cerebro_autopilot.prom --slack-webhook https://hooks.slack... --slack-user cerebro-autopilot` expone métricas (`cerebro_autopilot_success`, `..._metric{name="auc"}`) y envía un resumen a Slack (éxito/fallo + métricas). El log estructurado (`--log-file tmp_logs/cerebro_autopilot.log`) incluye todo el payload y la duración.
- `scripts/cron/cerebro_autopilot.sh` lee ahora `CEREBRO_AUTO_PROM_FILE`, `CEREBRO_AUTO_SLACK_WEBHOOK`, `CEREBRO_AUTO_SLACK_USER`, `CEREBRO_AUTO_REQUIRE_PROMOTE`, `CEREBRO_AUTO_MAX_DATASET_AGE_MIN`, `CEREBRO_AUTO_DATASET_MIN_WIN_RATE`, `CEREBRO_AUTO_DATASET_MAX_WIN_RATE`, `CEREBRO_AUTO_DATASET_MIN_SYMBOLS`, `CEREBRO_AUTO_DATASET_MAX_AGE_HOURS` y `CEREBRO_AUTO_SKIP_DATASET_CHECK` además de las variables previas (`CEREBRO_AUTO_MIN_ROWS`, `..._BACKFILL`, etc.) para agendarlo vía cron/systemd sin escribir flags manualmente. Su contraparte `scripts/cron/cerebro_ingest.sh` también respeta `CEREBRO_INGEST_SLACK_USER`, `CEREBRO_INGEST_SLACK_TIMEOUT`, `CEREBRO_INGEST_SLACK_PROXY` y `CEREBRO_INGEST_PROM_FILE`, por lo que puedes enrutar las alertas a Slack pasando por un proxy o exportar métricas al textfile collector sin tocar el script.
- Consulta `docs/observability.md` para integrar Prometheus/Grafana, programar `ops monitor check` y extender el pipeline CI recién añadido (`.github/workflows/ci.yml`).
- `make observability-up` levanta Prometheus + Grafana + Alertmanager usando `docs/observabilidad/docker-compose.yml` (usa `make observability-down` para apagarlos).
- `make observability-check` o `python scripts/ops.py observability check --prom-base http://127.0.0.1:9090 --grafana-base http://127.0.0.1:3000` verifican que Prometheus/Grafana/Alertmanager estén vivos y que las reglas/métricas esperadas estén cargadas (smoke que corre en CI). Usa `--grafana-user/--grafana-password` y `--alertmanager-base` cuando quieras probar instancias protegidas.
- Edita `docs/observability/alertmanager.yml` para colocar tu Webhook real de Slack (el repo incluye un placeholder `https://hooks.slack.com/services/CHANGE/ME/NOW` que sólo sirve para pruebas locales).
- Dashboards listos en `docs/observabilidad/grafana/` y reglas en `docs/observabilidad/prometheus_rules.yml`: impórtalos en Grafana/Prometheus y conecta Alertmanager para recibir avisos (`ArenaLagHigh`, `BotDrawdownCritical`, `CerebroSilent`, etc.).
- Endpoint nuevo `/observability/summary` (token panel) devuelve los indicadores del bot/Cerebro/Arena que el panel muestra en la tarjeta “Observabilidad”.

## Frentes débiles actuales
- **Panel / Observabilidad:** el bundle ya separa el gráfico y el detalle de ledger como chunks dinámicos (`ChartCard`, `ArenaDetail`), y `ANALYZE=true npm run build` genera `panel/.next/bundle-report.html` para auditar pesos. Falta consumir esas métricas dentro del panel (por ejemplo, enlazando a Grafana o renderizando tarjetas con datos de Prometheus) para evitar saltar de herramienta.
- **Cerebro IA / Ingestas:** ya contamos con feeds `market/news/macro/orderflow` y ahora también `funding` + `onchain` con toggles específicos desde `ops cerebro ingest`, pero sigue pendiente automatizar los entrenamientos (`ops cerebro train`) desde CI/cron con datasets validados antes de promover modelos y cablear más métricas operativas al dashboard para auditar cada feed en vivo.
- **Observabilidad / CI:** ya existe `.github/workflows/ci.yml` con `pytest`, `npm run lint` y `python scripts/ops.py monitor check --dry-run`, además del manual `docs/observability.md`; sigue pendiente instrumentar dashboards Prometheus/Grafana y alarmas externas que consuman `sls_arena_*`, `sls_bot_drawdown_pct` y `sls_cerebro_decisions_per_min`.

## Webhook HTTPS y prueba en Bybit Testnet

- **Dominio listo:** `api.slstudominio.com` apunta al VPS. Nginx (`/etc/nginx/sites-available/sls_api.conf`) proxyea `/webhook` y `/ia/signal` tanto por HTTP como por HTTPS (Certbot renueva automáticamente los certificados).
- **Endpoint activo:** usa `https://api.slstudominio.com/webhook` para las alertas de TradingView. El bot valida/ajusta TP y SL antes de enviar la orden (verás `tp_sl_applied …` en `logs/test/bridge.log`).
- **Prueba manual:**
  ```bash
  curl -X POST https://api.slstudominio.com/webhook \
       -H 'Content-Type: application/json' \
       -d '{
             "signal": "SLS_LONG_ENTRY",
             "symbol": "BTCUSDT",
             "tf": "15m",
             "risk_pct": 1,
             "post_only": false,
             "order_type": "LIMIT",
             "time_in_force": "GTC",
             "price": 1882071.6,
             "take_profit": 1882071.6,
             "stop_loss": 1808087.8
           }'
  ```
  Usa un precio por encima del `markPrice` (por ejemplo `mark × 1.03`) para forzar la ejecución inmediata en testnet.
- **Cierre reduce-only:**
  ```bash
  curl -X POST https://api.slstudominio.com/webhook \
       -H 'Content-Type: application/json' \
       -d '{"signal":"SLS_EXIT","symbol":"BTCUSDT","tf":"15m"}'
  ```
  El bot envía un market reduce-only; Bybit registra el PnL en “Órdenes completadas” / “P&L”.
- **Diagnóstico rápido:** `tail -f logs/test/bridge.log` permite vigilar `tp_sl_applied`, `order`, `close` y cualquier `order_error` devuelto por Bybit.
- `make setup-dirs` fuerza la creación de `logs/{mode}`, `excel/{mode}` y `models/cerebro/{mode}` según la configuración activa.
- `make rotate-artifacts DAYS=14` archiva logs/modelos antiguos en `logs/*/archive` y `models/cerebro/*/archive`.
- `make health PANEL_TOKEN=... CONTROL_USER=... CONTROL_PASSWORD=...` ejecuta un ping rápido a `/health`, `/status`, `/cerebro/status` y `/control/sls-bot/status`.
- `make smoke PANEL_TOKEN=... CONTROL_USER=... CONTROL_PASSWORD=...` corre `scripts/tests/e2e_smoke.py` contra el despliegue activo.
- `python3 scripts/manage_bot.py encender --retries 3 --retry-delay 10` reintenta acciones systemd automáticamente cuando fallan.

## Estructura
```
bot/
  sls_bot/
  requirements*.txt
  tests/
panel/
  app/
  package.json
config/
  config.sample.json
logs/ (ignorado)
excel/ (ignorado)
```

## Notas de seguridad
- Nunca publiques `config/config.json`, `.env` ni `panel/.env`.
- Mantén `CONTROL_USER/CONTROL_PASSWORD`, `PANEL_API_TOKENS` y cualquier `.env` fuera del repo. Habilita los rate limits (`CONTROL_RATE_LIMIT_MAX`, `CONTROL_RATE_LIMIT_WINDOW`, `PANEL_RATE_LIMIT_MAX`, `PANEL_RATE_LIMIT_WINDOW`) y sus equivalentes en `config/config.json` para cubrir `/control/*` y `X-Panel-Token`.
- Restringe CORS (`ALLOWED_ORIGINS`) a tus dominios y usa HTTPS detras de Nginx.
- Si defines `WEBHOOK_SHARED_SECRET`, el backend exigirá `X-Webhook-Signature` (HMAC-SHA256) en `/webhook` y `/ia/signal`.
- Configura systemd, Nginx + Certbot y ufw (solo 22/80/443) como indica el paquete de traspaso.
