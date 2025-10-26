# Automatización de despliegue

Estos archivos permiten instalar el backend, panel y servicios auxiliares con systemd/Nginx sin repetir tareas manuales.

## 1. Variables base
Define las rutas y usuario que ejecutará los servicios antes de correr cualquier script:
```bash
export APP_ROOT=/opt/SLS_Bot
export SVC_USER=sls
export INSTALL_SYSTEMD=1   # opcional, solo si quieres copiar los .service automáticamente
```
`APP_ROOT` apunta al repositorio ya sincronizado en el servidor y `SVC_USER` debe existir (`useradd -r -m sls`).

## 2. Bootstrap (Python + Node + pruebas)
```bash
cd $APP_ROOT
chmod +x scripts/deploy/bootstrap.sh
APP_ROOT=$APP_ROOT SVC_USER=$SVC_USER INSTALL_SYSTEMD=$INSTALL_SYSTEMD ./scripts/deploy/bootstrap.sh
```
El script crea/actualiza `venv`, instala dependencias (`requirements*.txt`), ejecuta `pytest`, `npm run lint`, `npm run build` y, si `INSTALL_SYSTEMD=1`, copia las unidades reemplazando `{{APP_ROOT}}`/`{{SVC_USER}}` por los valores actuales. Después hace `systemctl daemon-reload` y habilita `sls-api.service` y `sls-bot.service`. Para el panel, ejecuta `systemctl enable sls-panel.service` una vez construida la app.

## 3. Archivo de entorno global
Creá `/etc/sls_bot.env` para centralizar puertos y tokens:
```
APP_ROOT=/opt/SLS_Bot
SLS_API_PORT=8880
SLS_BOT_PORT=8080
PANEL_PORT=3000
PANEL_API_TOKENS=panel_prod@2025-12-31,panel_new
TRUST_PROXY_BASIC=1
PROXY_BASIC_HEADER=X-Forwarded-User
```
Systemd cargará este archivo en cada servicio (`EnvironmentFile=-/etc/sls_bot.env`). Ajusta `SLSBOT_CONFIG`, `ALLOWED_ORIGINS`, etc. según tu despliegue.

## 4. Nginx + Basic Auth delegada
Ejemplo mínimo (`/etc/nginx/sites-available/sls_panel.conf`):
```
server {
    listen 443 ssl;
    server_name panel.tu-dominio.com;

    auth_basic "SLS Panel";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location /api/ {
        proxy_pass http://127.0.0.1:8880/;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-User $remote_user;
    }

    location / {
        proxy_pass http://127.0.0.1:3000/;
    }
}
```
El backend valida `X-Forwarded-User` cuando `TRUST_PROXY_BASIC=1`, por lo que ya no es necesario exponer Basic Auth directamente en FastAPI. Usa `htpasswd` para rotar credenciales sin reiniciar la app.

## 5. Rotación de tokens
- Mantén dos entradas simultáneas en `PANEL_API_TOKENS` (`token_nuevo@YYYY-MM-DD,token_anterior@YYYY-MM-DD`). El backend ignora las que ya expiraron.
- Distribuye el token nuevo en `panel/.env` y vuelve a desplegar el frontend.
- Una vez confirmada la migración, elimina el token viejo de `/etc/sls_bot.env` y recarga `sls-api.service`.

## 6. Smoke tests post-deploy
Después de cada despliegue ejecuta:
```bash
SLS_API_BASE=https://api.tu-dominio.com \
SLS_PANEL_TOKEN=token_nuevo \
SLS_CONTROL_USER=panel \
SLS_CONTROL_PASSWORD='***' \
/opt/SLS_Bot/venv/bin/python /opt/SLS_Bot/scripts/tests/e2e_smoke.py
```
El script valida `/health`, `/pnl/diario` y `/control/*`. Integra este comando en tu pipeline (GitHub Actions, Jenkins, etc.) para detectar regresiones antes de abrir el panel a traders.

## 7. Cerebro IA como servicio dedicado
Si quieres aislar el loop de Cerebro (para que sobreviva a reinicios del bot principal) instala el nuevo unit file:
```bash
cd $APP_ROOT
chmod +x scripts/deploy/install_cerebro_service.sh
APP_ROOT=$APP_ROOT SVC_USER=$SVC_USER ./scripts/deploy/install_cerebro_service.sh
```
El script copia `scripts/deploy/systemd/sls-cerebro.service`, reemplaza `{{APP_ROOT}}/{{SVC_USER}}`, recarga systemd y habilita `sls-cerebro.service` (ejecuta `python -m cerebro.service --loop`). Para un healthcheck rápido:
```bash
curl -fsS http://127.0.0.1:${SLS_API_PORT:-8880}/cerebro/status | jq '.time'
```
Incorpora este servicio en tus dashboards (Prometheus, healthchecks externos, etc.) si necesitas observar la latencia de las decisiones IA de forma separada.
