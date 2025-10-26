from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from ..sls_bot import ia_signal_engine


@dataclass
class PolicyDecision:
    symbol: str
    timeframe: str
    action: str
    confidence: float
    risk_pct: float
    leverage: int
    summary: str
    evidences: Dict[str, float]
    price: float
    stop_loss: float
    take_profit: float
    metadata: Dict[str, float]


class PolicyEnsemble:
    """Combina heurísticas, noticias y el motor ML existente."""

    def __init__(self, min_confidence: float, sl_atr: float, tp_atr: float):
        self.min_confidence = min_confidence
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr

    def decide(
        self,
        *,
        symbol: str,
        timeframe: str,
        market_row: dict,
        news_sentiment: float | None = None,
    ) -> PolicyDecision:
        payload, evid_rules, meta = ia_signal_engine.decide(symbol=symbol, marco=timeframe)
        decision = payload["decision"]
        confidence = payload["confianza_pct"] / 100.0
        if news_sentiment is not None:
            # Ajuste sencillo: si la noticia es negativa, penalizamos longs; si es positiva, penalizamos shorts.
            if decision == "LONG":
                confidence = max(0.0, confidence + news_sentiment * 0.05)
            elif decision == "SHORT":
                confidence = max(0.0, confidence - news_sentiment * 0.05)
        if confidence < self.min_confidence:
            decision = "NO_TRADE"
        price = float(market_row.get("close") or 0.0)
        atr = float(market_row.get("atr") or price * 0.005)
        if atr <= 0:
            atr = max(price * 0.005, 0.1)
        if decision == "LONG":
            stop_loss = max(0.0, price - atr * self.sl_atr)
            take_profit = price + atr * self.tp_atr
        else:
            stop_loss = price + atr * self.sl_atr
            take_profit = max(0.0, price - atr * self.tp_atr)

        return PolicyDecision(
            symbol=symbol.upper(),
            timeframe=timeframe,
            action=decision,
            confidence=confidence,
            risk_pct=payload["riesgo_pct"],
            leverage=payload["leverage"],
            summary=payload["resumen"],
            evidences={"rules_long": evid_rules["rules"]["long"], "rules_short": evid_rules["rules"]["short"]},
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={"news_sentiment": news_sentiment or 0.0},
        )
