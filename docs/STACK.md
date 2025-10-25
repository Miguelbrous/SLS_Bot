# Stack y puntos de entrada

## Lenguajes detectados
- **Python 3.11+** para la API/bot (`bot/sls_bot/*.py`) con FastAPI, PyBit, OpenPyXL y rutinas de IA.
- **TypeScript + React 18** para el panel (`panel/app/**/*`) sobre Next.js 14.
- **Batch/PowerShell** para automatizar el arranque local (`bot/start.bat`).
- **YAML/JSON** para `docker-compose.yml`, `config/config.json` y plantillas de despliegue.

## Gestores de dependencias actuales
- **pip/venv**: el script `bot/start.bat` crea `bot/venv` e instala FastAPI, Uvicorn, PyBit, OpenPyXL, pandas, etc.
- **npm (lockfile v3)**: `panel/package.json` y `panel/package-lock.json` administran Next.js, React y tipos.
- **(Opcional) docker**: `docker-compose.yml` levanta el panel usando la imagen de Next.js.

## Puntos de entrada principales
1. **API FastAPI**: modulo `bot/sls_bot/app.py` (`uvicorn sls_bot.app:app`) expone `/webhook`, `/daily/summary`, endpoints IA, etc.
2. **Arranque local Windows**: ejecutar `bot/start.bat` desde `Terminal Windows PC` posicionandose en `C:\Users\migue\Desktop\SLS_Bot\bot`.
3. **Panel Next.js**: en `panel/` correr `npm run dev` (Terminal VS Code local) y consumir la API publicada.
4. **Docker**: `docker-compose.yml` (Terminal VS Code local) construye `panel` con `network_mode: host` apuntando a `http://127.0.0.1:8080`.

## Observaciones inmediatas
- No existe `requirements.txt` ni `.env.example`; la configuracion sensible vive en `config/config.json` y `panel/.env`.
- El repo incluye carpetas pesadas (`bot/venv`, `panel/node_modules`, `excel/*.xlsx`, `logs/*`) que deben ignorarse en Git.
- Falta una suite minima de pruebas (`pytest` para la API y `next lint`/tests para el panel).
