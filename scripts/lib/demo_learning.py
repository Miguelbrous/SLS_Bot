from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, MutableMapping, Optional, Tuple
from collections import defaultdict, deque


def _parse_iso(ts_raw: str | None) -> Optional[datetime]:
    if not ts_raw:
        return None
    try:
        if ts_raw.endswith("Z"):
            ts_raw = ts_raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_raw)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


@dataclass
class DemoDecision:
    strategy_id: str
    symbol: str
    tf: str | None
    side: str | None
    risk_pct: float
    ts: datetime
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CloseEntry:
    symbol: str
    tf: str | None
    pnl: float
    before: Optional[float]
    after: Optional[float]
    ts: datetime
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeRecord:
    strategy_id: str
    symbol: str
    tf: str | None
    pnl: float
    before: float
    after: float
    entry_ts: datetime
    exit_ts: datetime
    hold_minutes: float
    risk_pct: float
    side: str | None


@dataclass
class StrategyMetrics:
    strategy_id: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    pnl_sum_sq: float = 0.0
    avg_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    avg_hold_minutes: float = 0.0
    avg_risk_pct: float = 0.0
    latest_trade_ts: Optional[str] = None
    equity_start: Optional[float] = None
    equity_end: Optional[float] = None
    equity_peak: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class ActionPlan:
    strategy_id: str
    action: str
    risk_multiplier: float
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "risk_multiplier": self.risk_multiplier, "notes": self.notes}


@dataclass
class EvaluatorThresholds:
    min_trades: int = 15
    min_win_rate: float = 45.0
    min_sharpe: float = 0.2
    max_drawdown_pct: float = 8.0
    boost_win_rate: float = 65.0
    boost_sharpe: float = 0.7
    min_risk_multiplier: float = 0.25
    max_risk_multiplier: float = 1.6
    risk_step: float = 0.2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_demo_history(path: Path, *, since: Optional[datetime] = None) -> List[DemoDecision]:
    decisions: List[DemoDecision] = []
    if not path.exists():
        return decisions
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            signal = payload.get("payload") or {}
            strategy_id = signal.get("strategy_id")
            if not strategy_id:
                continue
            ts = (
                _parse_iso(signal.get("timestamp"))
                or _parse_iso(payload.get("ts"))
                or datetime.now(timezone.utc)
            )
            if since and ts < since:
                continue
            decisions.append(
                DemoDecision(
                    strategy_id=str(strategy_id),
                    symbol=str(signal.get("symbol") or "").upper(),
                    tf=signal.get("tf"),
                    side=signal.get("side"),
                    risk_pct=_safe_float(signal.get("risk_pct"), 1.0),
                    ts=ts,
                    payload=signal,
                )
            )
    decisions.sort(key=lambda item: item.ts)
    return decisions


def load_pnl_closes(path: Path, *, since: Optional[datetime] = None) -> List[CloseEntry]:
    closes: List[CloseEntry] = []
    if not path.exists():
        return closes
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "close":
                continue
            ts = _parse_iso(payload.get("ts"))
            if not ts:
                continue
            if since and ts < since:
                continue
            closes.append(
                CloseEntry(
                    symbol=str(payload.get("symbol") or "").upper(),
                    tf=payload.get("tf"),
                    pnl=_safe_float(payload.get("pnl")),
                    before=_safe_float(payload.get("before")) if payload.get("before") is not None else None,
                    after=_safe_float(payload.get("after")) if payload.get("after") is not None else None,
                    ts=ts,
                    raw=payload,
                )
            )
    closes.sort(key=lambda item: item.ts)
    return closes


def _pop_candidate(queue: Deque[int], used: MutableMapping[int, bool]) -> Optional[int]:
    while queue:
        idx = queue.popleft()
        if not used.get(idx):
            used[idx] = True
            return idx
    return None


def match_trades(
    decisions: List[DemoDecision],
    closes: List[CloseEntry],
) -> Tuple[List[TradeRecord], Dict[str, Any]]:
    if not decisions or not closes:
        return [], {"unmatched_closes": len(closes), "open_decisions": len(decisions)}

    decisions_map: Dict[int, DemoDecision] = {idx: dec for idx, dec in enumerate(decisions)}
    queues_pair: Dict[Tuple[str, str], Deque[int]] = defaultdict(deque)
    queues_symbol: Dict[str, Deque[int]] = defaultdict(deque)
    global_queue: Deque[int] = deque()
    used: Dict[int, bool] = {}

    for idx, dec in decisions_map.items():
        key = (dec.symbol, (dec.tf or "").lower())
        queues_pair[key].append(idx)
        queues_symbol[dec.symbol].append(idx)
        global_queue.append(idx)

    trades: List[TradeRecord] = []
    unmatched_closes = 0
    for close in closes:
        key = (close.symbol, (close.tf or "").lower())
        dec_idx = _pop_candidate(queues_pair[key], used)
        if dec_idx is None:
            dec_idx = _pop_candidate(queues_symbol[close.symbol], used)
        if dec_idx is None:
            dec_idx = _pop_candidate(global_queue, used)
        if dec_idx is None:
            unmatched_closes += 1
            continue
        dec = decisions_map[dec_idx]
        duration = max((close.ts - dec.ts).total_seconds() / 60.0, 0.0)
        before_value = close.before if close.before is not None else _safe_float(dec.payload.get("before"))
        after_value = close.after if close.after is not None else before_value + close.pnl
        trades.append(
            TradeRecord(
                strategy_id=dec.strategy_id,
                symbol=close.symbol,
                tf=close.tf or dec.tf,
                pnl=close.pnl,
                before=before_value,
                after=after_value,
                entry_ts=dec.ts,
                exit_ts=close.ts,
                hold_minutes=duration,
                risk_pct=dec.risk_pct,
                side=dec.side,
            )
        )

    open_decisions = sum(1 for idx in decisions_map.keys() if not used.get(idx))
    summary = {"unmatched_closes": unmatched_closes, "open_decisions": open_decisions}
    return trades, summary


def compute_metrics(trades: Iterable[TradeRecord]) -> Dict[str, StrategyMetrics]:
    grouped: Dict[str, List[TradeRecord]] = defaultdict(list)
    for trade in trades:
        grouped[trade.strategy_id].append(trade)

    metrics: Dict[str, StrategyMetrics] = {}
    for strategy_id, rows in grouped.items():
        rows.sort(key=lambda item: item.exit_ts)
        meta = StrategyMetrics(strategy_id=strategy_id)
        pnl_values: List[float] = []
        returns: List[float] = []
        hold_minutes: List[float] = []
        risk_pcts: List[float] = []
        equity_curve: List[float] = []

        equity_start: Optional[float] = None
        peak: Optional[float] = None
        last_equity: Optional[float] = None

        for trade in rows:
            meta.trades += 1
            pnl_values.append(trade.pnl)
            if trade.pnl > 0:
                meta.wins += 1
            elif trade.pnl < 0:
                meta.losses += 1
            if trade.before and trade.before > 0:
                returns.append(trade.pnl / trade.before)
                if equity_start is None:
                    equity_start = trade.before
            else:
                equity_start = equity_start or trade.after - trade.pnl
                returns.append(0.0)
            hold_minutes.append(trade.hold_minutes)
            risk_pcts.append(trade.risk_pct)
            last_equity = trade.after
            equity_curve.append(trade.after)
            peak = max(peak or trade.after, trade.after)

        meta.total_pnl = sum(pnl_values)
        meta.pnl_sum_sq = sum(p * p for p in pnl_values)
        meta.avg_pnl = meta.total_pnl / meta.trades if meta.trades else 0.0
        meta.win_rate = (meta.wins / meta.trades * 100.0) if meta.trades else 0.0
        if len(returns) >= 2 and statistics.pstdev(returns) > 0:
            meta.sharpe_ratio = statistics.fmean(returns) / statistics.pstdev(returns)
        elif returns:
            meta.sharpe_ratio = statistics.fmean(returns)
        meta.avg_hold_minutes = statistics.fmean(hold_minutes) if hold_minutes else 0.0
        meta.avg_risk_pct = statistics.fmean(risk_pcts) if risk_pcts else 0.0
        meta.latest_trade_ts = rows[-1].exit_ts.isoformat().replace("+00:00", "Z")
        meta.equity_start = equity_start
        meta.equity_end = last_equity
        meta.equity_peak = peak
        meta.max_drawdown_pct = _compute_max_drawdown(equity_curve, start=equity_start)
        meta.current_drawdown_pct = _compute_current_drawdown(equity_curve)
        metrics[strategy_id] = meta
    return metrics


def _compute_max_drawdown(equity_curve: List[float], start: Optional[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = start if (start and start > 0) else equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak <= 0:
            continue
        dd = (peak - value) / peak * 100.0
        max_dd = max(max_dd, dd)
    return round(max_dd, 4)


def _compute_current_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = max(equity_curve)
    tail = equity_curve[-1]
    if peak <= 0:
        return 0.0
    return round((peak - tail) / peak * 100.0, 4)


def plan_actions(
    metrics: Dict[str, StrategyMetrics],
    thresholds: EvaluatorThresholds,
) -> Dict[str, ActionPlan]:
    plans: Dict[str, ActionPlan] = {}
    for strategy_id, meta in metrics.items():
        notes: List[str] = []
        action = "steady"
        multiplier = 1.0
        if meta.trades < thresholds.min_trades:
            action = "insufficient_data"
            multiplier = max(thresholds.min_risk_multiplier, 0.5)
            notes.append(f"solo {meta.trades} trades (<{thresholds.min_trades})")
        else:
            if meta.max_drawdown_pct >= thresholds.max_drawdown_pct:
                action = "disable"
                multiplier = 0.0
                notes.append(f"drawdown {meta.max_drawdown_pct:.2f}% >= {thresholds.max_drawdown_pct}%")
            elif meta.win_rate < thresholds.min_win_rate or meta.sharpe_ratio < thresholds.min_sharpe:
                action = "reduce_risk"
                multiplier = max(thresholds.min_risk_multiplier, 1.0 - thresholds.risk_step)
                if meta.win_rate < thresholds.min_win_rate:
                    notes.append(f"win_rate {meta.win_rate:.2f}% < {thresholds.min_win_rate}%")
                if meta.sharpe_ratio < thresholds.min_sharpe:
                    notes.append(f"sharpe {meta.sharpe_ratio:.2f} < {thresholds.min_sharpe}")
            elif (
                meta.win_rate >= thresholds.boost_win_rate
                and meta.sharpe_ratio >= thresholds.boost_sharpe
                and meta.current_drawdown_pct < thresholds.max_drawdown_pct / 2
            ):
                action = "boost"
                multiplier = min(thresholds.max_risk_multiplier, 1.0 + thresholds.risk_step)
                notes.append("kpi superados; se recomienda subir riesgo")
        plans[strategy_id] = ActionPlan(strategy_id=strategy_id, action=action, risk_multiplier=round(multiplier, 4), notes=notes)
    return plans


def summarize(trades: List[TradeRecord], metrics: Dict[str, StrategyMetrics], summary_meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trades_processed": len(trades),
        "strategies": len(metrics),
        "unmatched_closes": summary_meta.get("unmatched_closes", 0),
        "open_decisions": summary_meta.get("open_decisions", 0),
    }


def filter_by_lookback(
    decisions: List[DemoDecision],
    closes: List[CloseEntry],
    lookback_hours: Optional[float],
) -> Tuple[List[DemoDecision], List[CloseEntry]]:
    if not lookback_hours or lookback_hours <= 0:
        return decisions, closes
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=lookback_hours)
    filtered_closes = [c for c in closes if c.ts >= since]
    if not filtered_closes:
        return [], []
    earliest = min(c.ts for c in filtered_closes) - timedelta(hours=6)
    filtered_decisions = [d for d in decisions if d.ts >= earliest]
    return filtered_decisions, filtered_closes


def ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_state(
    path: Path,
    *,
    metrics: Dict[str, StrategyMetrics],
    plans: Dict[str, ActionPlan],
    thresholds: EvaluatorThresholds,
    meta: Dict[str, Any],
) -> None:
    ensure_directory(path)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "thresholds": thresholds.to_dict(),
        "summary": meta,
        "strategies": {},
    }
    for strategy_id, metric in metrics.items():
        plan = plans.get(strategy_id)
        payload["strategies"][strategy_id] = {
            "metrics": metric.to_dict(),
            "plan": plan.to_dict() if plan else None,
        }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_ledger(path: Path, *, strategy_id: str, metrics: StrategyMetrics, plan: ActionPlan) -> None:
    ensure_directory(path)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "strategy_id": strategy_id,
        "metrics": metrics.to_dict(),
        "plan": plan.to_dict(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def update_arena_registry(metrics: Dict[str, StrategyMetrics]) -> Dict[str, Any]:
    try:
        from bot.arena.registry import ArenaRegistry
        from bot.arena.models import StrategyStats
    except Exception:
        return {"updated": 0, "missing": list(metrics.keys())}

    registry = ArenaRegistry()
    updated = 0
    missing: List[str] = []
    for strategy_id, metric in metrics.items():
        profile = registry.get(strategy_id)
        if not profile:
            missing.append(strategy_id)
            continue
        existing = profile.stats
        goal = existing.goal if existing else 0.0
        stats = existing or StrategyStats(balance=metric.equity_end or 0.0, goal=goal)
        stats.balance = metric.equity_end or stats.balance
        stats.trades = metric.trades
        stats.wins = metric.wins
        stats.losses = metric.losses
        stats.sharpe_ratio = metric.sharpe_ratio
        stats.drawdown_pct = metric.current_drawdown_pct
        stats.max_drawdown_pct = metric.max_drawdown_pct
        stats.pnl_sum = metric.total_pnl
        stats.pnl_sum_sq = metric.pnl_sum_sq
        stats.last_updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        profile.stats = stats
        registry.upsert(profile)
        updated += 1
    if updated:
        registry.save()
    return {"updated": updated, "missing": missing}
