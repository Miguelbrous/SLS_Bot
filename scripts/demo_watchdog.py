#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from bot.config_loader import load_config  # type: ignore
except ImportError:
    from bot.sls_bot.config_loader import load_config  # type: ignore

ROOT_DIR = Path(__file__).resolve().parents[1]


def _resolve_logs_dir(explicit: Optional[Path] = None) -> Path:
    if explicit:
        return explicit.expanduser().resolve()
    cfg = load_config()
    paths_cfg = cfg.get("paths") if isinstance(cfg, dict) else {}
    raw = (paths_cfg or {}).get("logs_dir")
    if isinstance(raw, str) and raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (ROOT_DIR / candidate).resolve()
        return candidate
    return (ROOT_DIR / "logs").resolve()


def _parse_iso(ts_raw: Optional[str]) -> Optional[datetime]:
    if not ts_raw:
        return None
    try:
        raw = ts_raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_last_history_ts(path: Path) -> Optional[datetime]:
    if not path.exists():
        return None
    last_line: Optional[str] = None
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if line:
                last_line = line
    if not last_line:
        return None
    try:
        payload = json.loads(last_line)
    except Exception:
        return None
    return _parse_iso(payload.get("ts"))


def _deadline_passed(deadline: str, now: datetime) -> bool:
    try:
        hour, minute = [int(part) for part in deadline.split(":")]
    except Exception:
        return False
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        return True
    return False


def _evaluate_issues(
    *,
    now: datetime,
    state: Dict[str, Any],
    history_ts: Optional[datetime],
    risk: Dict[str, Any],
    target_trades: int,
    max_stale_seconds: int,
    deadline: str,
    alert_if_blocked: bool,
    cooldown_grace: int,
    max_failures: int,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    trades_sent = int(state.get("trades_sent") or 0)
    if history_ts:
        diff = (now - history_ts).total_seconds()
        if diff > max_stale_seconds:
            issues.append(
                {
                    "key": "emitter_idle",
                    "message": f"Demo emitter sin señales hace {diff:.0f}s (umbral {max_stale_seconds}s).",
                }
            )
    else:
        issues.append({"key": "no_history", "message": "No hay historial en demo_emitter_history.jsonl"})

    if _deadline_passed(deadline, now) and trades_sent < target_trades:
        issues.append(
            {
                "key": "target_miss",
                "message": f"Meta diaria {trades_sent}/{target_trades} sin alcanzar antes de {deadline}Z.",
            }
        )

    state_date = state.get("date")
    if state_date and isinstance(state_date, str):
        try:
            if state_date != now.date().isoformat():
                issues.append(
                    {
                        "key": "state_desync",
                        "message": f"demo_emitter_state quedó en {state_date} (hoy {now.date().isoformat()}).",
                    }
                )
        except Exception:
            pass

    failures = int(state.get("failures") or 0)
    if max_failures >= 0 and failures > max_failures:
        issues.append(
            {
                "key": "emitter_failures",
                "message": f"{failures} fallos HTTP registrados (umbral {max_failures}).",
            }
        )

    if alert_if_blocked:
        blocked = bool(risk.get("blocked"))
        cooldown_ts = risk.get("cooldown_until_ts")
        if blocked:
            reason = risk.get("blocked_reason") or risk.get("active_cooldown_reason") or "cooldown"
            issues.append({"key": "risk_blocked", "message": f"Bot en cooldown activo ({reason})."})
        elif cooldown_ts:
            try:
                cooldown_until = float(cooldown_ts)
            except Exception:
                cooldown_until = None
            if cooldown_until:
                remaining = cooldown_until - time.time()
                if remaining > cooldown_grace:
                    issues.append(
                        {
                            "key": "cooldown_long",
                            "message": f"Cooldown restante {remaining/60:.1f}m (gracia {cooldown_grace/60:.1f}m).",
                        }
                    )
    return issues


def _post_slack(webhook: str, text: str) -> None:
    resp = requests.post(webhook, json={"text": text}, timeout=10)
    resp.raise_for_status()


def _post_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()


def _format_alert(issues: List[Dict[str, Any]]) -> str:
    lines = ["[demo-watchdog] Alertas detectadas:"]
    for issue in issues:
        lines.append(f"- {issue['message']}")
    return "\n".join(lines)


def _load_emitter_config(path: Path) -> Dict[str, Any]:
    candidates = [path, ROOT_DIR / "config" / "demo_emitter.json", ROOT_DIR / "config" / "demo_emitter.sample.json"]
    for candidate in candidates:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vigila el loop demo (emisor + riesgo).")
    parser.add_argument("--logs-dir", type=Path, default=None)
    parser.add_argument("--state-path", type=Path, default=None, help="Ruta a demo_emitter_state.json")
    parser.add_argument("--history-path", type=Path, default=None, help="Ruta a demo_emitter_history.jsonl")
    parser.add_argument("--risk-state-path", type=Path, default=None, help="Ruta a risk_state.json (modo demo)")
    parser.add_argument("--config-path", type=Path, default=ROOT_DIR / "config" / "demo_emitter.json")
    parser.add_argument("--max-stale-seconds", type=int, default=None)
    parser.add_argument("--target-trades", type=int, default=None)
    parser.add_argument("--target-deadline", default="22:30", help="Hora UTC para exigir meta diaria (HH:MM)")
    parser.add_argument("--block-grace-seconds", type=int, default=900)
    parser.add_argument("--max-failures", type=int, default=5)
    parser.add_argument("--alert-if-blocked", dest="alert_if_blocked", action="store_true", default=True)
    parser.add_argument("--no-alert-if-blocked", dest="alert_if_blocked", action="store_false")
    parser.add_argument("--slack-webhook")
    parser.add_argument("--telegram-token")
    parser.add_argument("--telegram-chat-id")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logs_dir = _resolve_logs_dir(args.logs_dir)
    state_path = args.state_path or (logs_dir / "demo_emitter_state.json")
    history_path = args.history_path or (logs_dir / "demo_emitter_history.jsonl")
    risk_path = args.risk_state_path or (logs_dir / "risk_state.json")

    cfg = _load_emitter_config(args.config_path)
    target_trades = args.target_trades or int(cfg.get("target_daily_trades") or 20)
    interval_seconds = int(cfg.get("interval_seconds") or 60)
    max_stale = args.max_stale_seconds or max(180, interval_seconds * 3)

    state = _load_json(state_path)
    risk = _load_json(risk_path)
    last_ts = _load_last_history_ts(history_path)
    now = datetime.now(timezone.utc)

    issues = _evaluate_issues(
        now=now,
        state=state,
        history_ts=last_ts,
        risk=risk,
        target_trades=target_trades,
        max_stale_seconds=max_stale,
        deadline=args.target_deadline,
        alert_if_blocked=args.alert_if_blocked,
        cooldown_grace=args.block_grace_seconds,
        max_failures=args.max_failures,
    )

    trades_sent = int(state.get("trades_sent") or 0)
    summary = (
        f"[demo-watchdog] trades={trades_sent}/{target_trades} last_signal="
        f"{last_ts.isoformat() if last_ts else 'n/a'} failures={state.get('failures')}"
    )

    if not issues:
        print(summary)
        print("[demo-watchdog] Todo en orden.")
        return 0

    message = _format_alert(issues)
    print(summary)
    print(message)
    if args.dry-run:
        return 2

    notified = False
    if args.slack_webhook:
        _post_slack(args.slack_webhook, f"{summary}\n{message}")
        notified = True
    if args.telegram_token and args.telegram_chat_id:
        _post_telegram(args.telegram_token, args.telegram_chat_id, f"{summary}\n{message}")
        notified = True
    if not notified:
        print("[demo-watchdog] No webhook configurado; alerta solo en stdout.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
