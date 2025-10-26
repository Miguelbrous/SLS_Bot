from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import CerebroConfig, load_cerebro_config
from .datasources.market import MarketDataSource
from .datasources.news import RSSNewsDataSource
from .features import FeatureStore
from .memory import Experience, ExperienceMemory
from .policy import PolicyDecision, PolicyEnsemble

log = logging.getLogger(__name__)


@dataclass
class DecisionSnapshot:
    decision: PolicyDecision
    generated_at: float
    features: dict


class Cerebro:
    def __init__(self, config: CerebroConfig | None = None):
        self.config = config or load_cerebro_config()
        self.feature_store = FeatureStore(maxlen=500)
        self.market_source = MarketDataSource()
        self.news_source = RSSNewsDataSource(self.config.news_feeds)
        self.memory = ExperienceMemory(maxlen=self.config.max_memory)
        self.policy = PolicyEnsemble(
            min_confidence=self.config.min_confidence,
            sl_atr=self.config.sl_atr_multiple,
            tp_atr=self.config.tp_atr_multiple,
        )
        self._lock = threading.Lock()
        self._decisions: Dict[str, DecisionSnapshot] = {}
        self._last_run = 0.0
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start_loop(self) -> None:
        if not self.config.enabled or (self._loop_thread and self._loop_thread.is_alive()):
            return
        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self.run_cycle()
                except Exception as exc:
                    log.exception("Cerebro loop error: %s", exc)
                time.sleep(max(10, self.config.refresh_seconds))

        self._loop_thread = threading.Thread(target=_loop, daemon=True, name="cerebro-loop")
        self._loop_thread.start()

    def stop_loop(self) -> None:
        self._stop_event.set()

    def run_cycle(self) -> None:
        if not self.config.enabled:
            return
        with self._lock:
            self._last_run = time.time()
            news_items = self.news_source.fetch(limit=10)
            news_sentiment = 0.0
            if news_items:
                # placeholder: sentimiento neutro, se puede ampliar con NLP
                news_sentiment = 0.0
            stats = self.memory.stats()
            for symbol in self.config.symbols:
                for tf in self.config.timeframes:
                    try:
                        rows = self.market_source.fetch(symbol=symbol, timeframe=tf, limit=200)
                        self.feature_store.update(symbol, tf, rows)
                        if not rows:
                            continue
                        decision = self.policy.decide(
                            symbol=symbol,
                            timeframe=tf,
                            market_row=rows[-1],
                            news_sentiment=news_sentiment,
                            memory_stats=stats,
                        )
                        key = f"{symbol.upper()}::{tf}"
                        self._decisions[key] = DecisionSnapshot(
                            decision=decision, generated_at=self._last_run, features=rows[-1]
                        )
                    except Exception as exc:
                        log.exception("Cerebro run_cycle failed for %s %s: %s", symbol, tf, exc)

    def register_trade(self, *, symbol: str, timeframe: str, pnl: float, features: Dict[str, float], decision: str) -> None:
        with self._lock:
            self.memory.push(Experience(symbol=symbol, timeframe=timeframe, pnl=pnl, features=features, decision=decision))

    def get_status(self) -> dict:
        with self._lock:
            decisions = {
                key: snapshot.decision.__dict__ | {"generated_at": snapshot.generated_at}
                for key, snapshot in self._decisions.items()
            }
            return {
                "config": self.config.__dict__,
                "last_run_ts": self._last_run,
                "feature_store": self.feature_store.stats(),
                "decisions": decisions,
                "memory": self.memory.stats(),
            }

    def latest_decision(self, symbol: str, timeframe: str) -> PolicyDecision | None:
        key = f"{symbol.upper()}::{timeframe}"
        snap = self._decisions.get(key)
        return snap.decision if snap else None


_singleton: Cerebro | None = None


def get_cerebro() -> Cerebro:
    global _singleton
    if _singleton is None:
        _singleton = Cerebro()
    return _singleton
