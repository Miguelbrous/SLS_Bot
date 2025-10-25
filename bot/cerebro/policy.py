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


class PolicyEnsemble:
    """Combina heurísticas, noticias y el motor ML existente."""

    def __init__(self, min_confidence: float):
        self.min_confidence = min_confidence

    def decide(self, *, symbol: str, timeframe: str, news_sentiment: float | None = None) -> PolicyDecision:
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
        return PolicyDecision(
            symbol=symbol.upper(),
            timeframe=timeframe,
            action=decision,
            confidence=confidence,
            risk_pct=payload["riesgo_pct"],
            leverage=payload["leverage"],
            summary=payload["resumen"],
            evidences={"rules_long": evid_rules["rules"]["long"], "rules_short": evid_rules["rules"]["short"]},
        )
