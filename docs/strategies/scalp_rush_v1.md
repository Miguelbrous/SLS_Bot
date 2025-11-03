# Estrategia Scalp Rush v1

- **Objetivo:** abrir operaciones cada ~30-45 segundos en testnet para generar datos rápidos.
- **Timeframe:** 1 minuto.
- **Indicadores:** EMA 9/21, RSI 14, ATR 14 y rango intrabarra.
- **Condiciones:**
  - LONG si EMA9 > EMA21 y RSI < 70 (o rango alto favorece el lado alcista).
  - SHORT si EMA9 < EMA21 y RSI > 30.
  - Si no hay señal clara pero el rango supera 8 bps, se opera siguiendo la pendiente de las EMAs.
- **Gestión:** riesgo fijo 0.45 %, leverage dinámico entre 8 y 25, SL/TP basados en ATR (0.9× y 1.4× respectivamente).
- **Activación:** `STRATEGY_ID=scalp_rush_v1 STRATEGY_INTERVAL=30 run SLS_Bot`.
- **Uso:** orientada a testnet para prueba y error continuo mientras la Arena refina 5 000 estrategias simuladas.
