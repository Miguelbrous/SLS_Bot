# Checklist para el remoto (estructura completa)

Este repositorio **debe** tener exactamente los directorios y archivos listados. Si tu VPS no los muestra, elimina la carpeta actual y vuelve a clonar desde el origen correcto antes de continuar.

## Árbol obligatorio
```
SLS_Bot/
├─ bot/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py
│  │  ├─ models.py
│  │  ├─ services.py
│  │  └─ utils.py
│  ├─ cerebro/
│  │  ├─ __init__.py
│  │  ├─ config.py
│  │  ├─ datasources/
│  │  │  ├─ __init__.py
│  │  │  ├─ market.py
│  │  │  └─ news.py
│  │  ├─ features.py
│  │  ├─ filters.py
│  │  ├─ memory.py
│  │  ├─ policy.py
│  │  ├─ router.py
│  │  ├─ service.py
│  │  └─ train.py
│  ├─ sls_bot/
│  │  ├─ __init__.py
│  │  ├─ app.py
│  │  ├─ bybit.py
│  │  ├─ config_loader.py
│  │  ├─ excel_writer.py
│  │  ├─ ia_signal_engine.py
│  │  ├─ ia_utils.py
│  │  └─ tests/
│  │     └─ test_health.py (y demás tests)
│  ├─ requirements.txt
│  ├─ requirements-dev.txt
│  └─ requirements-ia.txt
├─ panel/
│  ├─ app/
│  ├─ components/
│  ├─ public/
│  ├─ package.json
│  └─ tsconfig.json
├─ config/
│  ├─ config.sample.json
│  └─ config.json
├─ scripts/
│  ├─ deploy/
│  │  ├─ bootstrap.sh
│  │  ├─ README.md
│  │  └─ systemd/
│  │     ├─ sls-api.service
│  │     ├─ sls-bot.service
│  │     └─ sls-cerebro.service
│  ├─ tests/
│  │  └─ e2e_smoke.py
│  └─ tools/
│     ├─ infra_check.py
│     └─ promote_strategy.py
├─ excel/           (generado; crear subcarpetas `excel/test` y `excel/real`)
├─ logs/            (generado; crear `logs/test` y `logs/real`)
├─ models/
│  └─ cerebro/
│     ├─ test/
│     └─ real/
├─ .env.example
├─ Contexto BOT IA.md
├─ Remoto con todos los las cosas estructura de arbol archivos y contenidos de archivos.md
└─ README.md
```

## Procedimiento paso a paso
1. **Reiniciar el clon si falta algo:**
   ```bash
   rm -rf SLS_Bot
   git clone <URL-del-repo> SLS_Bot
   cd SLS_Bot
   git checkout codex/autonomy
   git pull origin codex/autonomy
   ```
   Comprueba con `git status -sb` que estás en `## codex/autonomy`.

2. **Verificar el árbol:**
   ```bash
   ls
   find bot -maxdepth 2 -type d | sort
   ```
   Debes ver todos los directorios indicados arriba.

3. **Crear carpetas ignoradas por git:**
   ```bash
   mkdir -p logs/test logs/real
   mkdir -p excel/test excel/real
   mkdir -p models/cerebro/test models/cerebro/real
   ```

4. **Configurar archivos sensibles:**
   - Copia `config/config.sample.json` → `config/config.json` y rellena credenciales para `modes.test.bybit` (testnet) y `modes.real.bybit` (mainnet).  
   - Crea `./.env` (o `/etc/sls_bot.env` en VPS) a partir de `.env.example` con `SLSBOT_MODE`, `BYBIT_*`, `CONTROL_USER`, `CONTROL_PASSWORD`, `PANEL_API_TOKENS`, etc.  
   - Crea `panel/.env` usando `panel/.env.example` con `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_PANEL_API_TOKEN`, etc.

5. **Confirmación final:** si después de estos pasos vuelve a faltar cualquier archivo, estás en otro repositorio o la rama remota no coincide; repite desde el paso 1 hasta que el árbol sea idéntico al listado.
