from __future__ import annotations

import logging
import threading
import time
import json
import os
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional

from .config import CerebroConfig, load_cerebro_config
from .datasources.market import MarketDataSource
from .datasources.news import RSSNewsDataSource
from .filters import MarketSessionGuard, summarize_news_items
from .features import FeatureStore
from .memory import Experience, ExperienceMemory
from .policy import PolicyDecision, PolicyEnsemble

log = logging.getLogger(__name__)

ROOT_DIR = Path(os.getenv("SLS_CEREBRO_ROOT", Path(__file__).resolve().parents[2]))
LOGS_DIR = Path(os.getenv("SLS_CEREBRO_LOGS", ROOT_DIR / "logs"))
MODELS_DIR = Path(os.getenv("SLS_CEREBRO_MODELS", ROOT_DIR / "models" / "cerebro"))
DECISIONS_LOG = LOGS_DIR / "cerebro_decisions.jsonl"
EXPERIENCE_LOG = LOGS_DIR / "cerebro_experience.jsonl"


def _append_jsonl(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        log.debug("Failed to append jsonl to %s", path, exc_info=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.policy = PolicyEnsemble(
            min_confidence=self.config.min_confidence,
            sl_atr=self.config.sl_atr_multiple,
            tp_atr=self.config.tp_atr_multiple,
            model_path=MODELS_DIR / "active_model.json",
        )
        self.session_guard = MarketSessionGuard(self.config.session_guards)
        self._lock = threading.Lock()
        self._decisions: Dict[str, DecisionSnapshot] = {}
        self._history: Deque[dict] = deque(maxlen=200)
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
            now = datetime.now(timezone.utc)
            news_items = self.news_source.fetch(limit=10)
            news_pulse = summarize_news_items(news_items, now=now, ttl_minutes=self.config.news_ttl_minutes)
            news_sentiment = news_pulse.sentiment
            news_meta = {
                "latest_title": news_pulse.latest_title,
                "latest_url": news_pulse.latest_url,
                "latest_ts": news_pulse.latest_ts.isoformat() if news_pulse.latest_ts else None,
                "is_fresh": news_pulse.is_fresh(now, self.config.news_ttl_minutes),
                "sentiment": news_pulse.sentiment,
            }
            session_guard = self.session_guard.evaluate(now=now, news_pulse=news_pulse)
            session_meta = session_guard.to_metadata() if session_guard else None
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
                            session_context=session_meta,
                            news_meta=news_meta,
                        )
                        key = f"{symbol.upper()}::{tf}"
                        self._decisions[key] = DecisionSnapshot(
                            decision=decision, generated_at=self._last_run, features=rows[-1]
                        )
                    except Exception as exc:
                        log.exception("Cerebro run_cycle failed for %s %s: %s", symbol, tf, exc)
                    else:
                        self._record_decision(symbol, tf, decision)

    def register_trade(self, *, symbol: str, timeframe: str, pnl: float, features: Dict[str, float], decision: str) -> None:
        with self._lock:
            self.memory.push(Experience(symbol=symbol, timeframe=timeframe, pnl=pnl, features=features, decision=decision))
            self._persist_experience(symbol, timeframe, pnl, features, decision)

    def get_status(self) -> dict:
        with self._lock:
            decisions = {
                key: snapshot.decision.__dict__ | {"generated_at": snapshot.generated_at}
                for key, snapshot in self._decisions.items()
            }
            config_payload = self.config.__dict__.copy()
            config_payload["session_guards"] = [asdict(sg) for sg in self.config.session_guards]
            return {
                "config": config_payload,
                "last_run_ts": self._last_run,
                "feature_store": self.feature_store.stats(),
                "decisions": decisions,
                "memory": self.memory.stats(),
                "history": list(self._history),
            }

    def latest_decision(self, symbol: str, timeframe: str) -> PolicyDecision | None:
        key = f"{symbol.upper()}::{timeframe}"
        snap = self._decisions.get(key)
        return snap.decision if snap else None

    def list_decisions(self, limit: int = 50) -> List[dict]:
        limit = max(1, min(limit, 500))
        rows: List[dict] = []
        if DECISIONS_LOG.exists():
            try:
                with DECISIONS_LOG.open("r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()[-limit:]
                for raw in reversed(lines):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rows.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
            except Exception:
                log.debug("Failed to read decisions log", exc_info=True)
        if len(rows) < limit:
            with self._lock:
                fallback = list(self._history)[-limit:]
            for entry in reversed(fallback):
                if any(row.get("ts") == entry.get("ts") for row in rows):
                    continue
                rows.append(entry)
                if len(rows) >= limit:
                    break
        rows.sort(key=lambda item: item.get("ts", ""), reverse=True)
        return rows[:limit]

    # ----- Persistencia auxiliar -----
    def _record_decision(self, symbol: str, timeframe: str, decision: PolicyDecision) -> None:
        payload = {
            "ts": _utc_now_iso(),
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "action": decision.action,
            "confidence": decision.confidence,
            "risk_pct": decision.risk_pct,
            "generated_at": getattr(decision, "generated_at", None),
            "metadata": decision.metadata,
        }
        self._history.append(payload)
        _append_jsonl(DECISIONS_LOG, payload)

    def _persist_experience(self, symbol: str, timeframe: str, pnl: float, features: Dict[str, float], decision: str) -> None:
        payload = {
            "ts": _utc_now_iso(),
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "pnl": pnl,
            "decision": decision,
            "features": features,
        }
        _append_jsonl(EXPERIENCE_LOG, payload)


_singleton: Cerebro | None = None


def get_cerebro() -> Cerebro:
    global _singleton
    if _singleton is None:
        _singleton = Cerebro()
    return _singleton
