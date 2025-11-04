# Contexto BOT IA

Este documento resume la arquitectura actual del repositorio **SLS_Bot** y sirve como punto de partida cuando se abre un nuevo chat o cuando alguien más toma el relevo. Cada vez que modifiquemos archivos clave deberíamos regresar aquí y actualizar la sección correspondiente.

## Bitácora Codex 2025-11-03 (tarde)
- Se habilitó compatibilidad retro con `/ia/signal` para clientes legacy (`simbolo/marco`) volviendo a usar `ia_signal_engine` cuando no llega un `Signal` completo. Quedó un log explícito de quién envía payloads incompletos.
- `micro_scalp_v1` ahora opera con filtros más laxos (EMA ≥3 bps, RSI 40-60) para producir más trades en testnet.
- Nueva estrategia `scalp_rush_v1` (1m) añadida al runner; basta con `STRATEGY_ID=scalp_rush_v1` para encenderla en testnet y forzar prueba/error constante.
- Nació la **Arena de estrategias** (`bot/arena/`): registro masivo de 5 000 estrategias, simulador compartido, league manager, ranking público y script `scripts/arena_bootstrap.py` para regenerar el roster.
- Documentación añadida en `docs/arena.md` y README para explicar la “carrera” y el proceso de promoción a modo real.
- FastAPI expone `/arena/ranking` y `/arena/state` (token panel) para que el dashboard consulte el leaderboard generado por `python -m bot.arena`.
- Tips operativos: define en `.env` `STRATEGY_ID=scalp_rush_v1` y `STRATEGY_INTERVAL_SECONDS=30`, agenda `scripts/run_arena_tick.sh` y usa `python scripts/promote_arena_strategy.py <strategy_id>` al seleccionar estrategias para modo real.
- Nuevo CLI `python scripts/ops.py` centraliza `up/down/status/logs`, healthcheck y acciones de arena para no depender de múltiples scripts.
- El CLI ahora incluye `ops infra` y `ops cerebro dataset/promote` para validar infraestructura y operar el Cerebro sin buscar scripts; añadimos pruebas automatizadas para el propio CLI y para los endpoints `/arena/*`.
- `bot/core/settings.py` unifica la lectura de `.env` mediante Pydantic, así loop y CLI comparten los mismos defaults (estrategia, intervalos, firma, modo).
- `bot/arena/service.py` introduce `ArenaService`, un loop embebido que puedes levantar con `python scripts/ops.py arena run` para mantener ranking/state sin depender de cron.
- `bot/arena/storage.py` agrega `arena.db` (SQLite) para registrar ledger e inspeccionar ranking desde el CLI sin depender sólo de JSON.
- `scripts/promote_arena_strategy.py` ahora genera carpetas completas (`profile.json`, `ledger_tail.json`, `SUMMARY.md`) para facilitar la revisión/promoción de estrategias ganadoras.
- API expone `/arena/ledger` y el panel cuenta con `/arena` para consumir ranking + ledger con filtros directamente desde la UI.
- Nuevos endpoints `POST /arena/tick` y `POST /arena/promote` permiten operar la arena (forzar tick/exportar) desde el panel vía botones dedicados.
- `/metrics` ahora expone métricas (Prometheus) gracias a `prometheus-fastapi-instrumentator`, útil para observabilidad externa.
- `scripts/ops.py` ahora incluye comandos `deploy bootstrap/rollout` y `monitor check` para orquestar systemd + enviar alertas Slack/Telegram cuando la arena se estanca o supera el drawdown configurado (ver `scripts/tools/monitor_guard.py`).
- `cup_state.json` registra `last_tick_ts`, `ticks_since_win`, `drawdown_pct` y los endpoints `/arena/state` actualizan métricas `sls_arena_*` que se consumen vía `/metrics`.
- Promover una estrategia ahora ejecuta validaciones (mínimo de trades, Sharpe y drawdown); el CLI/endpoint aceptan `--force`/`force=true` y generan `validation.json` con los métricos utilizados.
- `python scripts/ops.py arena notes add/list` y los endpoints `/arena/notes` registran bitácoras para cada estrategia directamente en `arena.db`, útil antes de moverlas a real.
- `make monitor-check` envuelve el monitor de arena (`ops monitor check`) y publica los nuevos gauges `sls_bot_drawdown_pct` y `sls_cerebro_decisions_per_min`, ideales para cron/CI y dashboards Grafana.

---

## Guía para nuevos chats
- **Visión del proyecto**: Bot de trading de futuros Bybit 24/7 con TP/SL obligatorios, autopiloto (SL→BE tras TP1), guardias de riesgo y Cerebro IA que aprende de cada operación. La arena (5 000 estrategias) corre en paralelo y promueve ganadoras a modo real.
- **Qué SÍ tocar**: backend FastAPI (`bot/`), Cerebro (`bot/cerebro/`), arena (`bot/arena/`), panel (`panel/`), scripts (`scripts/ops.py`, `scripts/run_arena_tick.sh`), estrategias (`bot/strategies/`). Cada cambio funcional debe reflejarse en `README.md`, `Contexto BOT IA.md` y en la doc específica (`docs/arena.md`, `docs/cerebro.md`, etc.).
- **Qué NO tocar**: credenciales reales (`.env`, `config/config.json`), autopiloto y lógica crítica de riesgo sin pruebas/migraciones claras, directorios generados (`logs/`, `excel/`, `models/`, `tmp_*`), modelos en producción (`models/cerebro/real/`). Nunca publicar tokens/urls privadas.
- **Comandos clave**: `python scripts/ops.py up/down/status/logs/qa`, `python scripts/ops.py arena run/tick/promote`, `python scripts/promote_arena_strategy.py <id>`, `./run SLS_Bot start`. El panel ofrece `/dashboard` y `/arena`; la API expone `/metrics`, `/arena/*`, `/dashboard/*`.
- **Documentación**: responder siempre en español; al modificar flujos actualizar `README.md`, `Contexto BOT IA.md` y los docs específicos (ej. `docs/arena.md`). Mantener sección Bitácora sincronizada.
- **Estado reciente**: CLI unificado (`scripts/ops.py`), settings centralizados (`bot/core/settings.py`), arena con servicio embebido + SQLite (`arena.db`), panel Arena completo, endpoints `/arena/tick`, `/arena/promote`, `/arena/ledger`, métricas Prometheus (`/metrics`). Cualquier evolución debe respetar esta arquitectura.

---

## Bitácora Codex 2025-10-31
- Se agregó ingesta `macro` (open interest / funding / whale flow) para el Cerebro, con cache configurable y scoring integrado al `PolicyEnsemble`.
- Nuevo guardia `low_capital` limita margen y riesgo para cuentas pequeñas (≈5 €) y ajusta el leverage automáticamente.
- Se añadió el módulo `bot/strategies/` con el runner CLI y la estrategia inicial `micro_scalp_v1` lista para operar en testnet.
- `scripts/tools/infra_check.py` ahora valida tokens (`token@YYYY-MM-DD`), detecta contraseñas por defecto y admite `--ensure-dirs` para crear `logs/{mode}`, `excel/{mode}` y `models/cerebro/{mode}`.
- Nuevo `scripts/tools/healthcheck.py` centraliza los pings a `/health`, `/status`, `/cerebro/status`, `/pnl/diario` y `/control/sls-bot/status`.
- Nuevo `scripts/tools/rotate_artifacts.py` archiva logs/modelos antiguos por modo y está conectado a `make rotate-artifacts`.
- `Makefile` incluye `infra-check`, `setup-dirs`, `rotate-artifacts`, `health` y `smoke` para simplificar las comprobaciones manuales.
- `scripts/manage_bot.py` incorpora reintentos configurables (`--retries/--retry-delay`) y registra cada intento en la salida JSON.
- Cerebro IA integra ingestión en cola, detector de anomalías, umbral dinámico de confianza, evaluación A/B, versionado de modelos, pipelines de entrenamiento y reporter diario (ver `docs/cerebro.md`).
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
| `bot/strategies/` | Estrategias autónomas (ej. `micro_scalp_v1`) y runner CLI para disparar señales firmadas al webhook. |
| `panel/` | Panel Next.js 14 que consume la API (`/status`, `/cerebro/*`, `/pnl/diario`). Ejecutar `npm run dev/lint/build`. |
| `config/` | `config.sample.json` con la estructura multi-modo. Copiar a `config.json` (no versionar). |
| `logs/{mode}/` | Bridge logs, decisiones, PnL, estado de riesgo y datasets Cerebro segregados por modo. |
| `excel/{mode}/` | Libros `26. Plan de inversión.xlsx` vinculados a operaciones/eventos del modo correspondiente. |
| `models/cerebro/{mode}/` | Artefactos activos y candidatos del Cerebro IA segregados por modo. |
| `logs/{mode}/metrics` / `logs/{mode}/reports` | Métricas A/B del Cerebro y reportes diarios por sesión. |
| `scripts/` | Deploy (`scripts/deploy`), pruebas (`scripts/tests/e2e_smoke.py`), utilidades Python (`scripts/tools/*.py`) y el gestor `scripts/manage.sh`. |
| `docs/data_sources.md` | Catálogo de dashboards externos (Coinglass, CoinMarketCap, Coin360) con notas sobre APIs y uso manual. |

---

## Archivos clave y propósito
- `bot/sls_bot/app.py`: Webhook principal, integra Bybit, risk-management, escritura Excel, logging y usa las rutas por modo. Helpers `utc_now*` y `_path_or_default` resuelven rutas relativas.  
- `bot/app/main.py`: API de control/panel. Expone `/status`, `/logs/*`, `/pnl/diario`, incluye el modo activo en la respuesta y lee los mismos directorios que el bot.  
- `bot/sls_bot/config_loader.py`: Parser robusto (comentarios, comas) + motor de perfiles (`modes`). Usa `SLSBOT_MODE` y tokens `{mode}` para generar rutas.  
- `bot/cerebro/service.py`: Servicio continuo del Cerebro. Guarda decisiones/experiencias en `logs/<mode>/cerebro_*.jsonl` y carga modelos desde `models/cerebro/<mode>/active_model.json`. Reporta el modo en `/cerebro/status`.  
- `bot/cerebro/train.py`: Entrenamiento ligero (logistic regression). `--mode` autodetecta rutas de dataset/modelos según el modo. Añade campo `mode` al artefacto.  
- `bot/cerebro/ingestion.py`: Gestor de colas y cache TTL para data sources de mercado/noticias.  
- `bot/cerebro/anomaly.py` / `confidence.py`: Detector de anomalías mediante z-score y compuerta dinámica de confianza.  
- `bot/cerebro/evaluation.py`: Métricas A/B entre heurística vs ML persistidas en `logs/<mode>/metrics`.  
- `bot/cerebro/versioning.py` / `pipelines.py`: Registro de modelos, promoción/rollback y pipeline de entrenamiento offline/online.  
- `bot/cerebro/reporting.py`: Reporter diario por sesión (`logs/<mode>/reports`).  
- `bot/cerebro/simulator.py`: Simulaciones ligeras para validar la consistencia de las señales.  
- `scripts/tools/promote_strategy.py`: Copia `active_model.json` desde el modo de prueba al real cuando las métricas superan los umbrales y opcionalmente archiva/reset el dataset de experiencias del modo prueba.  
- `scripts/tools/infra_check.py`: Valida `.env` y `config.json`, comprueba tokens (`token@YYYY-MM-DD`), detecta contraseñas por defecto y con `--ensure-dirs` crea `logs/{mode}`, `excel/{mode}` y `models/cerebro/{mode}`.  
- `scripts/tools/healthcheck.py`: Lanza GET/POST a `/health`, `/status`, `/cerebro/status`, `/pnl/diario` y `/control/sls-bot/status` y devuelve un resumen JSON del estado.
- `scripts/tools/rotate_artifacts.py`: Archiva logs y modelos antiguos en `archive/` por modo; integrado con `make rotate-artifacts`.
- `scripts/manage_bot.py`: Controla servicios systemd con validación opcional de `.env`, soporta reintentos (`--retries`) y exporta la traza de intentos.
- `scripts/manage.sh`: Ahora coordina API, bot, Cerebro y el loop de estrategia (`encender-*`, `apagar-*`, `estado`, `tail`).
- `run`: wrapper en la raíz; con `run SLS_Bot [start|stop|status|logs]` se orquesta todo sin recordar comandos largos.
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
