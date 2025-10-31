from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


@dataclass
class SessionReport:
    session_name: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    blocked: int = 0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "session": self.session_name,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
        }


class ReportBuilder:
    """Genera reportes diarios del desempeño del Cerebro."""

    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, SessionReport] = {}

    def register_trade(self, *, session_name: str, pnl: float, reason: str | None = None) -> None:
        session = self._sessions.setdefault(session_name, SessionReport(session_name=session_name))
        session.trades += 1
        if pnl > 0:
            session.wins += 1
        elif pnl < 0:
            session.losses += 1
        if reason:
            session.reasons.append(reason)

    def register_blocked(self, *, session_name: str, reason: str) -> None:
        session = self._sessions.setdefault(session_name, SessionReport(session_name=session_name))
        session.blocked += 1
        session.reasons.append(reason)

    def write_daily_report(self) -> Path:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sessions": [session.to_dict() for session in self._sessions.values()],
        }
        path = self.logs_dir / "cerebro_daily_report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def snapshot(self) -> Dict[str, dict]:
        return {name: session.to_dict() for name, session in self._sessions.items()}
