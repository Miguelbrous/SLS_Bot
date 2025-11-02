# Estrategia Micro Scalp v1

Diseñada para cuentas pequeñas (≈5 €) y operar en Bybit Testnet las 24 h.

## Enfoque
- Timeframe: 5m, símbolo principal BTCUSDT perps.
- Indicadores: EMA 20/50/200, RSI 14, ATR 14 (calculados vía `ia_utils`).
- Condiciones:
  - **LONG**: EMA20 > EMA50 > EMA200 y RSI < 68.
  - **SHORT**: EMA20 < EMA50 < EMA200 y RSI > 32.
  - Se ignoran escenarios con diferencia EMA < 6 bps (mercado lateral).
- Gestión de riesgo: riesgo base 0.35‑0.8 %, leverage dinámico (≥5 y ≤25), stop/take automáticos 1.35×ATR / 2.1×ATR.
- Guardias: `max_margin_pct=0.35`, `max_risk_pct=1.0`, `min_stop_distance_pct=0.002`.

## Ejecución
1. Activar backend (`uvicorn sls_bot.app:app`) y Cerebro (opcional).
2. Ejecutar runner:
   ```bash
   SLSBOT_MODE=test \
   WEBHOOK_SHARED_SECRET=... \
   python -m bot.strategies.runner micro_scalp_v1 --server http://127.0.0.1:8080 --verbose
   ```
3. El runner consulta `/diag` para estimar balance testnet, genera la señal y la firma.
4. El webhook aplica los guardias de capital, fija leverage y abre la orden con TP/SL + autopiloto BE.

## Métricas sugeridas
- Ratio win/loss por sesión (logs `bridge.log`, Excel, `cerebro_experience.jsonl`).
- Drawdown máximo y frecuencia de uso del guardia `low_capital`.
- Seguimiento macro (macro score en metadata) para estudiar ajustes futuros.
