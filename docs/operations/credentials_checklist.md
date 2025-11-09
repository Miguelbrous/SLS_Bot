# Checklist de credenciales y secretos – SLS_Bot 2V

Este documento resume **todo lo que debes completar una vez tengas credenciales reales**. El repositorio ya incluye plantillas, scripts y unidades listas; solo falta inyectar estos valores y ejecutarlos.

## 1. Backend / Bot / Cerebro

- `.env` (copia de `.env.example`):
  - `BYBIT_API_KEY` / `BYBIT_API_SECRET`
  - `PANEL_API_TOKENS` o `PANEL_API_TOKEN`
  - `CONTROL_USER` / `CONTROL_PASSWORD`
  - `AUDIT_LOG` (ruta definitiva, idealmente en disco persistente)
  - `SLACK_WEBHOOK_*` si deseas notificaciones (ver sección 4).
- `config/config.json` (basado en `config/config.sample.json`):
  - Rutas definitivas (`/srv/sls_bot/...` o similares).
  - Ajusta `modes.real.bybit.*` con las llaves de producción.
  - Configura `risk.guardrails` según tu apetito de riesgo.
- Systemd (`/etc/systemd/system/sls-api.service`, `sls-bot.service`, `sls-cerebro.service`):
  - Ya están parametrizados con `EnvironmentFile=/root/SLS_Bot/.env`. Solo confirma rutas si instalas en otra carpeta.

## 2. CI/CD y Provisioning

- GitHub Actions:
  - Secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` para habilitar el job de despliegue.
  - Opcional: `SLACK_WEBHOOK_CI` si quieres avisos automáticos.
- Ansible (`infra/ansible`):
  - `inventory.ini` con IP/usuario reales.
  - `group_vars/all.yml` (opcional) para centralizar variables sensibles (usa `ansible-vault` si hace falta).

## 3. Backups y almacenamiento

- Restic (local listo, pero si usas cloud):
  - `/etc/sls_bot_restic.pwd`:
    - `RESTIC_REPOSITORY=s3:s3.amazonaws.com/<bucket>/sls-bot`
    - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
    - `AWS_DEFAULT_REGION`
  - `/etc/sls_bot_backup.env`:
    - Ajusta `RESTIC_PASSWORD_FILE` si cambiaste la ruta.
    - Opcional: `RESTIC_TAGS`, `RESTIC_INCLUDE`, `RESTIC_EXCLUDE`.
- `sls-backup.service/timer` ya instalados: solo asegúrate de que el repositorio remoto sea accesible.

## 4. Observabilidad y alertas

- Prometheus:
  - Ubica `docs/observability/prometheus_rules.yml` en tu `rules.d`.
  - Si usas autentificación para scrape, agrega `bearer_token` o `basic_auth` en tu `prometheus.yml`.
- Alertmanager (`docs/observability/alertmanager.yml`):
  - `api_url` → Slack webhook real (`https://hooks.slack.com/...`).
  - `channel` si quieres rutas distintas por modo.
- Grafana:
  - Token/API o usuario/contraseña para importar `sls_bot_control_center.json`.
  - Datasource `DS_PROMETHEUS` apuntando a tu instancia.
- Cron/timers:
  - `sls-metrics-business.timer` (ver `docs/observabilidad/README.md`) solo requiere establecer `SLSBOT_MODE` y la ruta del textfile collector.
- `SLACK_WEBHOOK_AUTOPILOT`, `SLACK_WEBHOOK_ALERTS`, etc., en `.env` para que los scripts `autopilot_summary` y Alertmanager notifiquen.

## 5. Panel / Control Center

- `panel/.env`:
  - `NEXT_PUBLIC_API_BASE=https://api.tu-dominio.com`
  - `NEXT_PUBLIC_PANEL_API_TOKEN` (uno de los tokens definidos en `.env`)
  - `NEXT_PUBLIC_CONTROL_AUTH_MODE` (`browser` o `header` dependiendo de tu setup con Nginx/Proxy).
- Nginx/Proxy:
  - Certificados TLS válidos.
  - Cabeceras `X-Forwarded-User` si usas autenticación básica delegada.

## 6. Seguridad y cumplimiento

- Vault/SOPS:
  - Ruta del repositorio de secretos.
  - Roles/policies para rotar las llaves Bybit, Slack y Panel.
- Auditoría:
  - Asegura que `AUDIT_LOG` apunte a un storage con backup (p.ej. `/var/log/sls/audit.log` + logrotate).
- Rate limiting:
  - Variables `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW` ya documentadas en `.env`.

## 7. Go-Live (F5)

- `make autopilot-summary`:
  - `AUTOPILOT_DATASET` y `AUTOPILOT_RUNS` apuntan a datasets reales.
- `make deploy-plan`:
  - Define `DEPLOY_PLAN_SERVICES` con el estado esperado (`sls-bot=active`…).
  - Coloca `risk_state.json` y `audit.log` en `logs/<mode>/`.
  - El resultado `metrics/deploy_plan.md` se comparte en el comité Go/No-Go.
- Checklist 24/7 (`docs/operations/operacion_24_7.md`) ya listo: solo marca cada ítem con tus evidencias.

---

Con este checklist, el repositorio queda **plug-and-play**: únicamente necesitas introducir tus credenciales/URLs reales y ejecutar los comandos apuntados en cada sección.
