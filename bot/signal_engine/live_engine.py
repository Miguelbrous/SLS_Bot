from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

try:
    from bot.arena.models import StrategyStats
except ImportError:
    StrategyStats = None  # type: ignore

from pybit.unified_trading import HTTP

from bot.config_loader import load_config


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _is_testnet(base_url: str | None) -> bool:
    if not base_url:
        return False
    return "testnet" in base_url.lower()


def _mean(values: Iterable[float], default: float = 0.0) -> float:
    values = list(values)
    if not values:
        return default
    return statistics.fmean(values)


@dataclass
class MarketSnapshot:
    price: float
    atr: float
    bias: float
    ma_fast: float
    ma_slow: float


class LiveSignalEngine:
    """Motor de senales micro basado en datos vivos de Bybit."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, timeframe: str = "15", limit: int = 200):
        cfg = config or load_config()
        self.bybit_cfg = cfg.get("bybit", {}) if isinstance(cfg, dict) else {}
        base_url = self.bybit_cfg.get("base_url") or "https://api.bybit.com"
        api_key = self.bybit_cfg.get("api_key") or None
        api_secret = self.bybit_cfg.get("api_secret") or None
        testnet = _is_testnet(base_url)
        self.category = self.bybit_cfg.get("category", "linear")
        self.symbols = self.bybit_cfg.get("symbols", ["BTCUSDT"])
        self.timeframe = timeframe  # valores Bybit: 1,3,5,15...
        self.limit = min(max(limit, 10), 200)
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)

    # ------------------------------------------------------------------ helpers
    def _get_klines(self, symbol: str) -> list[dict[str, Any]]:
        try:
            resp = self.session.get_kline(category=self.category, symbol=symbol, interval=str(self.timeframe), limit=self.limit)
            return resp.get("result", {}).get("list", [])
        except Exception:
            return []

    def _get_orderbook(self, symbol: str) -> dict[str, Any]:
        try:
            resp = self.session.get_orderbook(category=self.category, symbol=symbol, limit=50)
            return resp.get("result", {})
        except Exception:
            return {}

    def _calc_atr(self, klines: list[dict[str, Any]]) -> float:
        if len(klines) < 2:
            return 0.0
        tr_values = []
        prev_close = _parse_float(klines[0]["close"])
        for candle in klines[1:]:
            high = _parse_float(candle["high"])
            low = _parse_float(candle["low"])
            tr = max(high - low, abs(high - prev_close), abs(prev_close - low))
            tr_values.append(tr)
            prev_close = _parse_float(candle["close"])
        return round(_mean(tr_values, 0.0), 4)

    def _orderbook_bias(self, orderbook: dict[str, Any]) -> float:
        bids = orderbook.get("b", [])
        asks = orderbook.get("a", [])
        bid_vol = sum(_parse_float(item[1]) for item in bids[:20])
        ask_vol = sum(_parse_float(item[1]) for item in asks[:20])
        denom = bid_vol + ask_vol
        if denom <= 0:
            return 0.0
        return round((bid_vol - ask_vol) / denom, 4)

    def _moving_averages(self, klines: list[dict[str, Any]]) -> tuple[float, float, float]:
        closes = [_parse_float(c["close"]) for c in klines]
        price = closes[-1] if closes else 0.0
        ma_fast = _mean(closes[-20:], price)
        ma_slow = _mean(closes[-60:], price)
        return price, round(ma_fast, 4), round(ma_slow, 4)

    def snapshot(self, symbol: str) -> Optional[MarketSnapshot]:
        klines = self._get_klines(symbol)
        if not klines:
            return None
        orderbook = self._get_orderbook(symbol)
        price, ma_fast, ma_slow = self._moving_averages(klines)
        atr = self._calc_atr(klines)
        bias = self._orderbook_bias(orderbook)
        return MarketSnapshot(price=price, atr=atr, bias=bias, ma_fast=ma_fast, ma_slow=ma_slow)

    # ------------------------------------------------------------------ decisions
    def _decide_side(self, snap: MarketSnapshot) -> Optional[str]:
        trend = snap.ma_fast - snap.ma_slow
        if abs(trend) < snap.price * 0.0005 and abs(snap.bias) < 0.05:
            return None
        if trend >= 0 and snap.bias >= -0.1:
            return "LONG"
        if trend <= 0 and snap.bias <= 0.1:
            return "SHORT"
        return None

    def build_payload(self, symbol: str, timeframe: str, stats: Optional[StrategyStats] = None) -> Optional[Dict[str, Any]]:  # type: ignore[name-defined]
        snap = self.snapshot(symbol)
        if not snap or snap.price <= 0:
            return None
        side = self._decide_side(snap)
        if not side:
            return None
        atr = snap.atr or snap.price * 0.003
        risk_score = (snap.ma_fast - snap.ma_slow) / snap.price
        confidence = max(min(abs(risk_score) * 20 + abs(snap.bias) * 5, 0.99), 0.05)
        if stats:
            confidence = max(confidence, min(stats.sharpe_ratio, 1.0))
        price = snap.price
        sl_mult = 1.5 if side == "LONG" else -1.5
        tp_mult = 2.5 if side == "LONG" else -2.5
        payload = {
            "symbol": symbol,
            "tf": timeframe,
            "side": side,
            "price": round(price, 3),
            "stop_loss": round(price - atr * sl_mult, 3) if side == "LONG" else round(price - atr * sl_mult, 3),
            "take_profit": round(price + atr * tp_mult, 3),
            "risk_score": round(confidence, 3),
            "atr": round(atr, 4)
        }
        return payload

    def generate(self, symbol: str, timeframe: str, stats: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        return self.build_payload(symbol, timeframe, stats)



