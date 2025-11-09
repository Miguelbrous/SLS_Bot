import json
import os
from pathlib import Path

os.environ.setdefault("SLSBOT_CONFIG", "config/config.sample.json")

from scripts.tools import autopilot_summary, deploy_plan


def _generate_autopilot_summary(tmp_path: Path) -> Path:
    args = autopilot_summary.parse_args(
        [
            "--dataset",
            "sample_data/cerebro_experience_sample.jsonl",
            "--runs",
            "sample_data/arena_runs_sample.jsonl",
            "--min-trades",
            "50",
            "--max-drawdown",
            "6",
        ]
    )
    data = autopilot_summary.autopilot_summary(args)
    path = tmp_path / "autopilot_summary.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_deploy_plan_markdown(tmp_path: Path):
    summary_path = _generate_autopilot_summary(tmp_path)
    risk_path = tmp_path / "risk_state.json"
    risk_path.write_text(
        json.dumps({"consecutive_losses": 1, "active_cooldown_reason": None, "recent_results": [{"pnl": 5}]}),
        encoding="utf-8",
    )
    audit_path = tmp_path / "audit.log"
    audit_path.write_text(json.dumps({"ts": "2025-01-01T00:00:00Z", "actor": "tester", "action": "sls-bot.status", "success": True}) + "\n", encoding="utf-8")

    args = deploy_plan.parse_args(
        [
            "--autopilot-summary",
            str(summary_path),
            "--risk-state",
            str(risk_path),
            "--audit-log",
            str(audit_path),
            "--service-status",
            "sls-bot=active",
            "--decision",
            "pending",
        ]
    )

    markdown = deploy_plan.generate_report(args)
    assert "Go/No-Go Report" in markdown
    assert "strategy_alpha" in markdown
    assert "Filas" in markdown
