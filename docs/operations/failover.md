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
