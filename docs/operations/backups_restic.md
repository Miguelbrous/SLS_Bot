# Backups automáticos con Restic

Este playbook describe cómo proteger `logs/`, `models/`, `config/` y artefactos críticos del bot usando Restic + cron/systemd.

## 1. Requisitos

- Restic 0.15+ instalado (`apt install restic` o `curl https://rclone.org/install.sh`).
- Destino compatible: S3/GCS, SFTP, carpeta local montada, etc.
- Variables sensibles almacenadas en `/etc/sls_bot_backup.env` (usar `chmod 600` y, si es posible, cifrar con Vault).

## 2. Script

`scripts/cron/backup_restic.sh`:

- Lee `RESTIC_REPOSITORY`, `RESTIC_PASSWORD/RESTIC_PASSWORD_FILE`, `RESTIC_BACKUP_PATHS`.
- Permite `RESTIC_TAGS`, `RESTIC_FORGET_ARGS`, `RESTIC_EXCLUDE_FILE`, `RESTIC_CHECK`.
- `RESTIC_DRY_RUN=1` simula la ejecución (útil para pipelines).

### Variables recomendadas

```
RESTIC_REPOSITORY=s3:s3.amazonaws.com/tu-bucket/sls-bot
RESTIC_PASSWORD_FILE=/etc/sls_bot_restic.pwd
RESTIC_BACKUP_PATHS="/opt/SLS_Bot/logs /opt/SLS_Bot/models /opt/SLS_Bot/config"
RESTIC_TAGS=sls-bot,prod
RESTIC_FORGET_ARGS="--keep-daily 7 --keep-weekly 4 --keep-monthly 6"
RESTIC_CHECK=1
```

## 3. Cron/systemd timer

### Cron clásico
```
0 3 * * * RESTIC_BIN=/usr/bin/restic RESTIC_REPOSITORY=... RESTIC_PASSWORD_FILE=... bash /opt/SLS_Bot/scripts/cron/backup_restic.sh >> /var/log/sls_bot/backup.log 2>&1
```

### systemd timer

`/etc/systemd/system/sls-backup.service`:
```
[Unit]
Description=SLS Bot Restic Backup
After=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/sls_bot_backup.env
ExecStart=/bin/bash /opt/SLS_Bot/scripts/cron/backup_restic.sh
```

`/etc/systemd/system/sls-backup.timer`:
```
[Unit]
Description=Programar backups restic SLS Bot

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Activar:
```
sudo systemctl daemon-reload
sudo systemctl enable --now sls-backup.timer
```

## 4. Verificación / Restore

1. **Dry-run**:  
   ```
   RESTIC_DRY_RUN=1 RESTIC_REPOSITORY=... RESTIC_PASSWORD_FILE=... bash scripts/cron/backup_restic.sh
   ```
2. **Backup real**: revisar `/var/log/sls_bot/backup.log` o `systemctl status sls-backup.service`.
3. **Restore en staging**:
   ```
   restic -r $RESTIC_REPOSITORY restore latest --target /tmp/sls_restore
   diff -qr /opt/SLS_Bot/config /tmp/sls_restore/opt/SLS_Bot/config
   ```
4. Documenta fecha de último backup y último restore en `Contexto BOT IA.md`.

## 5. Integración con Ansible

- Añade los ficheros anteriores en el rol `sls_bot` (pendiente).  
- Exporta las variables en `group_vars` cifradas (`ansible-vault encrypt_string`).  
- Usa `make provision STAGE=prod EXTRA='-e restic_enabled=true'` para instalar automáticamente el timer.

## 6. Checklist

- [ ] Restic instalado en el host.  
- [ ] `/etc/sls_bot_backup.env` con permisos 600.  
- [ ] Timer `sls-backup.timer` activo (`systemctl status`).  
- [ ] Registro del último backup (log).  
- [ ] Restore en staging verificado y documentado.  
- [ ] Alerta en Slack/Prometheus para fallos de backup (ver F1 Observabilidad).  
