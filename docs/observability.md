# Observabilidad y monitoreo

## Métricas Prometheus
- La API expone `/metrics` (Prometheus). Se incluyen `sls_arena_*`, `sls_bot_drawdown_pct`, `sls_cerebro_decisions_per_min` y métricas básicas de FastAPI.
- Ejemplo `prometheus.yml`:
  ```yaml
  scrape_configs:
    - job_name: "sls_bot"
      static_configs:
        - targets: ["127.0.0.1:8880"]
  ```
- Importa los endpoints a Grafana y crea paneles para: drawdown, ticks sin campeones, decisiones/minuto y estado de `/health`.

## Monitor activo (`ops monitor check`)
- `python scripts/ops.py monitor check --api-base https://api... --panel-token XXX --slack-webhook ...` valida lag de arena, drawdown y ticks sin campeones.
- Programa cron o systemd timer para ejecutarlo cada 5-10 minutos (usa `--dry-run` para pruebas). Revisa `tmp_logs/monitor_guard.log` si lo rediriges.

## CI/CD
- `.github/workflows/ci.yml` ejecuta `pytest`, `npm run lint` del panel y `python scripts/ops.py monitor check --dry-run` en cada push/PR. Úsalo como punto de partida para gatear despliegues.
- Amplía el pipeline con `scripts/tests/e2e_smoke.py` cuando tengas entornos staging accesibles desde GitHub Actions.

## Alertas externas
- Slack/Telegram: configura webhooks/token y pásalos al monitor (`--slack-webhook`, `--telegram-token`, `--telegram-chat-id`).
- Para alertas por Prometheus/Grafana: define reglas que disparen cuando `sls_arena_state_age_seconds` > umbral, drawdown supere `max_drawdown`, o `sls_cerebro_decisions_per_min` caiga por debajo de un límite.

## Bitácora
- Registra incidentes y cambios operativos en `Contexto BOT IA.md` (sección Bitácora) y mantén sincronizados README/docs para que el siguiente operador entienda el estado actual.
