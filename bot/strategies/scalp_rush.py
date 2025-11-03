from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

from ..sls_bot import ia_utils
from .base import Strategy, StrategyContext


@dataclass
class ScalpRushConfig:
    max_interval: int = 45  # segundos entre órdenes
    atr_sl_mult: float = 0.9
    atr_tp_mult: float = 1.4
    min_range_bps: float = 8.0


class ScalpRushStrategy(Strategy):
    """Scalper hiperactivo para testnet: abre trades con micro tendencias de 1m."""

    id = "scalp_rush_v1"
    symbol = "BTCUSDT"
    timeframe = "1m"

    def __init__(self, config: ScalpRushConfig | None = None):
        self.config = config or ScalpRushConfig()
        self._last_trade_ts = 0.0

    def build_signal(self, context: StrategyContext) -> Optional[Dict[str, object]]:
        now = time.time()
        if now - self._last_trade_ts < self.config.max_interval:
            return None

        df, last = ia_utils.latest_slice(self.symbol, self.timeframe, limit=360)
        price = float(last.get("close", 0.0))
        if price <= 0:
            return None

        ema9 = df["close"].ewm(span=9, adjust=False).mean().iloc[-1]
        ema21 = df["close"].ewm(span=21, adjust=False).mean().iloc[-1]
        rsi = float(last.get("rsi", 50.0))
        atr = float(last.get("atr", price * 0.003) or price * 0.003)
        range_bps = float(last.get("range_pct", 0.0))

        direction: Optional[str] = None
        if ema9 > ema21 and rsi < 70:
            direction = "LONG"
        elif ema9 < ema21 and rsi > 30:
            direction = "SHORT"
        elif range_bps >= self.config.min_range_bps:
            direction = "LONG" if ema9 >= ema21 else "SHORT"

        if direction is None:
            return None

        self._last_trade_ts = now
        risk_pct = 0.45
        leverage = max(8, min(25, context.leverage))
        sl_mult = self.config.atr_sl_mult
        tp_mult = self.config.atr_tp_mult
        if direction == "LONG":
            stop_loss = max(0.0, price - atr * sl_mult)
            take_profit = price + atr * tp_mult
        else:
            stop_loss = price + atr * sl_mult
            take_profit = max(0.0, price - atr * tp_mult)

        return {
            "signal": f"SLS_{direction}_ENTRY",
            "symbol": self.symbol,
            "tf": self.timeframe,
            "price": price,
            "risk_pct": round(risk_pct, 2),
            "leverage": leverage,
            "strategy_id": self.id,
            "order_type": "MARKET",
            "post_only": False,
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "tp1_close_pct": 30,
            "move_sl_to_be_on_tp1": True,
            "max_margin_pct": 0.45,
            "max_risk_pct": 1.2,
            "min_stop_distance_pct": 0.001,
            "confirmations": {
                "ema9": float(ema9),
                "ema21": float(ema21),
                "rsi": rsi,
                "range_bps": range_bps,
            },
        }
