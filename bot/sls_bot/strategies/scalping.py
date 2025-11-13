from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np

from ..ia_utils import latest_slice


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize(value: float, low: float, high: float) -> float:
    if high - low <= 0:
        return 0.0
    return _clamp((value - low) / (high - low), 0.0, 1.0)


@dataclass
class ScalpingDecision:
    payload: Dict[str, Any]
    evidences: Dict[str, Any]
    metadata: Dict[str, Any]


class ScalpingStrategy:
    """High-frequency scalping engine focused on the demo mode."""

    def __init__(self, config: Dict[str, Any]):
        self.update_config(config)

    def update_config(self, config: Dict[str, Any]) -> None:
        self.config = config or {}
        self.primary_tf = str(self.config.get("primary_timeframe", "1m"))
        self.anchor_tf = str(self.config.get("anchor_timeframe", "15m"))
        self.allowed_timeframes = [tf.lower() for tf in self.config.get("timeframes", [])]
        self.lookback = int(self.config.get("lookback", 720))
        self.volume_window = int(self.config.get("volume_window", 120))
        self.volatility_min = float(self.config.get("volatility_bps_min", 25))
        self.volatility_max = float(self.config.get("volatility_bps_max", 220))
        self.conf_threshold = float(self.config.get("confidence_threshold", 0.62))
        self.force_trade_conf = float(self.config.get("force_trade_confidence", 0.3))
        self.min_risk_pct = float(self.config.get("min_risk_pct", 0.25))
        self.atr_stop_mult = float(self.config.get("atr_stop_multiple", 1.15))
        self.atr_tp_mult = float(self.config.get("atr_take_profit_multiple", 2.35))
        self.max_hold_minutes = int(self.config.get("max_hold_minutes", 45))
        self.fee_bps_round_trip = float(self.config.get("fee_bps_round_trip", 12.0))
        self.min_trades_per_day = int(self.config.get("min_trades_per_day", 12))
        self.daily_target_pct = float(self.config.get("daily_target_pct", 0.6))

        self.base_risk_pct = float(self.config.get("risk_pct", 1.2))
        self.base_leverage = int(self.config.get("leverage", 12))
        self.aggressive_symbols = [s.upper() for s in self.config.get("aggressive_symbols", [])]

    # pylint: disable=too-many-locals
    def decide(
        self,
        *,
        symbol: str,
        marco: str,
        riesgo_pct_user: float | None,
        leverage_user: int | None,
    ) -> ScalpingDecision:
        target_tf = self.primary_tf if self._force_timeframe(marco) else marco
        df, last = latest_slice(symbol, target_tf, limit=self.lookback)
        _, anchor_last = latest_slice(symbol, self.anchor_tf, limit=300)

        window = min(len(df) - 1, 8)
        ema_slope = float(df["ema_fast"].iloc[-1] - df["ema_fast"].iloc[-window]) if window > 0 else 0.0
        ema_slope_bps = ema_slope / float(last.close) * 10000.0
        if anchor_last is not None:
            anchor_trend = 1.0 if anchor_last.close > anchor_last.ema_mid else -1.0
            anchor_momentum = np.tanh(float(anchor_last.rsi - 50.0) / 20.0)
        else:
            anchor_trend = 0.0
            anchor_momentum = 0.0

        micro_trend_long = 0.0
        micro_trend_short = 0.0
        if last.close > last.ema_mid and last.ema_mid > last.ema_slow:
            micro_trend_long += 0.35
        if last.close < last.ema_mid and last.ema_mid < last.ema_slow:
            micro_trend_short += 0.35
        if ema_slope_bps > 0:
            micro_trend_long += _normalize(ema_slope_bps, 0.5, 8.0) * 0.2
        else:
            micro_trend_short += _normalize(abs(ema_slope_bps), 0.5, 8.0) * 0.2

        breakout_bonus = 0.1 if last.breakout_up == 1 else 0.0
        breakdown_bonus = 0.1 if last.breakout_dn == 1 else 0.0

        atr_bps = float(last.atr / last.close * 10000.0)
        volatility_score = _normalize(atr_bps, self.volatility_min, self.volatility_max)

        recent_range = float(df["range_pct"].iloc[-20:].mean() or 0.0)
        compression = _normalize(60 - recent_range, 0, 40)

        recent_volume = df["volume"].tail(self.volume_window)
        volume_mean = float(recent_volume.mean() or 1.0)
        if not np.isfinite(volume_mean) or volume_mean <= 0:
            volume_mean = 1.0
        volume_ratio = float(last.volume) / volume_mean
        liquidity_score = _normalize(volume_ratio, 0.8, 2.5)

        anchor_bias = 0.15 * anchor_trend
        anchor_momo = 0.1 * anchor_momentum

        long_score = micro_trend_long + breakout_bonus + volatility_score * 0.2 + liquidity_score * 0.15
        short_score = micro_trend_short + breakdown_bonus + volatility_score * 0.2 + liquidity_score * 0.15
        long_score += max(0.0, anchor_bias) + max(0.0, anchor_momo)
        short_score += max(0.0, -anchor_bias) + max(0.0, -anchor_momo)

        # Compression favors breakout scalps
        long_score += compression * 0.1 if last.close > last.avwap else 0.0
        short_score += compression * 0.1 if last.close < last.avwap else 0.0

        direction = "LONG" if long_score >= short_score else "SHORT"
        confidence = max(long_score, short_score)
        confidence = _clamp(confidence, 0.0, 1.5)
        confidence_norm = confidence / 1.5

        decision = direction if confidence_norm >= self.conf_threshold else "NO_TRADE"
        forced_entry = False
        if decision == "NO_TRADE" and confidence_norm >= self.force_trade_conf:
            decision = direction
            forced_entry = True

        riesgo_pct = float(riesgo_pct_user if riesgo_pct_user is not None else self.base_risk_pct)
        leverage = int(leverage_user if leverage_user is not None else self.base_leverage)
        if symbol.upper() in self.aggressive_symbols:
            riesgo_pct *= 1.15
            leverage = max(leverage, self.base_leverage + 3)

        if volatility_score < 0.3:
            riesgo_pct *= 0.6
        elif volatility_score > 0.8:
            riesgo_pct *= 0.85

        fee_ratio = self.fee_bps_round_trip / 10000.0
        riesgo_pct = max(self.min_risk_pct, riesgo_pct - fee_ratio * leverage)
        if forced_entry:
            riesgo_pct = max(self.min_risk_pct, riesgo_pct * 0.5)

        riesgo_pct = _clamp(riesgo_pct, 0.1, 2.5)
        leverage = max(1, min(leverage, 30))

        stop_loss, take_profit = self._calc_levels(direction, float(last.close), float(last.atr))
        fee_price_offset = float(last.close) * fee_ratio
        if direction == "LONG":
            take_profit += fee_price_offset
        else:
            take_profit -= fee_price_offset

        resumen = (
            f"Scalp {target_tf}: trend={direction} | conf={confidence_norm:.2f} | "
            f"vol_ratio={volatility_score:.2f} | vol_mult={volume_ratio:.2f}"
        )

        webhook = {}
        if decision in {"LONG", "SHORT"}:
            webhook = {
                "signal": f"SCALP_{decision}",
                "symbol": symbol.upper(),
                "tf": target_tf,
                "risk_pct": round(riesgo_pct, 3),
                "leverage": leverage,
                "post_only": False,
                "tp1_close_pct": 40,
                "move_sl_to_be_on_tp1": True,
            }

        payload = {
            "simbolo": symbol.upper(),
            "marco": target_tf,
            "modo": "scalping",
            "decision": decision,
            "confianza_pct": round(confidence_norm * 100, 1),
            "riesgo_pct": round(riesgo_pct, 3),
            "leverage": leverage,
            "resumen": resumen,
            "webhook_body": webhook,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "notas": None if decision != "NO_TRADE" else "Filtro de confianza",
        }
        if forced_entry and decision in {"LONG", "SHORT"}:
            payload["notas"] = "Entrada forzada para acelerar el aprendizaje"

        evid = {
            "scores": {
                "long": round(long_score, 3),
                "short": round(short_score, 3),
                "confidence_norm": round(confidence_norm, 3),
            },
            "volatility_bps": round(atr_bps, 2),
            "volume_ratio": round(volume_ratio, 2),
            "compression": round(compression, 3),
        }

        metadata = {
            "strategy": "scalping_v1",
            "primary_tf": target_tf,
            "anchor_tf": self.anchor_tf,
            "max_hold_minutes": self.max_hold_minutes,
            "volatility_score": round(volatility_score, 3),
            "confidence_threshold": self.conf_threshold,
            "forced_entry": forced_entry,
            "fee_bps_round_trip": self.fee_bps_round_trip,
            "min_trades_per_day": self.min_trades_per_day,
            "daily_target_pct": self.daily_target_pct,
            "min_risk_pct": self.min_risk_pct,
            "force_trade_confidence": self.force_trade_conf,
        }

        return ScalpingDecision(payload=payload, evidences=evid, metadata=metadata)

    def _force_timeframe(self, marco: str) -> bool:
        if not self.allowed_timeframes:
            return True
        return str(marco).lower() not in self.allowed_timeframes

    def _calc_levels(self, side: str, price: float, atr: float) -> Tuple[float, float]:
        atr = atr or price * 0.004
        if side == "LONG":
            stop = max(0.0, price - atr * self.atr_stop_mult)
            take = price + atr * self.atr_tp_mult
        else:
            stop = price + atr * self.atr_stop_mult
            take = max(0.0, price - atr * self.atr_tp_mult)
        return stop, take
