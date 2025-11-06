# Plan de Failover y Resiliencia (SLS_Bot 2V)

## Objetivos
- Reiniciar servicios críticos en orden controlado.
- Validar salud posterior (healthcheck, métricas, monitor guard).
- Registrar un reporte para postmortem.

## Herramienta

`scripts/tools/failover_simulator.py`

Características:
- `--execute` aplica los comandos (`systemctl stop/start`, healthcheck).
- `--restart` (implicado cuando `--execute`) detiene y vuelve a levantar servicios en el orden definido.
- `--services` permite ajustar el orden (default: `sls-bot`, `sls-cerebro`, `sls-api`).
- Reporte en `tmp_logs/failover_report_<timestamp>.log`.

### Ejemplos

Dry-run (solo imprime comandos y genera reporte):
```bash
make failover-sim API_BASE=https://api.staging.tu-dominio.com PANEL_TOKEN=token123
```

Failover real (requiere sudo):
```bash
sudo API_BASE=https://api.prod.tu-dominio.com PANEL_TOKEN=token123 make failover-sim EXECUTE=1
```

### Contenido del reporte
- Estado inicial (`systemctl status`).
- Comandos ejecutados (stop/start).
- Resultado de `healthcheck.py`.
- Estado final.

## Escenarios sugeridos

| Escenario | Frecuencia | Pasos adicionales |
|-----------|------------|-------------------|
| Failover de mantenimiento | Mensual | Ejecutar `make failover-sim EXECUTE=1`, verificar dashboards tras restart. |
| Simulación de incidente | Trimestral | Forzar fallo en `sls-bot.service`, ejecutar failover, documentar postmortem. |
| Failover completo (API + Cerebro + panel) | Semestral | Añadir `sls-panel.service` a `--services`. |

## Checklist post-failover

- [ ] Reporte generado (`tmp_logs/failover_report_*.log`) cargado en Confluence/Notion.
- [ ] Alertas de Prometheus resueltas.
- [ ] Panel y API responden (`make health`).
- [ ] Monitor guard sin incidencias (`systemctl status sls-monitor.timer`).
- [ ] Restic backup confirmado si se ejecutó durante la ventana.

## Automatización futura

- Integrar este flujo en GitHub Actions o Jenkins para staging (`make failover-sim` en cron semanal).
- En producción, ejecutar bajo ventana de mantenimiento con notificación previa.
- Añadir pruebas de caos (apagar servicio random) combinadas con este script y reportar métricas de recuperación.
