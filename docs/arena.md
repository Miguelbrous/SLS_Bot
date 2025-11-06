# Arena de Estrategias SLS

La arena permite ejecutar miles de estrategias simuladas en paralelo sin consumir la API de Bybit. Cada
estrategia recibe el mismo stream de velas pero opera en un espacio aislado con su propio balance virtual.

## Componentes
- `bot/arena/config.py` y `cup_config.json`: definen capital inicial, meta, incremento tras cada victoria y
  la cantidad máxima de estrategias activas.
- `bot/arena/registry.py`: registro central (`registry.json`) con 5 000 estrategias generadas automáticamente.
  Cada entrada mantiene categoría, timeframe, indicadores y estadísticas (balance, meta, drawdown).
- `bot/arena/simulator.py`: simulador ligero que reutiliza `ia_utils.latest_slice` para compartir velas y
  calcular PnL virtual por estrategia.
- `bot/arena/league_manager.py`: orquestador que selecciona estrategias activas (`training`/`race`), corre el
  simulador y promueve campeones cuando superan la meta global. El objetivo aumenta en +50 € tras cada victoria
  y persiste el ledger/estado en `arena.db` mediante `bot/arena/storage.py`.
- `bot/arena/ranking.py`: genera `bot/arena/ranking_latest.json` con el top de estrategias ordenado por progreso.

## Generar estrategias
```
cd SLS_Bot
source venv/bin/activate
PYTHONPATH=. python scripts/arena_bootstrap.py --total 5000
```

## Integración
- FastAPI expone `/arena/ranking`, `/arena/state`, `/arena/ledger`, `POST /arena/tick` y `POST /arena/promote`
  (requieren token del panel). Puedes forzar un tick, obtener paquetes listos para promoción o inspeccionar ledger sin
  dejar la UI.
- Cuando una estrategia alcanza la meta vigente pasa a `champion` y se marca como candidata para modo real.
  Su carpeta en `bot/arena/strategies/<id>/` puede contener código personalizado y seguirá aprendiendo aun
  después de ser promovida.
- Para exportar una estrategia ganadora y promoverla fuera de la arena usa
  `python scripts/promote_arena_strategy.py <strategy_id>` (o el endpoint correspondiente); se genera `bot/arena/promoted/<id>/`
  con `profile.json`, `ledger_tail.json` y `SUMMARY.md` para facilitar el traspaso a modo real.
- `bot/arena/cup_state.json` mantiene `current_goal`, `goal_increment`, `wins`, `last_tick_ts`, `ticks_since_win`, `drawdown_pct`
  y `last_tick_promoted`. Estos campos alimentan tanto el panel como los tableros de observabilidad.

## CLI recomendado
- `python scripts/ops.py arena tick` corre un ciclo puntual (lo mismo que `run_arena_tick.sh`).
- `python scripts/ops.py arena run --interval 120` levanta el servicio embebido con `ArenaService` y actualiza ranking/ledger en loop.
- `python scripts/ops.py arena promote <id>` empaqueta una estrategia campeona con sus metadatos.
- `python scripts/ops.py arena ranking --limit 20` y `state` permiten auditar el top actual o la copa sin abrir archivos.
- `python scripts/ops.py arena promote <id> --min-trades 80 --min-sharpe 0.4 --max-drawdown 25` bloquea la exportación si los umbrales no se cumplen (usa `--force` para omitirlos); se genera `validation.json` con los motivos.
- `python scripts/ops.py arena promote-real <id> --source-mode test --target-mode real` genera el paquete y promueve automáticamente el modelo de Cerebro si supera los umbrales (`--min-auc`, `--min-win-rate`). Deja registro en `logs/promotions/promotion_log.jsonl`.
- `python scripts/ops.py arena notes add/list` registra notas de experimento directamente en `arena.db`, útiles para compartir hallazgos antes de promover.
- `python scripts/ops.py arena ledger <id> --limit 200 --csv out.csv` inspecciona el ledger histórico (los mismos datos que consume el panel) y permite exportarlo a CSV para auditorías/backup rápido.
- `python scripts/ops.py arena stats <id> --json` calcula estadísticas clave del ledger (PnL acumulado/promedio, win rate, max drawdown, balance final) para compararlas con los gráficos del panel o automatizar alertas.

Todos estos comandos comparten la misma configuración (`bot/core/settings.py`), así que el CLI respeta tus `.env` y rutas.

## Notas y workflow de promoción
- `POST /arena/notes` y `GET /arena/notes?strategy_id=...` permiten registrar/leer bitácoras desde el panel o scripts (las notas se guardan en SQLite y también están disponibles vía `ops arena notes *`).
- El panel `/arena` ahora permite filtrar el ledger (todas/ganadoras/perdedoras), ver métricas agregadas (PnL total/promedio, win rate) y exportar las operaciones a CSV directamente desde la UI, además de buscar notas por autor/texto. El ranking también tiene filtros por categoría, búsqueda libre y mínimos de trades/score, junto con indicadores promedio para tomar decisiones más rápido.
- La promoción ejecuta validaciones automáticas (`min_trades`, `min_sharpe`, `max_drawdown`). Si falla, la API/CLI devuelve un `400` explicando los motivos; puedes usar `force=true` o `--force` para omitirlas, aunque se registrará igualmente `validation.json`.

## Pruebas
- `bot/tests/test_arena_routes.py` valida que los endpoints `/arena/*` respetan autenticación (`X-Panel-Token`) y delegan en `ArenaService`, `ArenaStorage` y `export_strategy` según corresponda.
- Al ejecutar `python scripts/ops.py qa` se corre `pytest` (incluyendo las pruebas anteriores) y el lint del panel para detectar regresiones antes de publicar.

## Métricas y monitoreo
- FastAPI expone métricas Prometheus adicionales (`sls_arena_current_goal_eur`, `sls_arena_goal_drawdown_pct`, `sls_arena_state_age_seconds`, `sls_arena_ticks_since_win`, `sls_arena_total_wins`, `sls_bot_drawdown_pct`, `sls_cerebro_decisions_per_min`). Se actualizan automáticamente al consultar `/arena/state` o durante el scrape de `/metrics`.
- `python scripts/ops.py monitor check --api-base https://api --panel-token XXX --slack-webhook ...` ejecuta `scripts/tools/monitor_guard.py`, revisa `/arena/state` + `/metrics` y envía alertas (Slack o Telegram) cuando el drawdown o el lag superan los umbrales. Para integrarlo a cron/CI usa `make monitor-check PANEL_TOKEN=... SLACK_WEBHOOK=...`.

## Próximos pasos
1. Automatizar `LeagueManager` como servicio (`python scripts/ops.py arena run` o `python -m bot.arena`).
2. Extender el simulador con diferentes motores (martingale, mean reversion, news driven) para alimentar
   las 5 000 estrategias.
3. Conectar el ranking al panel y permitir “draft picks” para seleccionar estrategias a modo real (el endpoint ya está disponible; falta integrar la UI).
4. Añadir pruebas unitarias del registro/simulador y generar datasets de entrenamiento a partir del ledger.
