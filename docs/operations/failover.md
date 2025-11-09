# Procedimiento de Failover / Simulación de Resiliencia

Este procedimiento valida que los servicios críticos (`sls-api`, `sls-cerebro`, `sls-bot`) pueden reciclarse sin intervención manual y genera un reporte para post-mortem.

## 1. Requisitos previos

- Acceso sudo en el VPS.
- Servicios instalados como `*.service` en systemd.
- `logs/failover/` accesible para escribir el reporte.

## 2. Dry-run (planificación)

```
cd /root/SLS_Bot
make failover-sim
```

Esto **no** reinicia nada; captura `systemctl status` y `journalctl` y crea `logs/failover/failover_report_<timestamp>.log`. Revisa el archivo para confirmar el orden y dependencias.

## 3. Ejecución real

Planifica una ventana y ejecuta:

```
cd /root/SLS_Bot
sudo make failover-sim EXECUTE=1
```

Parámetros útiles:

- `FAILOVER_SERVICES="sls-api.service,sls-panel.service"` para personalizar la lista.
- `FAILOVER_MAX_WAIT=60` para ampliar el tiempo de espera.
- `FAILOVER_LOG_DIR=/var/log/sls_bot/failover` para guardar los reportes en otra ruta.

## 4. Contenido del reporte

Cada bloque incluye:

1. Estado inicial (`systemctl status`).
2. Resultado del reinicio (o comando dry-run).
3. Estado posterior.
4. Últimas `journalctl` líneas.

Adjunta el archivo al post-mortem de cada simulacro/incidente.

## 5. Checklist post-ejecución

- [ ] Verificar que los tres servicios quedaron en `active`.
- [ ] Revisar el panel `/health` y `/status`.
- [ ] Confirmar que el bot continúa recibiendo señales o cronjobs siguen ejecutándose.
- [ ] Documentar en `Contexto BOT IA.md` / runbook correspondiente la fecha y hallazgos.

## 6. Ejecución 2025-11-09

| Servicio | Resultado | Notas |
|----------|-----------|-------|
| `sls-api.service` | ✅ vuelve a `active` inmediato. | Un restart previo falló por `logs_dir` vacío, pero el simulador lo dejó estable. |
| `sls-cerebro.service` | ⚠️ (resuelto) | Fallaba por `ModuleNotFoundError: pandas`; se resolvió reinstalando `bot/requirements-ia.txt` en el venv (`pip install -r bot/requirements-ia.txt`). |
| `sls-bot.service` | ⚠️ (resuelto) | El ExecStart apuntaba a `/root/SLS_Bot/SLS_Bot/...`; actualizado a `/root/SLS_Bot/...` y se recargó systemd. Actualmente `systemctl status sls-bot` muestra `active (running)`. |

Reporte: `logs/failover/failover_report_20251109_144707.log`.
Próximo simulacro: volver a ejecutar `sudo make failover-sim EXECUTE=1` para verificar en frío que ambos servicios siguen en verde.
