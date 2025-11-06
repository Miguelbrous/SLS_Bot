# Operación 24/7 de SLS_Bot

Guía de referencia para mantener el bot operativo las 24 horas, con arranque automático, monitoreo, pipelines de datos y respuesta ante incidentes.

## 1. Componentes críticos
- **API de control (`sls-api.service`)**: expone `/health`, `/metrics`, `/arena/state` y endpoints de gestión.
- **Worker del bot (`sls-bot.service`)**: procesa señales y envía órdenes a Bybit.
- **Cerebro IA (`sls-cerebro.service`)**: ingesta datos, ejecuta estrategias, entrena modelos y expone métricas.
- **Panel (`sls-panel.service`)**: opcional en servidores headless. Depende de NEXT.js y se recomienda detrás de un proxy.
- **Cronjobs**:
  - `scripts/cron/cerebro_ingest.sh`: ingesta periódica de datos externos.
  - `scripts/cron/cerebro_autopilot.sh`: validación + entrenamiento automático del Cerebro.
  - `scripts/tests/cerebro_metrics_smoke.sh`: smoke semanal para validar métricas/textfiles.
- **Monitor Guard**: `scripts/tools/monitor_guard.py` (ahora con servicio systemd + timer) vigila Arena/Cerebro y notifica incidencias.
- **Observabilidad**: stack Prometheus + Grafana + Alertmanager (local o remota) + exportación vía textfile collector.
- **Backups Restic**: servicio/timer `sls-backup.*` invoca `scripts/cron/backup_restic.sh` y aplica políticas `forget/prune`.
- **Métricas de negocio**: `scripts/tools/prometheus_business_metrics.py` genera `business.prom` con PnL, drawdown y slippage para dashboards/alertas 2V.

## 2. Sistema operativo / arranque automático
1. Crear usuario de servicio (por defecto `sls`).
2. Copiar `.env` a `/etc/sls_bot.env` con rutas absolutas y secretos (**no** versionarlo).
3. Instalar servicios:
   ```bash
   make setup-dirs ENV_FILE=.env                # crea logs/, models/, excel/
   python scripts/deploy/bootstrap.py           # instala venv, dependencias y systemd units
   make encender                                # levanta api/bot/cerebro/panel vía systemd
   ```
4. Habilitar los servicios en el arranque:
   ```bash
   sudo systemctl enable sls-api.service sls-bot.service sls-cerebro.service
   sudo systemctl enable sls-panel.service      # opcional
   ```
5. Instalar watchdog:
   ```bash
   sudo cp scripts/deploy/systemd/sls-monitor.service /etc/systemd/system/
   sudo cp scripts/deploy/systemd/sls-monitor.timer /etc/systemd/system/
   sudo systemctl enable --now sls-monitor.timer
   ```
   El timer ejecuta `monitor_guard.py` cada 5 minutos y envía alertas a Slack/Telegram.

6. **Provisioning reproducible**:
   ```bash
   cp infra/ansible/inventory.sample.ini infra/ansible/inventory.staging.ini
   # Edita ansible_host, app_root, repo_url, etc.
   make provision STAGE=staging
   ```
   El playbook instala paquetes, crea el usuario `sls`, clona el repo y ejecuta el bootstrap/monitor guard. Usa `EXTRA='-e bootstrap_autorun=false'` para modo dry-run.

7. **Backups Restic**:
   ```bash
   sudo install -m 600 /dev/null /etc/sls_bot_backup.env
   sudo editor /etc/sls_bot_backup.env   # define RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE, etc.
   sudo systemctl enable --now sls-backup.timer
   systemctl status sls-backup.timer
   ```
   Consulta `docs/operations/backups_restic.md` para variables recomendadas, políticas `forget` y procedimiento de restore en staging.

## 3. Datos, ingesta y entrenamiento
- `CEREBRO_INGEST_*` y `CEREBRO_AUTO_*` en `.env` controlan símbolos, límites, textfile collector, webhooks y validaciones.
- Los scripts de cron usan el binario `PYTHON_BIN` (venv). Exportar `NODE_EXPORTER_TEXTFILE_DIR` para que escriban en `/var/lib/node_exporter/textfile_collector/`.
- Valores recomendados:
  ```ini
  CEREBRO_INGEST_REQUIRE_SOURCES=market,news,funding,onchain
  CEREBRO_INGEST_MIN_MARKET_ROWS=600
  CEREBRO_INGEST_PROM_FILE=/var/lib/node_exporter/textfile_collector/cerebro_ingest.prom
  CEREBRO_AUTO_MODE=real
  CEREBRO_AUTO_DATASET_MIN_WIN_RATE=0.52
  CEREBRO_AUTO_DATASET_MAX_LOSS_RATE=0.58
  CEREBRO_AUTO_SUMMARY_FILE=/var/log/sls_bot/cerebro_autopilot.jsonl
  CEREBRO_AUTO_SUMMARY_COMPARE=/var/log/sls_bot/cerebro_autopilot.jsonl
  CEREBRO_AUTO_SUMMARY_MAX_WIN_DELTA=0.08
  CEREBRO_AUTO_SUMMARY_MAX_ROWS_DROP=0.25
  ```
- Programar cron/systemd timers:
  ```bash
  */15 * * * * /usr/local/bin/bash /opt/sls_bot/scripts/cron/cerebro_ingest.sh >> /var/log/sls_bot/cron.log 2>&1
  5 * * * * /usr/local/bin/bash /opt/sls_bot/scripts/cron/cerebro_autopilot.sh >> /var/log/sls_bot/cron.log 2>&1
  0 7 * * MON bash scripts/tests/cerebro_metrics_smoke.sh --dir /var/lib/node_exporter/textfile_collector --max-age 30
  ```

## 4. Monitoreo y alertas
- Activar Prometheus/Grafana/Alertmanager (ver `docs/observability/`).
- Asegurar que `node_exporter` consume los `.prom` generados por ingest/autopilot.
- Programar `make metrics-business API_BASE=https://api.tu-dominio.com PANEL_TOKEN=token` (o integrar en cron/systemd) para alimentar `tmp_metrics/business.prom` con PnL/drawdown/slippage.
- `monitor_guard.py` requiere `SLACK_WEBHOOK_MONITOR` o Telegram. Configurar en `/etc/sls_bot.env`.
- Alertmanager: definir rutas a Slack/Email/SMS para eventos críticos (ver `docs/observability/alertmanager.yml`).
- Panel: habilitar `NEXT_PUBLIC_PROMETHEUS_BASE_URL` para grafos en tiempo real.

## 5. Logging y rotación
- Directorios:
  - `logs/` (por modo) para API, Cerebro, autopilot, ingest.
  - `tmp_logs/` (corridas temporales).
- Programar `logrotate` (ejemplo en `/etc/logrotate.d/sls_bot`):
  ```
  /opt/sls_bot/logs/*.log {
      daily
      rotate 14
      compress
      missingok
      notifempty
      copytruncate
  }
  ```
- Usar `make rotate-artifacts DAYS=14` para archivar modelos/datasets viejos.

## 6. Backups y postura de seguridad
- Respaldar `logs/<mode>/`, `models/cerebro/<mode>/`, `.env` cifrado y `panel/.env`.
- Sugerido: `restic` o `rsnapshot` diarios.
- Asegurar firewall (UFW) con puertos mínimos (API/panel tras Nginx).
- Renovar claves API Bybit periódicamente; usar `scripts/tools/infra_check.py` para detectar expiraciones.

## 7. Procedimiento de operación
1. **Startup**: `make encender` (o `systemctl start sls-{api,bot,cerebro}`).
2. **Smoke**: `make health`, `make monitor-check`, `make textfile-smoke DIR=/var/lib/node_exporter/textfile_collector`.
3. **Monitoreo continuo**: Slack/Telegram desde `sls-monitor.timer` + panel + Grafana.
4. **Incidente**:
   - Ver `journalctl -u sls-*.service`.
   - `make diagnostico` para estado + tail de logs.
   - Si hay degradación de datos, revisar `tmp_logs/cerebro_autopilot_*` y reinstanciar dataset (`scripts/tools/generate_cerebro_dataset.py`).
   - Ejecutar `make failover-sim` (dry-run) o `sudo make failover-sim EXECUTE=1` para reinicio ordenado y reporte (`docs/operations/failover.md`).
5. **Maintenance**:
   - `make autopilot-ci` antes de promover cambios.
   - `make rotate-artifacts DAYS=14` semanalmente.
   - `scripts/tests/cerebro_metrics_smoke.sh` cada lunes.

## 8. Checklist de producción
| Elemento | Estado |
|----------|--------|
| `.env` validado con `make infra-check ENSURE_DIRS=1` | ✅ |
| Servicios systemd habilitados (`enable --now`) | ✅ |
| `sls-monitor.timer` activo | ✅ |
| Cronjobs ingest/autopilot configurados | ✅ |
| Textfile collector accesible | ✅ |
| Slack/Telegram webhooks probados | ✅ |
| Observabilidad (Prom/Grafana/Alertmanager) | ✅ |
| Backups automáticos configurados | ✅ |
| Runbooks y credenciales seguras | ✅ |

Una vez cubiertos estos puntos y habilitados los servicios, el bot queda preparado para operar 24/7 y se puede iterar sobre nuevas mejoras sin perder continuidad.
