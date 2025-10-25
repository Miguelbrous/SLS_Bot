from __future__ import annotations

from typing import List

from ...sls_bot import ia_utils
from .base import DataSource


class MarketDataSource(DataSource):
    """Envuelve fetch_ohlc + indicadores para el Cerebro."""

    name = "market"

    def fetch(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 200) -> List[dict]:
        if not symbol or not timeframe:
            raise ValueError("symbol y timeframe son obligatorios para MarketDataSource")
        df = ia_utils.compute_indicators(ia_utils.fetch_ohlc(symbol, timeframe, limit=limit))
        return df.tail(limit).to_dict(orient="records")
