# Cerebro: Motor IA Autoaprendizaje

Cerebro es el servicio de IA que acompana al bot principal: observa el mercado, aprende de los
resultados reales y propone ajustes de riesgo en tiempo real. Esta revision incorpora protecciones
para las aperturas de mercados institucionales y un analizador ligero de noticias.

## Objetivos

1. **Observabilidad continua**: recopila velas, indicadores propios, estado de riesgo del bot y feeds RSS.
2. **Aprendizaje iterativo**: guarda cada trade real en la memoria de experiencias para reentrenar modelos.
3. **Retroalimentacion inmediata**: expone decisiones con confianza, riesgo sugerido y razones.
4. **Gobernanza del riesgo**: incluye reglas de drawdown y ahora una "session guard" para horas criticas.

## Componentes

- **DataIngestionManager**: mantiene una cola FIFO de tareas para `market`, `news` y ahora `macro` (open interest/funding/whale flow), con cache TTL configurable (`data_cache_ttl`). Evita golpear los endpoints si los datos siguen frescos.
- **FeatureStore**: buffer circular (max 500) por símbolo/timeframe. Calcula medias/varianzas y ofrece slices normalizados para alimentar el modelo ML.
- **AnomalyDetector**: valida cada ventana con z-score; cuando detecta un outlier fuerza `NO_TRADE` y añade el motivo en metadata.
- **MacroDataSource + MacroPulse**: consulta endpoints configurables de open interest/funding/ballenas, genera un `macro score` y lo incorpora a la decisión (ajusta riesgo y puede bloquear trades).
- **DynamicConfidenceGate**: ajusta el umbral mínimo de confianza según volatilidad, calidad del dataset y anomalías.
- **ExperienceMemory**: cola de tamaño configurable que guarda `features + pnl + decision` para el aprendizaje.
- **PolicyEnsemble**: combina `ia_signal_engine`, heurísticas y el modelo entrenado. Usa features normalizados, sentimiento, guardias y resultados del detector de anomalías.
- **EvaluationTracker**: lleva métricas `ml_vs_heuristic` persistidas en `logs/<mode>/metrics/cerebro_evaluation.json`.
- **ModelRegistry + TrainingPipeline**: registra cada artefacto (`registry.json`), permite `promote/rollback` y lanza entrenamientos offline con `python -m cerebro.train`. El pipeline online deja pistas para reentrenar en background.
- **BacktestSimulator**: corre simulaciones ligeras sobre las últimas velas para estimar PnL promedio y exponerlo en metadata.
- **ReportBuilder**: agrupa resultados por sesión (trades, wins, bloqueos) y genera `logs/<mode>/reports/cerebro_daily_report.json`.
- **API Router**: expone `/cerebro/status`, `/cerebro/decide`, `/cerebro/learn` y `/cerebro/decisions` dentro del FastAPI principal.

## Flujo rapido

1. Los data sources se encolan (`IngestionTask`) y el manager rellena cache para mercado/noticias.
2. `FeatureStore` actualiza buffers y devuelve slices normalizados + stats por símbolo/timeframe.
3. `AnomalyDetector` y `DynamicConfidenceGate` ajustan el umbral mínimo antes de pasar por `PolicyEnsemble`.
4. La política genera la decisión, simula un micro backtest y anota metadata (anomalías, confianza dinámica, score ML).
5. `EvaluationTracker` y `ReportBuilder` guardan métricas de desempeño y bloqueos por sesión.
6. Cada trade real pasa a `ExperienceMemory`, se persiste en `logs/cerebro_experience.jsonl` y, si `SLS_CEREBRO_AUTO_TRAIN=1`, se lanza entrenamiento offline según el intervalo configurado.

## Proteccion ante aperturas

- **Pre-apertura** (`state=pre_open`): si falta `pre_open_minutes` para abrir (por defecto 45-60 segun region)
  el Cerebro bloquea nuevas senales y en la metadata envia `should_close_positions=true` para que el bot pueda
  reducir exposicion.
- **Post-apertura sin noticias** (`state=news_wait`): tras la campanada se esperan noticias frescas (<= `wait_for_news_minutes`).
  Mientras no llegue un titular reciente la decision se fuerza a `NO_TRADE`.
- **Post-apertura con noticia** (`state=news_ready`): si hay un titular reciente el trade solo se permite cuando
  la direccion de la noticia no contradice el lado sugerido. Aunque se apruebe, el riesgo se multiplica por
  `risk_multiplier_after_news` (tipicamente 0.7-0.8) para entrar con menos tamano.
- La metadata de cada decision incluye `session_guard` con `state`, `session_name`, ventanas `window_*_ts` y
  un `reason` amigable para mostrar en el panel.

## Configuracion (`config/config.json`)

```jsonc
"cerebro": {
  "enabled": true,
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "timeframes": ["15m", "1h"],
  "refresh_seconds": 60,
  "news_feeds": [
    "https://www.binance.com/blog/rss",
    "https://cointelegraph.com/rss"
  ],
  "macro_feeds": {
    "open_interest_url": "https://example.com/oi",
    "funding_rate_url": "https://example.com/funding",
    "whale_flow_url": "https://example.com/whales",
    "cache_dir": "./tmp_logs/macro"
  },
  "min_confidence": 0.55,
  "confidence_max": 0.7,
  "confidence_min": 0.45,
  "data_cache_ttl": 20,
  "anomaly_z_threshold": 3.0,
  "anomaly_min_points": 25,
  "auto_train_interval": 200,
  "max_memory": 5000,
  "sl_atr_multiple": 1.5,
  "tp_atr_multiple": 2.0,
  "news_ttl_minutes": 45,
  "session_guards": [
    {
      "name": "Asia (Tokyo)",
      "timezone": "Asia/Tokyo",
      "open_time": "09:00",
      "pre_open_minutes": 45,
      "post_open_minutes": 30,
      "wait_for_news_minutes": 45,
      "risk_multiplier_after_news": 0.8,
      "close_positions_minutes": 15
    },
    {
      "name": "Europa (Londres)",
      "timezone": "Europe/London",
      "open_time": "08:00",
      "pre_open_minutes": 45,
      "post_open_minutes": 45,
      "wait_for_news_minutes": 60,
      "risk_multiplier_after_news": 0.75,
      "close_positions_minutes": 20
    },
    {
      "name": "America (Nueva York)",
      "timezone": "America/New_York",
      "open_time": "09:30",
      "pre_open_minutes": 60,
      "post_open_minutes": 60,
      "wait_for_news_minutes": 60,
      "risk_multiplier_after_news": 0.7,
      "close_positions_minutes": 20
    }
  ]
}
```

- `news_ttl_minutes`: cuanto tiempo sigue siendo util una noticia para tomar decisiones si no hay sesion abierta.
- `data_cache_ttl`: segundos que se mantienen en cache las respuestas de mercado/noticias.
- `macro_feeds`: URLs opcionales para open interest / funding / whale flow; si están vacías se usan cache o payload sintético.
- `anomaly_*`: parámetros del detector z-score (umbral y muestras mínimas).
- `confidence_min` / `confidence_max`: límites inferior/superior para el umbral dinámico.
- `auto_train_interval`: cada cuántos trades se lanza un entrenamiento offline cuando `SLS_CEREBRO_AUTO_TRAIN=1`.
- `session_guards`: lista de ventanas por region. Puedes eliminar o ajustar horarios/tiempos segun la cobertura del bot.
- `risk_multiplier_after_news`: multiplicador que se aplica al `risk_pct` cuando la sesion ya abrio y hay una noticia alineada.

## Entrenamiento automático (`bot/cerebro/train.py`)

Cada vez que el bot cierra una operación se escribe `logs/cerebro_experience.jsonl` con el `pnl`, las features de la decisión
(confianza, riesgo, sentimiento de noticias, estado del guardián, etc.) y el resultado final. El comando:

```
cd bot
python -m cerebro.train --dataset ../logs/cerebro_experience.jsonl --output-dir ../models/cerebro
```

1. Limpia/normaliza las features numéricas.
2. Entrena una regresión logística ligera (gradiente descendente puro-Python).
3. Calcula métricas en un holdout (`accuracy`, `win_rate`, `auc`).
4. Guarda el artefacto (`models/cerebro/model_<timestamp>.json`) con pesos, medias/std de cada feature y métricas.
5. Solo promueve a `models/cerebro/active_model.json` cuando `auc` y `win_rate` superan `--min-auc` / `--min-win-rate`
   y además el nuevo modelo no empeora al activo.

`PolicyEnsemble` carga automáticamente `active_model.json` (si existe) y mezcla su `ml_score` con la confianza del
motor heurístico: scores bajos reducen `risk_pct`, scores altos permiten subirlo hasta el máximo configurado.

El registro de modelos (`models/cerebro/<mode>/registry.json`) guarda cada versión con métricas y etiqueta. Usa
`scripts/tools/rotate_artifacts.py` para archivar artefactos antiguos y `ModelRegistry.promote()` para reactivar uno.
Si defines `SLS_CEREBRO_AUTO_TRAIN=1`, el servicio ejecuta `python -m cerebro.train` cada `auto_train_interval` trades,
registrando automáticamente el artefacto resultante.

## Simulaciones y promoción controlada

- `Cerebro.simulate_sequence()` genera decisiones hipotéticas sobre las últimas velas cargadas y calcula un PnL simulado
  usando `BacktestSimulator`; está expuesto vía `POST /cerebro/simulate` (`symbol`, `timeframe`, `horizon`, `news_sentiment`).
- `scripts/tools/generate_cerebro_dataset.py` (o `python scripts/ops.py cerebro dataset --mode test --rows 300 --overwrite`) crea datasets sintéticos (JSONL) para ejercitar entrenamientos sin depender de fills reales.
- `scripts/tools/promote_best_cerebro_model.py --mode test --metric auc --min-value 0.6` (o `python scripts/ops.py cerebro promote ...`) escoge el modelo registrado con mejor métrica y lo promueve a `active_model.json`, dejando trazabilidad en `models/cerebro/<mode>/registry.json`.
- `python scripts/ops.py cerebro train --mode test --epochs 400 --min-auc 0.58 --min-win-rate 0.55 --dry-run` ejecuta `bot.cerebro.train`: admite `--dataset`, `--output-dir`, `--seed`, `--no-promote` y umbrales customizados para automatizar entrenamientos desde el CLI.

## Logs e historial

- `logs/cerebro_decisions.jsonl`: cada decision publicada para auditar en el panel.
- `logs/cerebro_experience.jsonl`: dataset usado por el entrenamiento.
- `logs/<mode>/metrics/cerebro_evaluation.json`: métricas A/B entre heurístico y ML.
- `logs/<mode>/reports/cerebro_daily_report.json`: resumen por sesión (trades, wins, bloqueos).
- `/cerebro/status` ahora expone `history` (últimas ~200 decisiones), `evaluation` y `report` para graficar confianza y salud del modelo.
- `/metrics` publica `sls_cerebro_decisions_per_min`, calculado sobre los últimos 15 minutos del log `cerebro_decisions.jsonl`; úsalo para alertar cuando la producción de señales cae.

## Integracion con el panel

`/cerebro/status` devuelve cada decision con un bloque `metadata`. El panel ahora muestra:

- Sentimiento de noticias y ultimo titular (si llega desde los feeds).
- Estado de la Session Guard (badge amarillo/rojo segun `block_trade`).
- Razones completas (`decision.reasons`) para auditar por que se bloqueo una senal.
- Umbral de confianza dinámico (`metadata.confidence_gate`), score ML, anomalías y simulación rápida (`metadata.simulation`).
- Filtros por símbolo/timeframe, botón **Forzar decisión** (POST `/cerebro/decide`) y el gráfico de confianza histórica.
- Para auditoría o monitoreo externo puedes consultar `/cerebro/decisions?limit=50`, que lee directamente del log JSONL y siempre entrega las entradas más recientes.

## Servicio dedicado

Si quieres orquestar Cerebro como proceso separado del bot principal, usa `scripts/deploy/install_cerebro_service.sh`. El script copia `scripts/deploy/systemd/sls-cerebro.service`, sustituye `{{APP_ROOT}}/{{SVC_USER}}`, recarga systemd y deja el servicio activo. El comando que se ejecuta es:

```
{{APP_ROOT}}/venv/bin/python -m cerebro.service --loop
```

Healthcheck recomendado (ajusta puerto/api):

```
curl -fsS http://127.0.0.1:${SLS_API_PORT:-8880}/cerebro/status | jq '.time'
```

## Ejecucion rapida

```
cd bot
SLSBOT_CONFIG=../config/config.json python -m cerebro.service --once
python -m cerebro.service --loop
```

Tambien puedes dejar que FastAPI importe `cerebro` para que los endpoints se sirvan junto al resto de la API.
