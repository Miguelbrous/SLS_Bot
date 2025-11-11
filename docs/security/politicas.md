# Políticas de Seguridad y Cumplimiento

Este documento resume las prácticas recomendadas para operar **SLS_Bot** de forma segura.

## Gestión de secretos

- Nunca confirmes `.env`, `config/config.json` ni credenciales en el repositorio.
- Usa un gestor de secretos (Vault, SOPS + Git) para almacenar:
  - `BYBIT_API_KEY/SECRET`
  - `PANEL_API_TOKENS`
  - Webhooks (`SLACK_WEBHOOK_*`)
  - Cualquier token/pwd de terceros (Slack, Telegram, servicios internos)
- Para despliegues automatizados, el playbook Ansible (`infra/ansible/provision.yml`) crea `/etc/sls_bot.env`. Cifra este archivo (por ejemplo, `sops -e /etc/sls_bot.env > /etc/sls_bot.env.enc`) y registra el método de desencriptado en el runbook operativo.
- Rotación: define expiraciones usando el formato `token@YYYY-MM-DD` en `PANEL_API_TOKENS`. Mantén como máximo dos tokens vigentes (actual y siguiente).

## Auditoría

- Toda acción sobre `/control/*` queda registrada en `AUDIT_LOG` (por defecto `logs/<mode>/audit.log`). Cada entrada incluye timestamp, actor y resultado.
- Configura `AUDIT_LOG` en `.env` para apuntar a un directorio persistente (`/var/log/sls_bot/audit.log`).
- Revisa el archivo en incidentes o como parte del post-mortem (ver `docs/operations/failover.md`).

## Hardening de API

- El endpoint `/control/{service}/{action}` exige:
  - Basic Auth (`CONTROL_USER/CONTROL_PASSWORD`) o cabecera `X-Forwarded-User` si `TRUST_PROXY_BASIC=1`.
  - Rate limiting configurable (`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`). Superar el límite devuelve `429 Too Many Requests`.
- El panel requiere `X-Panel-Token`. Mantén la rotación de tokens en la hoja de secretos y actualiza a los operadores cuando cambien.
- Usa HTTPS + reverse proxy (Nginx) para publicar el panel/API.

## Autopilot Summary & Prometheus

- Programa `make autopilot-summary` (o `scripts/cron/autopilot_summary.sh`) para generar el reporte y métricas en `AUTOPILOT_SUMMARY_JSON`, `AUTOPILOT_PROM_FILE`.
- Expón `AUTOPILOT_PROM_FILE` al textfile collector de Prometheus para alertar cuando el dataset pierda calidad o no haya candidatos aprobados.

## Checklist operativo

- [ ] `.env` y `config.json` cifrados o almacenados en el gestor de secretos.
- [ ] `AUDIT_LOG` apuntando a directorio persistente y revisado semanalmente.
- [ ] Rate limit configurado (`RATE_LIMIT_REQUESTS/WINDOW`) acorde al entorno.
- [ ] `make autopilot-summary` en cron/systemd y su salida monitorizada en el panel/Prometheus.
- [ ] `make security-check` ejecutado antes de cada despliegue para asegurarse de que `.env`/`config.json` cumplen los requisitos mínimos (AUDIT_LOG, tokens vigentes, rate-limit, rutas válidas).
