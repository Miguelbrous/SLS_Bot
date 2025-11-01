from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class AlertRule:
    name: str
    pattern: re.Pattern[str]
    severity: str
    hint: str


RULES: List[AlertRule] = [
    AlertRule(
        name="order_error",
        pattern=re.compile(r"\border_error\b", re.IGNORECASE),
        severity="critical",
        hint="Revisar bridge.log y Bybit; la orden fue rechazada.",
    ),
    AlertRule(
        name="blocked",
        pattern=re.compile(r"\bstatus=blocked\b|\bblocked_reason\b", re.IGNORECASE),
        severity="warning",
        hint="El bot está en cooldown o bloqueado por reglas de riesgo.",
    ),
    AlertRule(
        name="pnl_sync_error",
        pattern=re.compile(r"\bpnl_sync_error\b", re.IGNORECASE),
        severity="warning",
        hint="La sincronización de PnL con Bybit falló.",
    ),
    AlertRule(
        name="anomaly_detector",
        pattern=re.compile(r"\banomaly\b", re.IGNORECASE),
        severity="info",
        hint="Una operación fue bloqueada por el detector de anomalías.",
    ),
]


def _parse_line(line: str) -> tuple[Optional[datetime], str]:
    if not line:
        return None, ""
    parts = line.split(" ", 1)
    if not parts:
        return None, line.strip()
    try:
        ts = datetime.fromisoformat(parts[0])
        message = parts[1] if len(parts) > 1 else ""
        return ts, message.strip()
    except ValueError:
        return None, line.strip()


def _load_last_lines(path: Path, limit: int = 2000) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()
    return lines[-limit:]


def collect_alerts(
    *,
    bridge_log: Path,
    decisions_log: Path,
    window_minutes: int = 60,
) -> Dict[str, object]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)

    counters: Dict[str, Dict[str, object]] = {}
    last_heartbeat: Optional[datetime] = None

    for raw in _load_last_lines(bridge_log):
        ts, message = _parse_line(raw.strip())
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts and ts < window_start:
            continue
        if "heartbeat" in message.lower():
            last_heartbeat = ts
        for rule in RULES:
            if rule.pattern.search(message):
                entry = counters.setdefault(
                    rule.name,
                    {
                        "count": 0,
                        "latest": None,
                        "severity": rule.severity,
                        "hint": rule.hint,
                    },
                )
                entry["count"] = int(entry["count"]) + 1
                if ts and (entry["latest"] is None or ts > entry["latest"]):  # type: ignore
                    entry["latest"] = ts

    decisions_recent = 0
    for raw in _load_last_lines(decisions_log, limit=500):
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ts_raw = payload.get("ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= window_start:
            decisions_recent += 1

    summary = {
        "window_minutes": window_minutes,
        "last_heartbeat_ts": last_heartbeat.isoformat().replace("+00:00", "Z") if last_heartbeat else None,
        "heartbeat_delay_seconds": (now - last_heartbeat).total_seconds() if last_heartbeat else None,
        "decisions_last_window": decisions_recent,
    }

    alerts = [
        {
            "name": name,
            "count": data["count"],
            "latest": data["latest"].isoformat().replace("+00:00", "Z") if data["latest"] else None,
            "severity": data["severity"],
            "hint": data["hint"],
        }
        for name, data in counters.items()
    ]

    alerts.sort(key=lambda item: (-item["count"], item["name"]))
    return {"alerts": alerts, "summary": summary}
