#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from bot.config_loader import load_config  # type: ignore
except ImportError:
    from bot.sls_bot.config_loader import load_config  # type: ignore


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


def _resolve_logs_dir(mode: str, override: Optional[Path]) -> Path:
    if override:
        return override.expanduser().resolve()
    # enforce mode before loading config
    os.environ.setdefault("SLSBOT_MODE", mode)
    cfg = load_config()
    paths = cfg.get("paths") if isinstance(cfg, dict) else {}
    raw = (paths or {}).get("logs_dir")
    if isinstance(raw, str) and raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (ROOT_DIR / candidate).resolve()
        return candidate
    return (ROOT_DIR / "logs" / mode).resolve()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tail_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for raw in lines[-limit:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    return rows


def _evaluate_pnl(entries: List[Dict[str, Any]], now: datetime, *, max_stale_seconds: int, min_trades: int, deadline: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    last_ts = None
    if entries:
        last_ts = _parse_iso(entries[-1].get("ts"))
    if not last_ts:
        issues.append({"key": "pnl_empty", "message": "No hay registros recientes en pnl.jsonl"})
    else:
        diff = (now - last_ts).total_seconds()
        if diff > max_stale_seconds:
            issues.append({"key": "pnl_stale", "message": f"Pnl.jsonl sin entradas desde hace {diff/60:.1f} minutos"})
    # trades today
    threshold = 0
    if entries:
        today = now.date().isoformat()
        threshold = sum(1 for entry in entries if entry.get("type") == "close" and entry.get("ts", "").startswith(today))
        if _deadline_passed(deadline, now) and threshold < min_trades:
            issues.append({"key": "trades_shortfall", "message": f"{threshold}/{min_trades} cierres registrados hoy antes de {deadline}Z"})
    return issues


def _deadline_passed(deadline: str, now: datetime) -> bool:
    try:
        hour, minute = [int(part) for part in deadline.split(":")]
    except Exception:
        return False
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=now.tzinfo)
    if target <= now:
        return True
    return False


def _evaluate_risk(risk: Dict[str, Any], now: datetime, *, block_grace_seconds: int) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if not risk:
        return issues
    target_date = risk.get("date")
    if isinstance(target_date, str) and target_date != now.date().isoformat():
        issues.append({"key": "risk_stale", "message": f"risk_state.json quedó en {target_date}"})
    cooldown = risk.get("cooldown_until_ts")
    blocked = bool(risk.get("blocked"))
    if blocked:
        reason = risk.get("blocked_reason") or risk.get("active_cooldown_reason") or "cooldown"
        issues.append({"key": "risk_blocked", "message": f"Bot en cooldown activo ({reason})."})
    elif cooldown:
        try:
            remaining = float(cooldown) - datetime.now(tz=timezone.utc).timestamp()
        except Exception:
            remaining = 0
        if remaining > block_grace_seconds:
            issues.append({"key": "cooldown_long", "message": f"Cooldown restante {remaining/60:.1f}m (gracia {block_grace_seconds/60:.1f}m)."})
    return issues


def _api_checks(api_base: Optional[str], panel_token: Optional[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    status: Dict[str, Any] = {}
    if not api_base:
        return issues, status
    headers = {}
    if panel_token:
        headers["X-Panel-Token"] = panel_token
    try:
        resp = requests.get(f"{api_base.rstrip('/')}/health", timeout=10)
        resp.raise_for_status()
        status["health"] = resp.json()
    except Exception as exc:
        issues.append({"key": "api_health", "message": f"API /health falló: {exc}"})
    try:
        resp = requests.get(f"{api_base.rstrip('/')}/risk", headers=headers, timeout=10)
        resp.raise_for_status()
        status["risk"] = resp.json()
    except Exception as exc:
        issues.append({"key": "api_risk", "message": f"API /risk falló: {exc}"})
    return issues, status


def _post_slack(webhook: str, text: str) -> None:
    resp = requests.post(webhook, json={"text": text}, timeout=10)
    resp.raise_for_status()


def _post_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()


def _format_summary(now: datetime, trades_today: int, min_trades: int, last_pnl: Optional[datetime]) -> str:
    return (
        f"[real-watchdog] fecha={now.isoformat()} trades_hoy={trades_today}/{min_trades} "
        f"ultimo_pnl={last_pnl.isoformat() if last_pnl else 'n/a'}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vigila el modo real (pnl + riesgo + API).")
    parser.add_argument("--mode", default="real", help="Perfil de config (default real)")
    parser.add_argument("--logs-dir", type=Path, default=None, help="Override para logs/<mode>")
    parser.add_argument("--risk-file", type=Path, default=None)
    parser.add_argument("--pnl-file", type=Path, default=None)
    parser.add_argument("--api-base", help="URL base del API real (https://api...)")
    parser.add_argument("--panel-token", help="Token para headers X-Panel-Token")
    parser.add_argument("--max-pnl-stale-seconds", type=int, default=3600)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--deadline", default="22:00")
    parser.add_argument("--block-grace-seconds", type=int, default=900)
    parser.add_argument("--slack-webhook")
    parser.add_argument("--telegram-token")
    parser.add_argument("--telegram-chat-id")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    logs_dir = _resolve_logs_dir(args.mode, args.logs_dir)
    risk_path = args.risk_file or (logs_dir / "risk_state.json")
    pnl_path = args.pnl_file or (logs_dir / "pnl.jsonl")

    pnl_entries = _tail_jsonl(pnl_path, limit=500)
    trades_today = sum(
        1
        for entry in pnl_entries
        if entry.get("type") == "close" and isinstance(entry.get("ts"), str) and entry["ts"].startswith(now.date().isoformat())
    )
    pnl_issues = _evaluate_pnl(
        pnl_entries,
        now,
        max_stale_seconds=args.max_pnl_stale_seconds,
        min_trades=args.min_trades,
        deadline=args.deadline,
    )
    risk_payload = _load_json(risk_path)
    risk_issues = _evaluate_risk(risk_payload, now, block_grace_seconds=args.block_grace_seconds)
    api_issues, api_status = _api_checks(args.api_base, args.panel_token)
    all_issues = pnl_issues + risk_issues + api_issues

    last_ts = _parse_iso(pnl_entries[-1].get("ts")) if pnl_entries else None
    summary = _format_summary(now, trades_today, args.min_trades, last_ts)
    print(summary)
    if api_status:
        print(f"[real-watchdog] API status keys: {', '.join(api_status.keys())}")

    if not all_issues:
        print("[real-watchdog] Todo en orden.")
        return 0

    for issue in all_issues:
        print(f"- {issue['message']}")
    message = summary + "\n" + "\n".join(f"- {issue['message']}" for issue in all_issues)
    if args.dry_run:
        return 2
    notified = False
    if args.slack_webhook:
        _post_slack(args.slack_webhook, message)
        notified = True
    if args.telegram_token and args.telegram_chat_id:
        _post_telegram(args.telegram_token, args.telegram_chat_id, message)
        notified = True
    if not notified:
        print("[real-watchdog] No hooks configurados; alerta solo en stdout.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
