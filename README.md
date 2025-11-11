<<<<<<< HEAD
﻿# SLS_Bot

Panel (Next.js 14 + TS) nativo en Windows y API FastAPI que corre en VPS Linux. El repo tambien incluye stubs y utilidades IA para generar decisiones desde Bybit.

## Arquitectura
- `bot/` FastAPI + PyBit, maneja webhooks, control de riesgo, escritura en Excel y endpoints IA.
- `panel/` Next.js 14 (app router) que consume la API via `NEXT_PUBLIC_API_BASE` y `X-Panel-Token`.
- `config/` plantillas y secretos locales (no subir `config.json`).
- `logs/`, `excel/`, `models/` contienen datos generados en tiempo real y no se versionan.
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
   - Si activas el Cerebro (`cerebro.enabled=true`), define `cerebro.symbols/timeframes`, los multiplicadores `sl_atr_multiple` / `tp_atr_multiple`, un `min_confidence`, el horizonte de noticias (`news_ttl_minutes`) y al menos una entrada en `session_guards`. El bot usar? esas salidas para ajustar riesgo, leverage, stop-loss/take-profit y bloquear entradas cuando el guardia de sesi?n est? activo.
2. Copia `panel/.env.example` como `panel/.env` (Terminal VS Code local) y define `NEXT_PUBLIC_PANEL_API_TOKEN` con el token activo. Ajusta `NEXT_PUBLIC_CONTROL_AUTH_MODE` a `browser` si desarrollarás sin Nginx (pide credenciales desde la UI) o `proxy` para delegar en el reverse proxy.
3. Copia `config/config.sample.json` a `config/config.json`. El archivo ya trae un bloque `shared` y dos perfiles (`modes.test`/`modes.real`); personaliza tus llaves Bybit, rutas (`logs/{mode}`, `excel/{mode}`), `default_mode` y cualquier override por modo. Usa `SLSBOT_MODE` para alternar sin tocar el archivo (ideal para levantar simult�neamente el bot de pruebas y el real). Si trabajas en el VPS, mant�n la versi�n cifrada.
4. Ajusta el bloque `risk` dentro de `shared` para valores comunes o sobrescribe `modes.*.risk` cuando quieras reglas distintas por modo:
   - `daily_max_dd_pct` / `dd_cooldown_minutes`: pausan el bot cuando la caída diaria supera el límite.
   - `cooldown_after_losses` / `cooldown_minutes`: lógica tradicional por pérdidas consecutivas.
   - `cooldown_loss_streak` / `cooldown_loss_window_minutes` / `cooldown_loss_minutes`: nuevo cooldown inteligente que cuenta las pérdidas de la ventana móvil y detiene el bot durante `cooldown_loss_minutes` si se supera la racha.
   - `pnl_epsilon`: umbral mínimo para considerar una operación como ganadora/perdedora (evita que resultados muy pequeños rompan la racha).
   - `dynamic_risk`: habilita multiplicadores autom?ticos seg?n drawdown/equity (define `drawdown_tiers`, `min_multiplier`, `max_multiplier`, `equity_ceiling_pct`).
   - `guardrails`: límites adicionales para autopilot (`min_confidence`, `max_risk_pct`, `volatility.max_atr_pct` y `per_symbol.{max_risk_pct,max_leverage}`). Si una guardia se dispara, el bot ajusta el riesgo/leverage o bloquea la señal antes de enviar la orden.

## Modos prueba vs real
- Define `SLSBOT_MODE` (`test` o `real`) en cada servicio. Ambos procesos pueden ejecutarse en paralelo usando el mismo `config.json` gracias a los perfiles (`modes.*`).
- Ejecuta `python scripts/tools/infra_check.py --env-file .env` antes de desplegar para validar que las credenciales, rutas (`logs/{mode}`/`excel/{mode}`) y tokens est�n completos.
- El modo prueba usa las credenciales del modo demo/paper trading (`https://api-demo.bybit.com`); apunta sus rutas a `logs/test`, `excel/test` y `models/cerebro/test` para que el aprendizaje y los reportes no se mezclen con producci�n.
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
Antes de entrenar valida la calidad del dataset:
```
python scripts/tools/cerebro_dataset_check.py ^
  --dataset logs/test/cerebro_experience.jsonl ^
  --min-rows 200 ^
  --min-win-rate 0.45 ^
  --require-symbols BTCUSDT,ETHUSDT
```
`cerebro.train` también acepta `--dataset-min-rows`, `--dataset-min-win-rate`, `--dataset-require-symbols` y `--dataset-max-dominant-share` para forzar estos controles automáticamente.

## Arena / Autopilot Ranking
```
python scripts/tools/arena_rank.py runs/ \
  --min-trades 100 \
  --max-drawdown 5 \
  --target-sharpe 1.6 \
  --target-calmar 2.2 \
  --json
```
El script acepta archivos `.json` o `.jsonl` con `stats` (pnl, max_drawdown, trades, returns_avg/std, etc.), calcula Sharpe/Calmar/Profit Factor, aplica guardias (`min_trades`, `max_drawdown`, `max_drift`) y devuelve la tabla ordenada por score. Guarda los descartados con la razón para documentar por qué no calificaron.
- Si quieres un resumen integrado (dataset + ranking + métricas Prometheus + Markdown), usa `autopilot_summary.py` o `make autopilot-summary` como se explica más abajo.

## Autopilot summary / CI
```
python scripts/tools/autopilot_summary.py ^
  --dataset logs/test/cerebro_experience.jsonl ^
  --runs arena/runs/*.jsonl ^
  --min-trades 120 ^
  --max-drawdown 4.5 ^
  --output-json metrics/autopilot_summary.json ^
  --markdown metrics/autopilot_summary.md ^
  --prometheus-file metrics/autopilot.prom
```
La salida contiene:
- `dataset.summary/violations`: mismas métricas del dataset check (filas, win_rate, símbolos dominantes).
- `arena.accepted / rejected`: ranking multi-métrica usando `arena_rank`.
- Slack opcional (`SLACK_WEBHOOK_AUTOPILOT`) para avisar resultados al canal de trading.
- Markdown opcional (`--markdown`) para incluir el resumen directo en PR/Notion.
- `--prometheus-file` genera métricas (`sls_autopilot_dataset_rows`, `..._win_rate`, `..._top_score`, etc.) listas para el textfile collector.
- Puedes automatizarlo con `make autopilot-summary` (ajusta `AUTOPILOT_*` env vars) o vía `scripts/cron/autopilot_summary.sh` en systemd/cron.
El script detecta el modo y usa `logs/<mode>/cerebro_experience.jsonl` junto con `models/cerebro/<mode>` por defecto, por lo que no necesitas pasar rutas cuando sigues la convenci�n de carpetas. Solo promueve `active_model.json` si supera los umbrales y mejora la m�trica previa; al terminar puedes ejecutar `scripts/tools/promote_strategy.py` para copiar el modelo al modo real y reiniciar el dataset de pruebas.

## Security & Compliance
- `AUDIT_LOG`: todas las llamadas a `/control/{service}/{action}` se registran como JSON (`actor`, `acción`, resultado). Cambia la ruta en `.env` y replica el archivo en un storage persistente.
- Rate limiting configurable (`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`) protege los endpoints de control; un exceso devuelve `429`.
- Consulta `docs/security/politicas.md` para recomendaciones de secretos (Vault/SOPS), rotación de tokens y monitoreo del resumen Autopilot.
- Ejecuta `make security-check` para validar que `.env` y `config/config.json` tienen los secretos mínimos (AUDIT_LOG, tokens rotatorios, rate limit, rutas válidas). El comando imprime advertencias y falla si falta algún requisito crítico.
- Antes de poner credenciales reales, revisa `docs/operations/credentials_checklist.md`: resume cada secreto/env necesario por frente (Bybit, Slack, backups, Alertmanager, panel, Vault).

## Go-Live escalonado (Fase F5)
- Ejecuta `make autopilot-summary` antes de cada ventana piloto; revisa el Markdown generado (`metrics/autopilot_summary.md`) y comparte el enlace/archivo con el comité Go/No-Go.
- Checklist de producción:
  1. `systemctl status sls-bot sls-api sls-cerebro` en verde.
  2. `make failover-sim EXECUTE=1` completado en las últimas 24 h.
  3. `AUTOPILOT_SUMMARY_JSON` sin violaciones (dataset sano + ≥1 candidato aprobado).
  4. `AUDIT_LOG` limpio; no hay intentos fallidos recientes en `/control/*`.
- `make go-nogo` automatiza el ritual: genera el resumen Autopilot con los datasets reales (`GO_NOGO_AUTOPILOT_DATASET/RUNS`) y produce `metrics/deploy_plan.md` con el estado de servicios, riesgo y auditoría. Sobre-escribe las rutas vía variables si necesitas un modo distinto (ejemplo local):
  ```bash
  make go-nogo \
    GO_NOGO_AUTOPILOT_DATASET=sample_data/cerebro_experience_sample.jsonl \
    GO_NOGO_AUTOPILOT_RUNS=sample_data/arena_runs_sample.jsonl \
    GO_NOGO_RISK_STATE=logs/test/risk_state.json \
    GO_NOGO_AUDIT_LOG=logs/test/audit.log
  ```
- El panel muestra la tarjeta **Autopilot 2V** (dataset health + ranking) y la sección de Estado (cooldown/risk). Usa estos indicadores como parte del Go/No-Go.
- `scripts/tools/deploy_plan.py` genera el Markdown para cada ventana piloto a partir del resumen autopilot y la checklist (`--output-md docs/operations/deploy_plan.md`). Úsalo desde CI/cron (`make deploy-plan`) para tener el reporte listo antes del comité.

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
El panel leerá `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_PANEL_API_TOKEN` y `NEXT_PUBLIC_CONTROL_AUTH_MODE` desde `panel/.env`. La tarjeta **Cerebro IA** permite filtrar por s�mbolo/timeframe, forzar una decisi�n (POST `/cerebro/decide`) y graficar la confianza usando el historial expuesto por `/cerebro/status`. Además, la tarjeta **Autopilot 2V** consume `/autopilot/summary` y muestra la salud del dataset + top estrategias calculadas por `scripts/tools/autopilot_summary.py` (ejecuta `make autopilot-summary` o `scripts/cron/autopilot_summary.sh` para mantenerlo actualizado).
### Lint / Build
```
npm run lint
npm run build
```
`lint` usa `eslint-config-next` (core-web-vitals) y `build` valida tipos antes de generar el bundle.

## Docker (opcional)
`docker-compose.yml` levanta solo el panel en modo host. Ajusta el archivo si quieres incluir la API/control.

## Comandos utiles
- `venv\Scripts\python -m uvicorn sls_bot.app:app --reload` para desarrollo rapido.
- `npm run build && npm run start` para revisar el bundle productivo.
- `npm run lint` para validar el panel antes de publicar.
- `venv\Scripts\python -m pip install -r bot/requirements-ia.txt` para habilitar el motor IA.
- El bot escribe datos reales en `logs/decisions.jsonl`, `logs/bridge.log` y `logs/pnl.jsonl`, que el panel consume en vivo.

## Observabilidad y alertas
- **Métricas de negocio**: `make metrics-business MODE=real METRICS_OUTPUT=/var/lib/node_exporter/textfile_collector/sls_bot_business.prom` ejecuta `scripts/tools/metrics_business.py` y genera el textfile compatible con el collector de Node Exporter. Programa el target con systemd/cron para refrescarlo cada 5 min.
- **Prometheus**: copia `docs/observability/prometheus_rules.yml` a tu `rules.d` y recarga Prometheus. Se incluyen alerts para “sin trades”, “win rate bajo”, “drawdown alto” y “resumen diario ausente”.
- **Alertmanager**: parte de `docs/observabilidad/alertmanager.yml`, reemplaza el webhook y recarga. Los labels `{mode,service}` permiten rutear por entorno.
- **Grafana**: importa `docs/observabilidad/grafana/sls_bot_control_center.json`, selecciona el datasource (`DS_PROMETHEUS`) y usa la variable `$mode` para cambiar entre `test` y `real`.
- Consulta `docs/observabilidad/README.md` para ver el timer de ejemplo y comandos de validación (`promtool`, `alertmanager --dry.run`, etc.).

## Resiliencia / Failover
- `make failover-sim` ejecuta el simulador en modo dry-run: no reinicia nada, pero genera `logs/failover/failover_report_<ts>.log` con `systemctl status` y `journalctl`.
- Para un ejercicio real, ejecuta `sudo make failover-sim EXECUTE=1`. Personaliza la lista con `FAILOVER_SERVICES="sls-api.service,sls-bot.service"` y ajusta tiempos con `FAILOVER_MAX_WAIT`.
- Cambia la ruta del reporte con `FAILOVER_LOG_DIR=/var/log/sls_bot/failover`.
- Sigue el checklist descrito en `docs/operations/failover.md` para documentar hallazgos/post-mortem.

## CI/CD & Provisioning
- **GitHub Actions**: `.github/workflows/ci.yml` ejecuta `make test`, `npm run lint`, `npm run build` y publica el build del panel como artefacto. Se dispara en `push`/`pull_request` a `main` y cancela ejecuciones previas para la misma rama.
- **Provisioning Ansible**: `infra/ansible/provision.yml` instala paquetes base, clona el repo, crea el venv, instala dependencias (incluyendo IA), genera un `.env` placeholder y despliega los servicios systemd. Edita `inventory.example.ini` con tu host y ejecuta `ansible-playbook`.
- Las plantillas de systemd (`infra/ansible/templates/*.service.j2`) usan las mismas rutas que los servicios productivos: personaliza `sls_bot_root`, `sls_bot_user` y `sls_bot_env_file` vía variables o `-e`.
- Para habilitar despliegues desde Actions, configura los secrets `DEPLOY_HOST`, `DEPLOY_USER` y `DEPLOY_SSH_KEY` (clave privada con acceso SSH). El job `deploy` sólo se ejecuta si esos valores existen.

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
- Mantén `CONTROL_USER/CONTROL_PASSWORD`, `PANEL_API_TOKENS` y cualquier `.env` fuera del repo.
- Restringe CORS (`ALLOWED_ORIGINS`) a tus dominios y usa HTTPS detras de Nginx.
- Configura systemd, Nginx + Certbot y ufw (solo 22/80/443) como indica el paquete de traspaso.

=======
# SLS_Bot
>>>>>>> f91eea92f5d09a794832800818d920906f4be1be
