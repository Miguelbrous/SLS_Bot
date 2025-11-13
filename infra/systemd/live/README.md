SLS_Bot systemd units (con rutas resueltas)
==========================================

Este directorio contiene copias listas para usar de los servicios systemd,
con `APP_ROOT=/root/SLS_Bot` y `SVC_USER=root`. Para instalarlos:

```bash
sudo cp infra/systemd/live/sls-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sls-api sls-bot sls-cerebro
# (Opcional) panel si quieres servir Next.js en el mismo host
sudo systemctl enable --now sls-panel
```

Asegúrate de tener `/etc/sls_bot.env` con tus variables (Bybit, panel,
`CRYPTOPANIC_TOKEN`, etc.) antes de habilitarlos.
