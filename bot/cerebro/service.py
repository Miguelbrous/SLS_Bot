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

from .anomaly import AnomalyDetector
from .config import CerebroConfig, load_cerebro_config
from .confidence import ConfidenceContext, DynamicConfidenceGate
from .evaluation import EvaluationTracker
from .filters import MarketSessionGuard, summarize_news_items
from .features import FeatureStore
from .ingestion import DataIngestionManager, IngestionTask
from .memory import Experience, ExperienceMemory
from .pipelines import TrainingConfig, TrainingPipeline, detect_python_bin
from .policy import PolicyDecision, PolicyEnsemble
from .reporting import ReportBuilder
from .simulator import BacktestSimulator
from .versioning import ModelRegistry

log = logging.getLogger(__name__)

try:
    from ..sls_bot.config_loader import load_config as _load_bot_config
except Exception:  # pragma: no cover - fallback when running standalone
    try:
        from sls_bot.config_loader import load_config as _load_bot_config  # type: ignore
    except Exception:
        _load_bot_config = None


def _detect_mode() -> str:
    env_mode = os.getenv("SLS_CEREBRO_MODE") or os.getenv("SLSBOT_MODE")
    if env_mode:
        return env_mode
    if _load_bot_config:
        try:
            cfg = _load_bot_config()
            mode = cfg.get("_active_mode")
            if mode:
                return str(mode)
        except Exception:
            pass
    return "default"


MODE_NAME = _detect_mode()
ROOT_DIR = Path(os.getenv("SLS_CEREBRO_ROOT", Path(__file__).resolve().parents[2]))
LOGS_DIR = Path(os.getenv("SLS_CEREBRO_LOGS", ROOT_DIR / "logs" / MODE_NAME))
MODELS_DIR = Path(os.getenv("SLS_CEREBRO_MODELS", ROOT_DIR / "models" / "cerebro" / MODE_NAME))
DECISIONS_LOG = LOGS_DIR / "cerebro_decisions.jsonl"
EXPERIENCE_LOG = LOGS_DIR / "cerebro_experience.jsonl"
METRICS_DIR = LOGS_DIR / "metrics"
REPORTS_DIR = LOGS_DIR / "reports"


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
        self.ingestion = DataIngestionManager(
            news_feeds=self.config.news_feeds,
            cache_ttl=max(5, self.config.data_cache_ttl),
        )
        self.ingestion.warmup(self.config.symbols, self.config.timeframes)
        self.memory = ExperienceMemory(maxlen=self.config.max_memory)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.policy = PolicyEnsemble(
            min_confidence=self.config.min_confidence,
            sl_atr=self.config.sl_atr_multiple,
            tp_atr=self.config.tp_atr_multiple,
            model_path=MODELS_DIR / "active_model.json",
        )
        self.session_guard = MarketSessionGuard(self.config.session_guards)
        self.anomaly_detector = AnomalyDetector(
            z_threshold=self.config.anomaly_z_threshold,
            min_points=self.config.anomaly_min_points,
        )
        self.confidence_gate = DynamicConfidenceGate(
            base_threshold=self.config.min_confidence,
            max_threshold=self.config.confidence_max,
            min_threshold=self.config.confidence_min,
        )
        self.registry = ModelRegistry(MODELS_DIR)
        self.evaluation = EvaluationTracker(METRICS_DIR)
        self.report_builder = ReportBuilder(REPORTS_DIR)
        self.simulator = BacktestSimulator()
        self.training = TrainingPipeline(self.registry)
        self.python_bin = detect_python_bin()
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
            self.ingestion.schedule(IngestionTask(source="news", limit=20))
            for symbol in self.config.symbols:
                for tf in self.config.timeframes:
                    self.ingestion.schedule(IngestionTask(source="market", symbol=symbol, timeframe=tf, limit=200))
            self.ingestion.run_pending(max_tasks=len(self.config.symbols) * len(self.config.timeframes) + 1)
            news_items = self.ingestion.fetch_now("news", limit=10)
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
                        rows = self.ingestion.fetch_now("market", symbol=symbol, timeframe=tf, limit=200)
                        self.feature_store.update(symbol, tf, rows)
                        slice_window = self.feature_store.latest(symbol, tf, window=120)
                        if not slice_window.data:
                            continue
                        anomaly = self.anomaly_detector.score_series(slice_window.data, field="close")
                        means, variances = self.feature_store.describe(symbol, tf)
                        volatility = abs(variances.get("close", 1.0))
                        dataset_quality = min(len(slice_window.data) / float(self.feature_store.maxlen), 1.0)
                        confidence_threshold = self.confidence_gate.compute(
                            ConfidenceContext(
                                volatility=volatility or 0.0,
                                dataset_quality=dataset_quality,
                                anomaly_score=anomaly.score,
                            )
                        )
                        normalized_row = slice_window.normalized[-1] if slice_window.normalized else None
                        decision = self.policy.decide(
                            symbol=symbol,
                            timeframe=tf,
                            market_row=slice_window.data[-1],
                            news_sentiment=news_sentiment,
                            memory_stats=stats,
                            session_context=session_meta,
                            news_meta=news_meta,
                            anomaly_score=anomaly.score,
                            min_confidence_override=confidence_threshold,
                            normalized_features=normalized_row,
                        )
                        session_name = (session_meta or {}).get("session_name", "General")
                        decision.metadata.update(self.confidence_gate.to_metadata(confidence_threshold))
                        decision.metadata["anomaly"] = {
                            "score": anomaly.score,
                            "flag": anomaly.is_anomalous,
                            "reason": anomaly.reason,
                        }
                        decision.metadata["feature_means"] = {k: v for k, v in means.items() if k in {"close", "atr", "volume"}}
                        decision.metadata["feature_vars"] = {k: v for k, v in variances.items() if k in {"close", "atr", "volume"}}
                        decision.metadata["dataset_quality"] = dataset_quality
                        decision.metadata["volatility_estimate"] = volatility
                        if anomaly.is_anomalous and decision.action != "NO_TRADE":
                            decision.action = "NO_TRADE"
                            decision.reasons.append(anomaly.reason or "Anomalía detectada")
                            decision.metadata["blocked_by"] = "anomaly_detector"
                            self.report_builder.register_blocked(session_name=session_name, reason=anomaly.reason or "anomaly")
                        if session_meta and session_meta.get("block_trade") and decision.action == "NO_TRADE":
                            self.report_builder.register_blocked(session_name=session_name, reason=session_meta.get("reason", "session_guard"))
                        simulation = self.simulator.simulate(
                            ohlc=slice_window.data[-5:],
                            decisions=[decision.action] * min(len(slice_window.data[-5:]), 5),
                        )
                        decision.metadata["simulation"] = {
                            "trades": simulation.trades,
                            "pnl": simulation.pnl,
                            "avg_pnl": simulation.avg_pnl,
                        }
                        self.evaluation.register(symbol=symbol, timeframe=tf, decision=decision)
                        key = f"{symbol.upper()}::{tf}"
                        self._decisions[key] = DecisionSnapshot(
                            decision=decision, generated_at=self._last_run, features=slice_window.data[-1]
                        )
                    except Exception as exc:
                        log.exception("Cerebro run_cycle failed for %s %s: %s", symbol, tf, exc)
                    else:
                        self._record_decision(symbol, tf, decision)
            self.evaluation.save()
            self.report_builder.write_daily_report()

    def register_trade(
        self,
        *,
        symbol: str,
        timeframe: str,
        pnl: float,
        features: Dict[str, float],
        decision: str,
        session_name: str | None = None,
        reason: str | None = None,
    ) -> None:
        with self._lock:
            self.memory.push(Experience(symbol=symbol, timeframe=timeframe, pnl=pnl, features=features, decision=decision))
            self._persist_experience(symbol, timeframe, pnl, features, decision)
            target_session = session_name or "General"
            self.report_builder.register_trade(session_name=target_session, pnl=pnl, reason=reason)
        self.training.online_update(experiences_path=EXPERIENCE_LOG)
        if os.getenv("SLS_CEREBRO_AUTO_TRAIN") == "1":
            stats = self.memory.stats()
            total = stats.get("total", 0)
            interval = max(10, self.config.auto_train_interval)
            if total and total % interval == 0:
                cfg = TrainingConfig(
                    python_bin=self.python_bin,
                    mode=MODE_NAME,
                    dataset_path=EXPERIENCE_LOG,
                    output_dir=MODELS_DIR,
                )
                artifact = self.training.offline_training(cfg)
                if artifact:
                    log.info("Nuevo modelo registrado desde %s", artifact)

    def simulate_sequence(
        self,
        *,
        symbol: str,
        timeframe: str,
        horizon: int = 30,
        news_sentiment: float = 0.0,
    ) -> dict:
        horizon = max(1, min(horizon, 120))
        with self._lock:
            window = self.feature_store.latest(symbol, timeframe, window=horizon)
            if not window.data:
                raise ValueError(f"No hay suficientes datos para {symbol} {timeframe}")
            stats = self.memory.stats()
        decisions: List[PolicyDecision] = []
        actions: List[str] = []
        session_context = None
        for idx, row in enumerate(window.data):
            normalized = window.normalized[idx] if idx < len(window.normalized) else None
            decision = self.policy.decide(
                symbol=symbol,
                timeframe=timeframe,
                market_row=row,
                news_sentiment=news_sentiment,
                memory_stats=stats,
                session_context=session_context,
                news_meta=None,
                anomaly_score=0.0,
                min_confidence_override=None,
                normalized_features=normalized,
            )
            decisions.append(decision)
            actions.append(decision.action)
        simulation = self.simulator.simulate(ohlc=window.data, decisions=actions)
        return {
            "decisions": [asdict(decision) for decision in decisions],
            "simulation": {
                "trades": simulation.trades,
                "pnl": simulation.pnl,
                "avg_pnl": simulation.avg_pnl,
                "details": simulation.details,
            },
        }

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
                "mode": MODE_NAME,
                "evaluation": self.evaluation.snapshot(),
                "report": self.report_builder.snapshot(),
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
            "mode": MODE_NAME,
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
            "mode": MODE_NAME,
        }
        _append_jsonl(EXPERIENCE_LOG, payload)


_singleton: Cerebro | None = None


def get_cerebro() -> Cerebro:
    global _singleton
    if _singleton is None:
        _singleton = Cerebro()
    return _singleton
