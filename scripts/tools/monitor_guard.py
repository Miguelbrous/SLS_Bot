#!/usr/bin/env python3
"""
Monitor liviano que consulta /arena/state y /metrics para detectar problemas.

Genera alertas cuando:
  - No hay ticks de la arena desde hace demasiado tiempo.
  - El drawdown vs la meta supera el umbral permitido.
  - La arena acumula demasiados ticks sin promover campeones.

Puede enviar notificaciones a Slack (webhook entrante) o Telegram.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Dict, List

import requests


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        raw = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def parse_metrics(payload: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for raw in payload.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        name, value = parts
        try:
            metrics[name] = float(value)
        except ValueError:
            continue
    return metrics


def evaluate_issues(
    state: Dict[str, object],
    metrics: Dict[str, float],
    *,
    lag_threshold: int,
    drawdown_threshold: float,
    ticks_threshold: int,
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    tick_ts = _parse_iso(state.get("last_tick_ts") or state.get("updated_at"))
    now = datetime.now(timezone.utc)
    if tick_ts:
        lag = (now - tick_ts).total_seconds()
    else:
        lag = metrics.get("sls_arena_state_age_seconds")
    if lag is not None and lag > lag_threshold:
        issues.append(
            {
                "key": "arena_lag",
                "message": f"Arena sin tick hace {lag:.0f}s (umbral {lag_threshold}s).",
            }
        )

    drawdown = state.get("drawdown_pct")
    if not isinstance(drawdown, (int, float)):
        drawdown = metrics.get("sls_arena_goal_drawdown_pct")
    if isinstance(drawdown, (int, float)) and drawdown > drawdown_threshold:
        issues.append(
            {
                "key": "arena_drawdown",
                "message": f"Drawdown vs meta {drawdown:.1f}% > {drawdown_threshold}%.",
            }
        )

    ticks_since_win = state.get("ticks_since_win")
    if not isinstance(ticks_since_win, (int, float)):
        ticks_since_win = metrics.get("sls_arena_ticks_since_win")
    if isinstance(ticks_since_win, (int, float)) and ticks_since_win > ticks_threshold:
        issues.append(
            {
                "key": "arena_stall",
                "message": f"{ticks_since_win:.0f} ticks sin campeones (umbral {ticks_threshold}).",
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


def _format_alert(issues: List[Dict[str, str]]) -> str:
    lines = ["🚨 Monitor SLS_Bot"]
    for issue in issues:
        lines.append(f"- {issue['message']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitoriza /arena/state y /metrics.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8880")
    parser.add_argument("--panel-token")
    parser.add_argument("--max-arena-lag", type=int, default=600)
    parser.add_argument("--max-drawdown", type=float, default=30.0)
    parser.add_argument("--max-ticks-since-win", type=int, default=20)
    parser.add_argument("--slack-webhook")
    parser.add_argument("--telegram-token")
    parser.add_argument("--telegram-chat-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    headers = {}
    if args.panel_token:
        headers["X-Panel-Token"] = args.panel_token
    api_base = args.api_base.rstrip("/")

    try:
        resp = requests.get(f"{api_base}/arena/state", headers=headers, timeout=10)
        resp.raise_for_status()
        state = resp.json()
    except Exception as exc:
        print(f"[monitor] Error al leer /arena/state: {exc}", file=sys.stderr)
        return 1

    try:
        resp_metrics = requests.get(f"{api_base}/metrics", timeout=10)
        resp_metrics.raise_for_status()
        metrics = parse_metrics(resp_metrics.text)
    except Exception as exc:
        print(f"[monitor] Error al leer /metrics: {exc}", file=sys.stderr)
        return 1

    issues = evaluate_issues(
        state,
        metrics,
        lag_threshold=args.max_arena_lag,
        drawdown_threshold=args.max_drawdown,
        ticks_threshold=args.max_ticks_since_win,
    )

    if not issues:
        print("[monitor] Todo en orden.")
        return 0

    message = _format_alert(issues)
    print(message)

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
        print("[monitor] No se configuró Slack ni Telegram; alerta solo en stdout.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
