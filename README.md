# SLS_Bot

Panel (Next.js 14 + TS) nativo en Windows y API FastAPI que corre en VPS Linux. El repo tambien incluye stubs y utilidades IA para generar decisiones desde Bybit.

## Arquitectura
- `bot/` FastAPI + PyBit, maneja webhooks, control de riesgo, escritura en Excel y endpoints IA.
- `panel/` Next.js 14 (app router) que consume la API via `NEXT_PUBLIC_API_BASE` y `X-Panel-Token`.
- `config/` plantillas y secretos locales (no subir `config.json`).
- `logs/`, `excel/`, `models/` contienen datos generados en tiempo real y no se versionan.
- `docs/cerebro.md` describe el nuevo **Cerebro IA**, un servicio que observa al bot,
  genera features y aprende de los resultados para proponer mejoras. Act?valo
  habilitando `cerebro.enabled` en `config/config.json`; el Cerebro propondr?
  `risk_pct`, `leverage` y SL/TP din?micos, puede descartar operaciones (`NO_TRADE`)
  y ahora integra un guardia de sesiones (Asia/Europa/USA) con sentimiento NLP,
  logging/auditor?a (`/cerebro/decisions`) y un modelo ligero entrenado con tus
  propias operaciones (`bot/cerebro/train.py`) que ajusta la confianza/riesgo solo
  cuando supera los umbrales de AUC/win-rate.

## Variables de entorno
1. Copia `.env.example` como `.env` en la raiz (Terminal Windows PC) y ajusta:
   - `ALLOWED_ORIGINS`: dominios autorizados para el panel.
   - `CONTROL_USER` / `CONTROL_PASSWORD`: credenciales Basic para `/control/*` cuando trabajes en local.
   - `PANEL_API_TOKENS`: lista separada por comas en formato `token@YYYY-MM-DD`. Puedes dejar un token sin fecha para la rotación actual y mantener el anterior hasta su caducidad. La API acepta cualquiera que no haya expirado.
   - `PANEL_API_TOKEN`: compatibilidad hacia atrás si aún manejas un solo token.
   - `TRUST_PROXY_BASIC` / `PROXY_BASIC_HEADER`: activa (`1`) cuando Nginx ya protege `/control/*` con Basic Auth y reenvía el usuario en `X-Forwarded-User`.
   - Variables Bybit (`BYBIT_*`) para el bot real y rutas (`SLSBOT_CONFIG`).
   - Si activas el Cerebro (`cerebro.enabled=true`), define `cerebro.symbols/timeframes`, los multiplicadores `sl_atr_multiple` / `tp_atr_multiple`, un `min_confidence`, el horizonte de noticias (`news_ttl_minutes`) y al menos una entrada en `session_guards`. El bot usar? esas salidas para ajustar riesgo, leverage, stop-loss/take-profit y bloquear entradas cuando el guardia de sesi?n est? activo.
2. Copia `panel/.env.example` como `panel/.env` (Terminal VS Code local) y define `NEXT_PUBLIC_PANEL_API_TOKEN` con el token activo. Ajusta `NEXT_PUBLIC_CONTROL_AUTH_MODE` a `browser` si desarrollarás sin Nginx (pide credenciales desde la UI) o `proxy` para delegar en el reverse proxy.
3. Para el bot real, copia `config/config.sample.json` a `config/config.json` y completa tus credenciales. Si trabajas en el VPS, manten la version cifrada.
4. Ajusta el bloque `risk` en `config/config.json`:
   - `daily_max_dd_pct` / `dd_cooldown_minutes`: pausan el bot cuando la caída diaria supera el límite.
   - `cooldown_after_losses` / `cooldown_minutes`: lógica tradicional por pérdidas consecutivas.
   - `cooldown_loss_streak` / `cooldown_loss_window_minutes` / `cooldown_loss_minutes`: nuevo cooldown inteligente que cuenta las pérdidas de la ventana móvil y detiene el bot durante `cooldown_loss_minutes` si se supera la racha.
   - `pnl_epsilon`: umbral mínimo para considerar una operación como ganadora/perdedora (evita que resultados muy pequeños rompan la racha).
   - `dynamic_risk`: habilita multiplicadores autom?ticos seg?n drawdown/equity (define `drawdown_tiers`, `min_multiplier`, `max_multiplier`, `equity_ceiling_pct`).

## Requisitos
- Python 3.11+ (evita problemas con dependencias cientificas).
- Node.js 20 LTS para el panel.
- `pip` y `npm` disponibles en las terminales que uses.

## Backend FastAPI (API de control + bot)
### Instalar dependencias (Terminal Windows PC)
```
cd C:\Users\migue\Desktop\SLS_Bot
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r bot/requirements-dev.txt
```
`bot/requirements-ia.txt` agrega numpy/pandas/sklearn/xgboost si necesitas entrenar IA.

### API de control (panel) - local
```
cd C:\Users\migue\Desktop\SLS_Bot\bot
set ALLOWED_ORIGINS=http://localhost:3000
set CONTROL_USER=panel
set CONTROL_PASSWORD=cambia_est0
set PANEL_API_TOKENS=panel_token@2099-12-31
set TRUST_PROXY_BASIC=0
..\venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8880
```
Con `NEXT_PUBLIC_CONTROL_AUTH_MODE=browser` el panel seguirá solicitando usuario/contraseña para `/control/*`. En producción cambia a `proxy` y deja que Nginx firme las peticiones con `X-Forwarded-User`.

### Bot trading (`sls_bot.app`) - local
```
cd C:\Users\migue\Desktop\SLS_Bot\bot
set PYTHONPATH=%cd%
set SLSBOT_CONFIG=..\config\config.json
set PORT=8080
..\venv\Scripts\uvicorn sls_bot.app:app --host 127.0.0.1 --port %PORT%
```

### Despliegue en VPS (Terminal VS Code remoto)
```
cd ~/SLS_Bot/bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SLSBOT_CONFIG=/root/SLS_Bot/config/config.json
export CONTROL_USER=panel
export CONTROL_PASSWORD='super-seguro'
export PANEL_API_TOKENS='token_prod@2025-12-31,token_backup'
export TRUST_PROXY_BASIC=1
uvicorn app.main:app --host 0.0.0.0 --port 8880
```
Integra con systemd y Nginx siguiendo `scripts/deploy/README.md` para que el proxy maneje Basic Auth y rote tokens sin reiniciar la API.

### Pruebas automatizadas
```
cd C:\Users\migue\Desktop\SLS_Bot
venv\Scripts\python -m pytest bot/tests
SLS_API_BASE=http://127.0.0.1:8880 ^
SLS_PANEL_TOKEN=panel_token ^
SLS_CONTROL_USER=panel ^
SLS_CONTROL_PASSWORD=cambia_est0 ^
venv\Scripts\python scripts/tests/e2e_smoke.py
```
Las pruebas de pytest usan `config/config.sample.json`, escriben `logs/test_pnl.jsonl` y fijan `SLS_SKIP_TIME_SYNC=1`. El script `scripts/tests/e2e_smoke.py` realiza un smoke test end-to-end contra una API en ejecución verificando `/health`, `/pnl/diario` y `/control`.

## Modelo Cerebro (entrenamiento y despliegue)
```
cd C:/Users/migue/Desktop/SLS_Bot/bot
python -m cerebro.train --dataset ../logs/cerebro_experience.jsonl --output-dir ../models/cerebro --min-auc 0.55 --min-win-rate 0.55
```
El script lee logs/cerebro_experience.jsonl, entrena una regresi�n log�stica ligera y solo promueve el artefacto a models/cerebro/active_model.json si supera los umbrales de AUC/win-rate y mejora el modelo vigente. PolicyEnsemble carga autom�ticamente ese archivo al iniciarse; basta con reiniciar el servicio del bot o el proceso de Cerebro tras cada entrenamiento.

## Servicio Cerebro IA (systemd)
```
bash APP_ROOT=/opt/SLS_Bot SVC_USER=sls ./scripts/deploy/install_cerebro_service.sh
```
El script copia `scripts/deploy/systemd/sls-cerebro.service`, reemplaza `{{APP_ROOT}}/{{SVC_USER}}`, recarga systemd y deja ejecut�ndose `python -m cerebro.service --loop`. Tras habilitarlo valida el estado con:
```
curl -fsS http://127.0.0.1:${SLS_API_PORT:-8880}/cerebro/status | jq '.time'
```


## Automatización de despliegue
- `scripts/deploy/bootstrap.sh` prepara el entorno Python/Node, ejecuta `pytest`, `npm run lint`/`build` y opcionalmente instala los servicios systemd si exportas `INSTALL_SYSTEMD=1 APP_ROOT=/opt/SLS_Bot SVC_USER=sls`.
- `scripts/deploy/systemd/*.service` incluyen plantillas para `sls-api`, `sls-bot` y `sls-panel`. El script reemplaza `{{APP_ROOT}}` y `{{SVC_USER}}` automáticamente; si lo haces a mano, ajusta esas cadenas y copia los archivos a `/etc/systemd/system/`.
- `scripts/deploy/README.md` describe cómo generar `/etc/sls_bot.env`, configurar Nginx (Basic Auth + cabecera `X-Forwarded-User`) y rotar tokens sin downtime.

## Panel Next.js
### Instalar deps (Terminal VS Code local)
```
cd C:\Users\migue\Desktop\SLS_Bot\panel
npm install
```
### Ejecutar
```
npm run dev
```
El panel leerá `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_PANEL_API_TOKEN` y `NEXT_PUBLIC_CONTROL_AUTH_MODE` desde `panel/.env`. La tarjeta **Cerebro IA** permite filtrar por s�mbolo/timeframe, forzar una decisi�n (POST `/cerebro/decide`) y graficar la confianza usando el historial expuesto por `/cerebro/status`.
### Lint / Build
```
npm run lint
npm run build
```
`lint` usa `eslint-config-next` (core-web-vitals) y `build` valida tipos antes de generar el bundle.

## Docker (opcional)
`docker-compose.yml` levanta solo el panel en modo host. Ajusta el archivo si quieres incluir la API/control.

## Comandos utiles
- `venv\Scripts\python -m uvicorn sls_bot.app:app --reload` para desarrollo rapido.
- `npm run build && npm run start` para revisar el bundle productivo.
- `npm run lint` para validar el panel antes de publicar.
- `venv\Scripts\python -m pip install -r bot/requirements-ia.txt` para habilitar el motor IA.
- El bot escribe datos reales en `logs/decisions.jsonl`, `logs/bridge.log` y `logs/pnl.jsonl`, que el panel consume en vivo.

## Estructura
```
bot/
  sls_bot/
  requirements*.txt
  tests/
panel/
  app/
  package.json
config/
  config.sample.json
logs/ (ignorado)
excel/ (ignorado)
```

## Notas de seguridad
- Nunca publiques `config/config.json`, `.env` ni `panel/.env`.
- Mantén `CONTROL_USER/CONTROL_PASSWORD`, `PANEL_API_TOKENS` y cualquier `.env` fuera del repo.
- Restringe CORS (`ALLOWED_ORIGINS`) a tus dominios y usa HTTPS detras de Nginx.
- Configura systemd, Nginx + Certbot y ufw (solo 22/80/443) como indica el paquete de traspaso.
