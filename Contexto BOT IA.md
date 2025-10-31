# Contexto BOT IA

Este documento resume la arquitectura actual del repositorio **SLS_Bot** y sirve como punto de partida cuando se abre un nuevo chat o cuando alguien más toma el relevo. Cada vez que modifiquemos archivos clave deberíamos regresar aquí y actualizar la sección correspondiente.

---

## Bitácora Codex 2025-10-31
- `scripts/tools/infra_check.py` ahora valida tokens (`token@YYYY-MM-DD`), detecta contraseñas por defecto y admite `--ensure-dirs` para crear `logs/{mode}`, `excel/{mode}` y `models/cerebro/{mode}`.
- Nuevo `scripts/tools/healthcheck.py` centraliza los pings a `/health`, `/status`, `/cerebro/status`, `/pnl/diario` y `/control/sls-bot/status`.
- `Makefile` incluye `infra-check`, `setup-dirs`, `health` y `smoke` para simplificar las comprobaciones manuales.
- Se crearon los directorios `logs/real`, `excel/real`, `models/cerebro/real` y `models/cerebro/test`.

---

## Modos operativos (TEST vs REAL)
- El archivo `config/config.json` ahora sigue el esquema `shared + modes`. El modo activo se elige con `SLSBOT_MODE` (`test` por defecto).  
- Rutas sensibles (logs, excel, modelos) aceptan el token `{mode}` para mantener separados los datos de pruebas (`logs/test`, `excel/test`, `models/cerebro/test`) y producción (`.../real`).  
- El cargador (`bot/sls_bot/config_loader.py`) combina `shared` + `modes.<activo>` y expone `_active_mode`, `_available_modes` y `_mode_config_path`.  
- Siempre que arranques un servicio systemd o un proceso manual (bot, Cerebro, panel) exporta `SLSBOT_MODE` para evitar mezclar credenciales o datos.

---

## Directorios y servicios principales
| Ruta | Descripción |
| --- | --- |
| `bot/` | Backend FastAPI + webhook del bot (`sls_bot.app`), helpers de Excel, cliente Bybit y router de control (`app.main`). |
| `bot/cerebro/` | Servicio “Cerebro IA” que observa el mercado, genera decisiones y mantiene memoria/experiencias. Usa modelos por modo (`models/cerebro/<mode>`). |
| `panel/` | Panel Next.js 14 que consume la API (`/status`, `/cerebro/*`, `/pnl/diario`). Ejecutar `npm run dev/lint/build`. |
| `config/` | `config.sample.json` con la estructura multi-modo. Copiar a `config.json` (no versionar). |
| `logs/{mode}/` | Bridge logs, decisiones, PnL, estado de riesgo y datasets Cerebro segregados por modo. |
| `excel/{mode}/` | Libros `26. Plan de inversión.xlsx` vinculados a operaciones/eventos del modo correspondiente. |
| `models/cerebro/{mode}/` | Artefactos activos y candidatos del Cerebro IA segregados por modo. |
| `scripts/` | Deploy (`scripts/deploy`), pruebas (`scripts/tests/e2e_smoke.py`), utilidades Python (`scripts/tools/*.py`) y el gestor `scripts/manage.sh`. |

---

## Archivos clave y propósito
- `bot/sls_bot/app.py`: Webhook principal, integra Bybit, risk-management, escritura Excel, logging y usa las rutas por modo. Helpers `utc_now*` y `_path_or_default` resuelven rutas relativas.  
- `bot/app/main.py`: API de control/panel. Expone `/status`, `/logs/*`, `/pnl/diario`, incluye el modo activo en la respuesta y lee los mismos directorios que el bot.  
- `bot/sls_bot/config_loader.py`: Parser robusto (comentarios, comas) + motor de perfiles (`modes`). Usa `SLSBOT_MODE` y tokens `{mode}` para generar rutas.  
- `bot/cerebro/service.py`: Servicio continuo del Cerebro. Guarda decisiones/experiencias en `logs/<mode>/cerebro_*.jsonl` y carga modelos desde `models/cerebro/<mode>/active_model.json`. Reporta el modo en `/cerebro/status`.  
- `bot/cerebro/train.py`: Entrenamiento ligero (logistic regression). `--mode` autodetecta rutas de dataset/modelos según el modo. Añade campo `mode` al artefacto.  
- `scripts/tools/promote_strategy.py`: Copia `active_model.json` desde el modo de prueba al real cuando las métricas superan los umbrales y opcionalmente archiva/reset el dataset de experiencias del modo prueba.  
- `scripts/tools/infra_check.py`: Valida `.env` y `config.json`, comprueba tokens (`token@YYYY-MM-DD`), detecta contraseñas por defecto y con `--ensure-dirs` crea `logs/{mode}`, `excel/{mode}` y `models/cerebro/{mode}`.  
- `scripts/tools/healthcheck.py`: Lanza GET/POST a `/health`, `/status`, `/cerebro/status`, `/pnl/diario` y `/control/sls-bot/status` y devuelve un resumen JSON del estado.
- `README.md`: Documentación general (instrucciones de entorno, pruebas, despliegue, explicación modos/prueba-real y comandos de entrenamiento/promoción).  
- `docs/roadmap.md`: Estado detallado de los 10 objetivos del bot y los 10 objetivos del Cerebro IA con progreso por fases.
- `.env.example`: Ejemplo de variables, incluye `SLSBOT_MODE`, credenciales panel y Bybit.  
- `bot/tests/test_health.py`: Tests FastAPI ajustados para usar `logs/<mode>`; ejecutar `venv\Scripts\python -m pytest bot/tests -q`.

---

## Flujo recomendado (modo prueba → modo real)
1. **Infra check**: `python scripts/tools/infra_check.py --env-file .env` para validar credenciales y rutas.  
2. **Modo prueba**: `SLSBOT_MODE=test` al iniciar `sls_bot.app`, `app.main` y `cerebro.service`. Ejecutar `scripts/tests/e2e_smoke.py` para comprobar la API.  
3. **Entrenamiento**: `python -m cerebro.train --mode test --min-auc ...` genera artefactos en `models/cerebro/test/`.  
4. **Promoción**: `python scripts/tools/promote_strategy.py --source-mode test --target-mode real` copia el modelo a `models/cerebro/real/active_model.json` y rota el dataset de test (opcional).  
5. **Modo real**: iniciar servicios con `SLSBOT_MODE=real`, apuntando a llaves Bybit reales. El panel debe consumir la API del modo real para ver operaciones/cooldowns productivos.  
6. **Iterar**: tras cada promoción, entrenar un nuevo candidato en modo prueba para mantener un pipeline continuo de estrategias.

---

## Convenciones de mantenimiento
- **Cualquier cambio en rutas, config o comportamiento** debe reflejarse aquí (archivo nuevo o sección actualizada) para preservar el contexto histórico.  
- **Nombres de archivos**: usa rutas relativas (`bot/sls_bot/app.py`) para que sean clicables desde la CLI.  
- **Formato**: Markdown plano para mantener compatibilidad con cualquier editor. Añade secciones/separadores si crece el alcance.  
- **Versionado**: incluye este archivo en cualquier PR/commit que modifique la arquitectura o instructivos operativos. De ese modo siempre estará sincronizado con la base de código.
