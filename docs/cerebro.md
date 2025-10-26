# Cerebro: Motor IA Autoaprendizaje

Este documento describe la arquitectura propuesta para el “Cerebro” de SLS Bot, un
servicio separado encargado de **observar**, **aprender** y **sugerir** ajustes a la
estrategia en tiempo real.

## Objetivos

1. **Observabilidad continua**: recopilar mercado, indicadores, noticias y resultados
   del bot para crear un contexto histórico.
2. **Aprendizaje iterativo**: entrenar modelos (supervisado + heurístico) que
   estimen la probabilidad de éxito de una operación futura.
3. **Retroalimentación**: exponer decisiones sugeridas, niveles de confianza y
   parámetros recomendados (riesgo, apalancamiento, filtros).
4. **Memoria viva**: almacenar todas las operaciones con su contexto para seguir
   mejorando sin depender de hojas de cálculo manuales.

## Componentes

```
┌─────────────┐        ┌──────────────┐        ┌──────────────┐
│ DataSource  │  --->  │ FeatureStore │  --->  │ PolicyEngine │
└─────────────┘        └──────────────┘        └──────────────┘
      ^                       │                         │
      │                       v                         v
┌─────────────┐        ┌──────────────┐        ┌──────────────┐
│ News/RSS    │        │ Experience   │        │ API / Router │
│ Sentiment   │        │ Memory       │        │ (FastAPI)    │
└─────────────┘        └──────────────┘        └──────────────┘
```

- **DataSources**: conectores a Bybit (velas + indicadores), noticias (RSS),
  métricas internas y, en el futuro, on-chain u otras fuentes.
- **FeatureStore**: cachea series temporales, normaliza y entrega “slices”
  listos para la política.
- **ExperienceMemory**: almacena cada operación real (features + resultado) para
  reentrenar modelos y evaluar estrategias.
- **PolicyEngine**: combina heurísticas, modelos existentes (`ia_signal_engine`)
  y “penalizaciones” basadas en drawdown para generar una recomendación.
- **API Router**: expone `/cerebro/status`, `/cerebro/decide` y `/cerebro/learn`
  para integrarse con el panel o con scripts de despliegue.

## Flujo de entrenamiento / inferencia

1. **Ingesta** (`Cerebro.run_cycle`)
   - Descarga OHLC reciente (`ia_utils.fetch_ohlc`) y calcula indicadores.
   - Consulta noticias en RSS (lista configurable).
   - Actualiza FeatureStore y guarda el “contexto” (últimas velas + sentimiento).

2. **Evaluación**
   - PolicyEngine recibe el contexto y produce:
     - Dirección sugerida (`LONG/SHORT/NO_TRADE`).
     - Confianza (0-1), riesgo sugerido y palanca sugerida.
     - Explicaciones (por qué/qué indicadores activaron la señal).

3. **Feedback**
   - Cuando el bot real cierra una operación se llama a `/cerebro/learn`.
   - La memoria almacena `features + pnl` y actualiza métricas (winrate,
     drawdown, racha).
   - Se programa un “refresh” para reentrenar modelos (por ahora manual).

4. **Consumo por el bot**
   - `ia_router` o `sls_bot.app` pueden consultar `/cerebro/decide` para obtener
     un “score” adicional y filtrarlo con la lógica existente.
   - El panel mostrará el estado del cerebro (últimas decisiones, noticias
     relevantes, confianza media).

## Configuración (`config/config.json`)

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
  "tp_atr_multiple": 2.0
}
```

- `symbols` / `timeframes`: universos que analizará el Cerebro.
- `refresh_seconds`: cada cuánto se ejecuta `run_cycle`.
- `news_feeds`: fuentes RSS confiables.
- `min_confidence`: umbral para destacar señales.
- `max_memory`: cantidad máxima de operaciones guardadas.

## Roadmap

1. **Versión Alfa (este commit)**: estructura del servicio, endpoints básicos,
   ingesta de mercado/noticias, almacenamiento de experiencias y heurística
   inicial combinada con el IA actual.
2. **Versión Beta**
   - Entrenamiento periódico (cron) con `ia_train.py`.
   - Métricas de validación (AUC, Sharpe simulado).
   - Ajuste automático de parámetros del bot (riesgo_pct, filtros).
3. **Versión 1.0**
   - Integración de NLP para clasificar noticias (bullish/bearish).
   - Refuerzo continuo (policy gradient) usando simulaciones / backtests.
   - Evaluación multi-símbolo y gestión de portafolio.

## Integración con el Panel

- `/status` ya expone `risk_state_details`.
- `/cerebro/status` provee información adicional: última iteración, confianza
  media y noticias relevantes.
- Próximo paso: panel mostrará una tarjeta “Cerebro” con esos datos y un botón
  para solicitar una decisión manualmente.

## Cómo ejecutar

```
cd bot
SLSBOT_CONFIG=../config/config.json \
python -m cerebro.service --once      # Ejecuta un ciclo
python -m cerebro.service --loop      # Ciclo continuo (usa refresh_seconds)
```

Los endpoints se montan automáticamente en la API principal (`/cerebro/*`)
cuando `bot/app/main.py` puede importar el módulo.
