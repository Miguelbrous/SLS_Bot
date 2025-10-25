# SLS_Bot

Panel (Next.js 14 + TS) nativo en Windows y API FastAPI que corre en VPS Linux. El repo tambien incluye stubs y utilidades IA para generar decisiones desde Bybit.

## Arquitectura
- `bot/` FastAPI + PyBit, maneja webhooks, control de riesgo, escritura en Excel, endpoints IA.
- `panel/` Next.js 14 (app router) que consulta la API via `NEXT_PUBLIC_API_BASE`.
- `config/` plantillas y secretos locales (no subir `config.json`).
- `logs/`, `excel/`, `models/` contienen datos generados en tiempo real y no se versionan.

## Variables de entorno
1. Copia `.env.example` como `.env` en la raiz (Terminal Windows PC).
2. Copia `panel/.env.example` como `panel/.env` (Terminal VS Code local).
3. Para la API, copia `config/config.sample.json` a `config/config.json` y completa tus claves. Si trabajas en el VPS, sube solo la version cifrada.

## Requisitos
- Python 3.11+ (se recomienda 3.11 para evitar problemas con dependencias cuantitativas).
- Node.js 20 LTS para el panel.
- `pip` y `npm` disponibles en la terminal que uses.

## Backend FastAPI
### Instalar deps (Terminal Windows PC)
```
cd C:\Users\migue\Desktop\SLS_Bot
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r bot/requirements-dev.txt
```
`bot/requirements-ia.txt` agrega numpy/pandas/sklearn/xgboost si necesitas el motor IA (recomendado hacerlo en Linux con toolchain disponible).

### Ejecutar local (Terminal Windows PC)
```
cd C:\Users\migue\Desktop\SLS_Bot\bot
set PYTHONPATH=%cd%
set SLSBOT_CONFIG=..\config\config.json
set PORT=8080
..\venv\Scripts\uvicorn sls_bot.app:app --host 127.0.0.1 --port %PORT%
```

### Ejecutar en VPS (Terminal VS Code remoto)
```
cd ~/SLS_Bot/bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SLSBOT_CONFIG=/root/SLS_Bot/config/config.json
uvicorn sls_bot.app:app --host 0.0.0.0 --port 8880
```
Integra con systemd (`sls-api.service`) y Nginx tal como se describe en la documentacion de traspaso.

### Pruebas automatizadas
```
cd C:\Users\migue\Desktop\SLS_Bot
venv\Scripts\python -m pytest bot/tests
```
Las pruebas usan `config/config.sample.json` y fijan `SLS_SKIP_TIME_SYNC=1` para evitar llamadas a Bybit en CI.

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
El panel leera `NEXT_PUBLIC_API_BASE` de `panel/.env`.

## Docker (opcional)
`docker-compose.yml` levanta solo el panel en network host. Ajusta para incluir la API si deseas stack completo.

## Comandos utiles
- `venv\Scripts\python -m uvicorn sls_bot.app:app --reload` para desarrollo rapido.
- `npm run build && npm run start` para revisar el bundle productivo del panel.
- `venv\Scripts\python -m pip install -r bot/requirements-ia.txt` para habilitar el motor IA.

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
- Nunca publiques `config/config.json` ni `panel/.env`.
- Restringe CORS en FastAPI cuando despliegues el panel.
- Usa systemd + Nginx + Certbot (TLS) descritos en el paquete de traspaso.
- Configura ufw para exponer solo 22/80/443.
