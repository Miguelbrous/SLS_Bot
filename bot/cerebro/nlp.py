from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    SentimentIntensityAnalyzer = None  # type: ignore


@dataclass
class SentimentResult:
    compound: float
    positive: float
    negative: float
    neutral: float


class HeadlineSentiment:
    """Envuelve un analizador ligero (VADER) para puntuar titulares."""

    def __init__(self) -> None:
        if SentimentIntensityAnalyzer is None:  # pragma: no cover - depende del entorno
            self._analyzer = None
        else:
            self._analyzer = SentimentIntensityAnalyzer()

    def score(self, text: str | None) -> Optional[SentimentResult]:
        if not text or not text.strip() or not self._analyzer:
            return None
        try:
            scores = self._analyzer.polarity_scores(text)
            return SentimentResult(
                compound=float(scores.get("compound") or 0.0),
                positive=float(scores.get("pos") or 0.0),
                negative=float(scores.get("neg") or 0.0),
                neutral=float(scores.get("neu") or 0.0),
            )
        except Exception:
            log.debug("Sentiment scoring failed", exc_info=True)
            return None


_SENTIMENT_SINGLETON: Optional[HeadlineSentiment] = None


def get_sentiment_analyzer() -> Optional[HeadlineSentiment]:
    global _SENTIMENT_SINGLETON
    if _SENTIMENT_SINGLETON is None:
        _SENTIMENT_SINGLETON = HeadlineSentiment()
    return _SENTIMENT_SINGLETON
