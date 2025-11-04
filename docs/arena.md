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

## CLI recomendado
- `python scripts/ops.py arena tick` corre un ciclo puntual (lo mismo que `run_arena_tick.sh`).
- `python scripts/ops.py arena run --interval 120` levanta el servicio embebido con `ArenaService` y actualiza ranking/ledger en loop.
- `python scripts/ops.py arena promote <id>` empaqueta una estrategia campeona con sus metadatos.
- `python scripts/ops.py arena ranking --limit 20` y `state` permiten auditar el top actual o la copa sin abrir archivos.

Todos estos comandos comparten la misma configuración (`bot/core/settings.py`), así que el CLI respeta tus `.env` y rutas.

## Pruebas
- `bot/tests/test_arena_routes.py` valida que los endpoints `/arena/*` respetan autenticación (`X-Panel-Token`) y delegan en `ArenaService`, `ArenaStorage` y `export_strategy` según corresponda.
- Al ejecutar `python scripts/ops.py qa` se corre `pytest` (incluyendo las pruebas anteriores) y el lint del panel para detectar regresiones antes de publicar.

## Próximos pasos
1. Automatizar `LeagueManager` como servicio (`python scripts/ops.py arena run` o `python -m bot.arena`).
2. Extender el simulador con diferentes motores (martingale, mean reversion, news driven) para alimentar
   las 5 000 estrategias.
3. Conectar el ranking al panel y permitir “draft picks” para seleccionar estrategias a modo real (el endpoint ya está disponible; falta integrar la UI).
4. Añadir pruebas unitarias del registro/simulador y generar datasets de entrenamiento a partir del ledger.
