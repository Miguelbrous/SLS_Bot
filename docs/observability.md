# Observabilidad y monitoreo

## Métricas Prometheus
- La API expone `/metrics` (Prometheus). Se incluyen `sls_arena_*`, `sls_bot_drawdown_pct`, `sls_cerebro_decisions_per_min` y métricas básicas de FastAPI.
- Use `/observability/summary` (requiere token del panel) para obtener un snapshot JSON listo para el panel, con meta de la arena, drawdown del bot y decisiones/minuto del Cerebro.
- Ejemplo `prometheus.yml`:
  ```yaml
  scrape_configs:
    - job_name: "sls_bot"
      static_configs:
        - targets: ["127.0.0.1:8880"]
  ```
- Importa los endpoints a Grafana y crea paneles para: drawdown, ticks sin campeones, decisiones/minuto y estado de `/health`.

## Dashboards Grafana
- Importa los dashboards JSON ubicados en `docs/observability/grafana/`:
  - `arena_dashboard.json`: muestra drawdown, meta y estado de la arena (ticks sin campeón, envejecimiento del tick, decisiones/min del Cerebro) y ahora también métricas extra expuestas por el panel (Sharpe/score promedio, count de estrategias).
  - `bot_cerebro_dashboard.json`: monitorea drawdown del bot, latencias HTTP y actividad del Cerebro.
- Desde Grafana: *Dashboards → Import → Upload JSON* y selecciona el archivo (si no usas el provisioning). Usa el datasource Prometheus configurado para `/metrics`.
- Si quieres exponer enlaces rápidos desde el panel, define `NEXT_PUBLIC_GRAFANA_BASE_URL` y los UIDs (`NEXT_PUBLIC_GRAFANA_ARENA_UID`, `NEXT_PUBLIC_GRAFANA_BOT_UID`) en `panel/.env`.
- Para que el panel pinte sparklines directamente desde Prometheus, completa también `NEXT_PUBLIC_PROMETHEUS_BASE_URL` con la URL de tu Prom (`http://localhost:9090`, etc.).

## Stack local (docker compose)
- `docs/observability/docker-compose.yml` levanta Prometheus + Alertmanager + Grafana usando las plantillas del repo (`prometheus.yml`, `prometheus_rules.yml`, `alertmanager.yml`).
- Ejecuta `make observability-up` para arrancar el stack (usa `host.docker.internal:8880` como target por defecto). Para detenerlo: `make observability-down`.
- Ajusta variables antes de levantar (ej. `SLS_PROM_TARGET_HOST`, `GRAFANA_PORT`, `GRAFANA_ADMIN_PASSWORD`) o añade tus credenciales Slack en `alertmanager.yml` para probar alertas reales.
- `docs/observability/alertmanager.yml` trae un webhook Slack de ejemplo (`https://hooks.slack.com/services/CHANGE/ME/NOW`). Cámbialo por tu URL real antes de habilitar alertas o de correr el smoke test.
- Grafana se levanta con provisioning (`docs/observability/grafana/provisioning/*`) para que el datasource Prometheus y los dashboards Arena/Bot se importen automáticamente tras `make observability-up`.

## Smoke automático
- `scripts/tests/observability_check.py` valida que Prometheus exponga `/api/v1/rules`, que existan las reglas críticas (`ArenaLagHigh`, `BotDrawdownCritical`, etc.) y, opcionalmente, que Grafana/Alertmanager respondan (`GRAFANA_BASE`, `GRAFANA_USER/PASSWORD`, `ALERTMANAGER_BASE`). Devuelve `SystemExit` con un mensaje claro si falta alguno.
- `python scripts/ops.py observability check --prom-base http://127.0.0.1:9090 --grafana-base http://127.0.0.1:3000 --alertmanager-base http://127.0.0.1:9093` ejecuta el mismo smoke pero permite pasar URLs/credenciales desde el CLI sin exportar variables (ideal para cron/CI).
- `make observability-check` invoca el comando anterior dentro del venv y se usa en CI para bloquear merges cuando el stack de métricas quedó roto o sin reglas.

## Reglas de alerta
- `docs/observability/prometheus_rules.yml` incluye reglas listas para Prometheus/Alertmanager (`ArenaLagHigh`, `ArenaDrawdownHigh`, `BotDrawdownCritical`, `CerebroSilent`). Carga el archivo en tu instancia (`rule_files` en `prometheus.yml`) y conecta Alertmanager para enviar notificaciones a Slack/Telegram.

## Monitor activo (`ops monitor check`)
- `python scripts/ops.py monitor check --api-base https://api... --panel-token XXX --slack-webhook ...` valida lag de arena, drawdown y ticks sin campeones.
- Ajusta los umbrales `--min-arena-sharpe` y `--min-decisions-per-min` para recibir alertas cuando el Sharpe promedio del panel o las decisiones/min del Cerebro caen por debajo de lo esperado.
- Programa cron o systemd timer para ejecutarlo cada 5-10 minutos (usa `--dry-run` para pruebas). Revisa `tmp_logs/monitor_guard.log` si lo rediriges.

## CI/CD
- `.github/workflows/ci.yml` ejecuta `pytest`, `npm run lint` del panel y `python scripts/ops.py monitor check --dry-run` en cada push/PR. Úsalo como punto de partida para gatear despliegues.
- Amplía el pipeline con `scripts/tests/e2e_smoke.py` cuando tengas entornos staging accesibles desde GitHub Actions.

## Alertas externas
- Slack/Telegram: configura webhooks/token y pásalos al monitor (`--slack-webhook`, `--telegram-token`, `--telegram-chat-id`).
- Para alertas por Prometheus/Grafana: define reglas que disparen cuando `sls_arena_state_age_seconds` > umbral, drawdown supere `max_drawdown`, o `sls_cerebro_decisions_per_min` caiga por debajo de un límite.

## Bitácora
- Registra incidentes y cambios operativos en `Contexto BOT IA.md` (sección Bitácora) y mantén sincronizados README/docs para que el siguiente operador entienda el estado actual.
