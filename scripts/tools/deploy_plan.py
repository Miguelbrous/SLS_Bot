#!/usr/bin/env python3
"""
Genera un reporte Markdown (Go/No-Go) combinando el resumen Autopilot, estado de riesgo
y eventos de auditoría. Pensado para la fase F5 (ventana piloto).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera reporte Go/No-Go (Markdown).")
    parser.add_argument("--autopilot-summary", type=Path, required=True, help="JSON generado por autopilot_summary.py")
    parser.add_argument("--risk-state", type=Path, default=None, help="Archivo risk_state.json (opcional)")
    parser.add_argument("--audit-log", type=Path, default=None, help="Log JSONL de auditoría (opcional)")
    parser.add_argument("--service-status", action="append", default=[], help="Estado de servicios (ej. sls-bot=active)")
    parser.add_argument("--failover-report", type=Path, default=None, help="Reporte failover más reciente")
    parser.add_argument("--decision", choices=["pending", "go", "no-go"], default="pending")
    parser.add_argument("--output", type=Path, default=None, help="Ruta donde escribir el Markdown (stdout si se omite)")
    return parser.parse_args(list(argv) if argv is not None else None)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_services(entries: List[str]) -> List[dict]:
    summary = []
    for entry in entries:
        if "=" in entry:
            name, status = entry.split("=", 1)
        else:
            name, status = entry, "unknown"
        summary.append({"name": name.strip(), "status": status.strip()})
    return summary


def summarize_risk(path: Optional[Path]) -> dict:
    if not path or not path.exists():
        return {}
    try:
        data = load_json(path)
        return {
            "consecutive_losses": data.get("consecutive_losses"),
            "cooldown_until_ts": data.get("cooldown_until_ts"),
            "active_cooldown_reason": data.get("active_cooldown_reason"),
            "recent_results": data.get("recent_results", [])[-5:],
        }
    except Exception:
        return {}


def summarize_audit(path: Optional[Path], limit: int = 3) -> List[dict]:
    if not path or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except Exception:
        return []
    events: List[dict] = []
    for raw in lines[-limit:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return events


def format_ts(ts: Optional[str | int | float]) -> str:
    if ts is None:
        return "-"
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return str(ts)


def render_markdown(data: dict) -> str:
    dataset = data["dataset"]
    arena = data["arena"]
    services = data["services"]
    risk = data["risk"]
    audit = data["audit"]
    failover = data["failover"]
    decision = data["decision"]
    lines: List[str] = []
    lines.append("# Go/No-Go Report")
    lines.append("")
    lines.append(f"_Generado: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}_")
    lines.append("")

    lines.append("## Checklist")
    if services:
        for svc in services:
            status = svc["status"]
            badge = "✅" if status in {"active", "green", "ok"} else "⚠️"
            lines.append(f"- {badge} {svc['name']}: {status}")
    else:
        lines.append("- ⚠️ Servicios sin revisar (añade `--service-status`)")
    lines.append(f"- Failover report: {failover if failover else '⚠️ no reportado'}")
    lines.append(f"- Dataset violaciones: {', '.join(dataset['violations']) if dataset['violations'] else 'ninguna'}")
    lines.append(f"- Arena candidatos: {len(arena['accepted'])} aceptados / {len(arena['rejected'])} rechazados")
    lines.append("")

    lines.append("## Dataset")
    lines.append(f"- Filas: {dataset['summary']['total']}  · Win rate: {(dataset['summary']['win_rate']*100):.1f}%")
    lines.append(f"- Símbolo dominante: {(dataset['summary']['dominant_symbol_share']*100):.1f}%")
    if dataset["violations"]:
        lines.append(f"- **Violaciones:** {', '.join(dataset['violations'])}")
    lines.append("")

    lines.append("## Top estrategias")
    if arena["accepted"]:
        lines.append("| Rank | Estrategia | Score | Sharpe | Calmar | PF | Win% | DD% | Drift |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for idx, row in enumerate(arena["accepted"][:5], 1):
            stats = row["stats"]
            lines.append(
                f"| {idx} | {row['name']} | {row['score']:.2f} | {stats.get('sharpe', 0):.2f} | "
                f"{stats.get('calmar', 0):.2f} | {stats.get('profit_factor', 0):.2f} | "
                f"{(stats.get('win_rate', 0)*100):.1f}% | {stats.get('max_drawdown', 0):.2f}% | "
                f"{stats.get('feature_drift', 0):.3f} |"
            )
    else:
        lines.append("_No hay candidatos activos (autopilot_summary)._")
    lines.append("")

    if arena["rejected"]:
        lines.append("### Rechazados")
        for rej in arena["rejected"][:5]:
            lines.append(f"- {rej['name']}: {', '.join(rej.get('violations', []))}")
        lines.append("")

    lines.append("## Riesgo actual")
    if risk:
        lines.append(f"- Consecutive losses: {risk.get('consecutive_losses')}")
        if risk.get("active_cooldown_reason"):
            lines.append(f"- Cooldown activo: {risk['active_cooldown_reason']} hasta {format_ts(risk.get('cooldown_until_ts'))}")
        if risk.get("recent_results"):
            results = ", ".join(str(entry.get("pnl")) for entry in risk["recent_results"])
            lines.append(f"- Resultados recientes: {results}")
    else:
        lines.append("- No se encontró risk_state.json")
    lines.append("")

    lines.append("## Auditoría (últimos eventos)")
    if audit:
        for event in audit:
            status = "ok" if event.get("success") else "fail"
            lines.append(f"- {event.get('ts')}: {event.get('actor')} → {event.get('action')} ({status})")
    else:
        lines.append("- Sin eventos recientes (o sin AUDIT_LOG)")
    lines.append("")

    decision_map = {"pending": "🟡 Pendiente", "go": "🟢 GO", "no-go": "🔴 NO GO"}
    lines.append(f"## Estado: {decision_map.get(decision, 'Pendiente')}")
    return "\n".join(lines).strip()


def main() -> None:
    args = parse_args()
    markdown = generate_report(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)


def generate_report(args: argparse.Namespace) -> str:
    autopilot = load_json(args.autopilot_summary)
    dataset = autopilot.get("dataset") or {}
    arena = autopilot.get("arena") or {}
    if args.failover_report:
        if args.failover_report.exists():
            failover_ref: Optional[str] = str(args.failover_report)
        else:
            failover_ref = f"missing:{args.failover_report}"
    else:
        failover_ref = None

    summary_data = {
        "dataset": {
            "summary": {
                "total": int(dataset.get("summary", {}).get("total") or 0),
                "win_rate": float(dataset.get("summary", {}).get("win_rate") or 0.0),
                "dominant_symbol_share": float(dataset.get("summary", {}).get("dominant_symbol_share") or 0.0),
            },
            "violations": dataset.get("violations") or [],
        },
        "arena": {
            "accepted": arena.get("accepted") or [],
            "rejected": arena.get("rejected") or [],
        },
        "services": summarize_services(args.service_status),
        "risk": summarize_risk(args.risk_state),
        "audit": summarize_audit(args.audit_log),
        "failover": failover_ref,
        "decision": args.decision,
    }
    return render_markdown(summary_data)


if __name__ == "__main__":
    main()
