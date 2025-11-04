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
  simulador y promueve campeones cuando superan la meta global. El objetivo aumenta en +50 € tras cada victoria.
- `bot/arena/ranking.py`: genera `bot/arena/ranking_latest.json` con el top de estrategias ordenado por progreso.

## Generar estrategias
```
cd SLS_Bot
source venv/bin/activate
PYTHONPATH=. python scripts/arena_bootstrap.py --total 5000
```

## Integración
- FastAPI ya expone `/arena/ranking` y `/arena/state` (requieren token del panel). Ambos leen
  `bot/arena/ranking_latest.json` y `bot/arena/cup_state.json`, por lo que basta ejecutar periódicamente
  `python -m bot.arena`, `scripts/run_arena_tick.sh` o `python scripts/ops.py arena run` para mantener los datos frescos.
- Cuando una estrategia alcanza la meta vigente pasa a `champion` y se marca como candidata para modo real.
  Su carpeta en `bot/arena/strategies/<id>/` puede contener código personalizado y seguirá aprendiendo aun
  después de ser promovida.
- Para exportar una estrategia ganadora y promoverla fuera de la arena usa
  `python scripts/promote_arena_strategy.py <strategy_id>`; el JSON generado en `bot/arena/promoted/` incluye
  los metadatos a replicar en el modo real.

## Próximos pasos
1. Automatizar `LeagueManager` como servicio (`python scripts/ops.py arena run` o `python -m bot.arena`).
2. Extender el simulador con diferentes motores (martingale, mean reversion, news driven) para alimentar
   las 5 000 estrategias.
3. Conectar el ranking al panel y permitir “draft picks” para seleccionar estrategias a modo real (el endpoint ya está disponible; falta integrar la UI).
4. Añadir pruebas unitarias del registro/simulador y generar datasets de entrenamiento a partir del ledger.
