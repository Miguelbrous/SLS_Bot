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

- **DataSources**: conectores a Bybit (OHLC + ATR) y RSS (titulares). Cada `fetch()` entrega diccionarios
  crudos que la politica puede consumir directamente, ahora con sentimiento NLP (`vaderSentiment`) en cada titular.
- **FeatureStore**: buffer circular (max 500) que almacena las ultimas velas por simbolo/timeframe.
- **ExperienceMemory**: cola de tamano configurable que guarda `features + pnl + decision`.
- **PolicyEnsemble**: combina `ia_signal_engine` + heuristicas de riesgo + sentimiento de noticias y un modelo ligero entrenado con los trades reales (logística).
- **MarketSessionGuard** (nuevo): detecta las ventanas de apertura (Asia/Europa/USA) y bloquea/reduce
  operaciones segun el contexto de noticias mas reciente.
- **API Router**: expone `/cerebro/status`, `/cerebro/decide` y `/cerebro/learn` dentro del FastAPI principal.

## Flujo rapido

1. `run_cycle()` descarga OHLC recientes y actualiza el FeatureStore.
2. Lee los feeds RSS configurados, calcula un `NewsPulse` (sentimiento -1..1, noticia mas reciente y antiguedad).
3. El guard de sesiones revisa si estamos dentro de la ventana de pre-apertura/post-apertura.
4. PolicyEnsemble genera una decision (LONG/SHORT/NO_TRADE) con confianza, riesgo y SL/TP dinamicos.
5. El bot real consume esa decision via `_maybe_apply_cerebro`. Si la accion es `NO_TRADE` la senal se descarta.
6. Al cerrar una operacion se llama a `/cerebro/learn` para alimentar la memoria.

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
  "min_confidence": 0.55,
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
- `session_guards`: lista de ventanas por region. Puedes eliminar o ajustar horarios/tiempos segun la cobertura del bot.
- `risk_multiplier_after_news`: multiplicador que se aplica al `risk_pct` cuando la sesion ya abrio y hay una
  noticia alineada.

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

## Logs e historial

- `logs/cerebro_decisions.jsonl`: cada decision publicada para auditar en el panel.
- `logs/cerebro_experience.jsonl`: dataset usado por el entrenamiento.
- `/cerebro/status` ahora expone `history` (últimas ~60 decisiones) para graficar confianza en el panel.

## Integracion con el panel

`/cerebro/status` devuelve cada decision con un bloque `metadata`. El panel ahora muestra:

- Sentimiento de noticias y ultimo titular (si llega desde los feeds).
- Estado de la Session Guard (badge amarillo/rojo segun `block_trade`).
- Razones completas (`decision.reasons`) para auditar por que se bloqueo una senal.
- Filtros por símbolo/timeframe, botón **Forzar decisión** (POST `/cerebro/decide`) y el gráfico de confianza histórica.

## Ejecucion rapida

```
cd bot
SLSBOT_CONFIG=../config/config.json python -m cerebro.service --once
python -m cerebro.service --loop
```

Tambien puedes dejar que FastAPI importe `cerebro` para que los endpoints se sirvan junto al resto de la API.
