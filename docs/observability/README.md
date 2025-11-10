# Observabilidad – SLS Bot 2V

Esta guía resume cómo dejar operativo el stack de métricas/alertas para el bot.

## 1. Métricas de negocio (Prometheus textfile)

1. Instala Node Exporter con el textfile collector habilitado (`--collector.textfile.directory=/var/lib/node_exporter/textfile_collector`).
2. Ejecuta el generador de métricas:
   ```bash
   # Ejemplo manual
   make metrics-business MODE=real METRICS_OUTPUT=/var/lib/node_exporter/textfile_collector/sls_bot_business.prom
   ```
3. Automatiza con systemd/cron. Ya incluimos las unidades en `docs/observability/systemd/`:
  ```bash
  sudo cp docs/observability/systemd/sls-metrics-business.service /etc/systemd/system/
  sudo cp docs/observability/systemd/sls-metrics-business.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now sls-metrics-business.timer
  ```
  *Tip:* ajusta `Environment=SLSBOT_MODE` y `Environment=METRICS_OUTPUT` dentro del `.service` antes de copiarlo.

## 2. Reglas de Prometheus

1. Copia `docs/observability/prometheus_rules.yml` a tu `rules.d` (p.ej. `/etc/prometheus/rules.d/sls_bot.yml`).
2. Recarga Prometheus (`systemctl reload prometheus`).
3. Las reglas incluidas:
   - `SLSBotNoTrades30m`: no hay trades en 30 min.
   - `SLSBotPnLDailyMissing`: no se generó resumen diario en >25 h.
   - `SLSBotWinRateLow`: win rate < 45 % con >15 trades.
   - `SLSBotDrawdownHigh`: drawdown móvil > 4 %.
   - `sls_bot_business_sharpe_proxy`: recording rule auxiliar para dashboards.

## 3. Alertmanager

1. Usa `docs/observability/alertmanager.yml` como base.
2. Sustituye `api_url` por tu webhook real de Slack/Teams.
3. Coloca el archivo en `/etc/alertmanager/alertmanager.yml` o inclúyelo en tu configuración.
4. Recarga Alertmanager (`systemctl reload alertmanager`).

## 4. Grafana – Control Center

1. Importa `docs/observability/grafana/sls_bot_control_center.json`.
2. Selecciona tu datasource Prometheus (`DS_PROMETHEUS`) al importar.
3. El dashboard incluye:
   - KPIs (PnL acumulado, win rate).
   - Tabla/serie con PnL diario y trades por día.
   - Panel con alertas `ALERTS{alertname=~"SLSBot.*"}`.
   - Variable `$mode` para cambiar entre `test` y `real`.

## 5. Validaciones rápidas

```bash
make metrics-business MODE=test METRICS_OUTPUT=/tmp/sls_bot_test.prom
cat /tmp/sls_bot_test.prom
promtool check rules docs/observability/prometheus_rules.yml
alertmanager --config.file=docs/observability/alertmanager.yml --dry.run
```

Mantén este directorio actualizado si se agregan nuevas métricas, reglas o dashboards.
