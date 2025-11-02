from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ..sls_bot import ia_utils
from .base import Strategy, StrategyContext


@dataclass
class Thresholds:
    ema_diff_bps: float = 6.0
    rsi_upper: float = 68.0
    rsi_lower: float = 32.0


class MicroScalpStrategy(Strategy):
    """Estrategia ligera pensada para cuentas pequeñas (≈5 €)."""

    id = "micro_scalp_v1"
    symbol = "BTCUSDT"
    timeframe = "5m"

    def __init__(self, thresholds: Thresholds | None = None):
        self.thresholds = thresholds or Thresholds()

    def build_signal(self, context: StrategyContext) -> Optional[Dict[str, object]]:
        df, last = ia_utils.latest_slice(self.symbol, self.timeframe, limit=420)
        ema_fast = float(last.get("ema_fast", 0.0))
        ema_mid = float(last.get("ema_mid", 0.0))
        ema_slow = float(last.get("ema_slow", 0.0))
        price = float(last.get("close", 0.0))
        rsi = float(last.get("rsi", 50.0))
        atr = float(last.get("atr", price * 0.005))
        ema_diff_bps = float(last.get("ema_diff_bps", 0.0))

        direction: Optional[str] = None
        if abs(ema_diff_bps) < self.thresholds.ema_diff_bps:
            return None
        if ema_fast > ema_mid > ema_slow and rsi < self.thresholds.rsi_upper:
            direction = "LONG"
        elif ema_fast < ema_mid < ema_slow and rsi > self.thresholds.rsi_lower:
            direction = "SHORT"

        if direction is None or price <= 0 or atr <= 0:
            return None

        risk_pct = max(0.35, min(0.8, context.balance * 0.12))
        leverage = max(5, min(context.leverage, 25))
        sl_distance = atr * 1.35
        tp_distance = atr * 2.1
        if direction == "LONG":
            stop_loss = max(0.0, price - sl_distance)
            take_profit = price + tp_distance
        else:
            stop_loss = price + sl_distance
            take_profit = max(0.0, price - tp_distance)

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
            "tp1_close_pct": 40,
            "move_sl_to_be_on_tp1": True,
            "max_margin_pct": 0.35,
            "max_risk_pct": 1.0,
            "min_stop_distance_pct": 0.002,
            "confirmations": {
                "ema_trend_1h": "bull" if direction == "LONG" else "bear",
                "rsi": rsi,
                "atr": atr,
            },
        }
