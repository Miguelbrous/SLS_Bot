from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
import json
from typing import List

import pytest

from scripts import ops


@pytest.fixture()
def stub_run(monkeypatch):
    calls: List[dict] = []

    def _fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})

    monkeypatch.setattr(ops, "_run", _fake_run)
    monkeypatch.setattr(ops, "_python_exec", lambda: "python")
    return calls


def test_infra_command_invokes_infra_check(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(["infra", "--env-file", ".env.local", "--ensure-dirs"])
    args.func(args)
    assert stub_run[0]["cmd"] == ["python", str(ops.INFRA_CHECK), "--env-file", ".env.local", "--ensure-dirs"]


def test_cerebro_dataset_command_builds_expected_args(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        ["cerebro", "dataset", "--mode", "real", "--rows", "250", "--bias", "0.25", "--overwrite"]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        str(ops.GENERATE_DATASET),
        "--mode",
        "real",
        "--rows",
        "250",
        "--bias",
        "0.25",
        "--overwrite",
    ]


def test_cerebro_promote_command_accepts_min_value(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        ["cerebro", "promote", "--mode", "real", "--metric", "win_rate", "--min-value", "0.7"]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        str(ops.PROMOTE_MODEL),
        "--mode",
        "real",
        "--metric",
        "win_rate",
        "--min-value",
        "0.7",
    ]


def test_deploy_bootstrap_passes_env(stub_run, monkeypatch):
    parser = ops.build_parser()
    args = parser.parse_args(["deploy", "bootstrap", "--app-root", "/opt/app", "--svc-user", "sls", "--install-systemd"])
    args.func(args)
    call = stub_run[-1]
    assert call["cmd"] == ["bash", str(ops.DEPLOY_BOOTSTRAP)]
    env = call["kwargs"]["env"]
    assert env["APP_ROOT"] == "/opt/app"
    assert env["SVC_USER"] == "sls"
    assert env["INSTALL_SYSTEMD"] == "1"


def test_monitor_check_command(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "monitor",
            "check",
            "--api-base",
            "https://api",
            "--panel-token",
            "token",
            "--max-arena-lag",
            "100",
            "--max-drawdown",
            "25",
            "--max-ticks-since-win",
            "10",
            "--dry-run",
        ]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        str(ops.MONITOR_GUARD),
        "--api-base",
        "https://api",
        "--max-arena-lag",
        "100",
        "--max-drawdown",
        "25.0",
        "--max-ticks-since-win",
        "10",
        "--panel-token",
        "token",
        "--dry-run",
    ]


def test_observability_check_command(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "observability",
            "check",
            "--prom-base",
            "http://prom",
            "--grafana-base",
            "http://grafana",
            "--grafana-user",
            "admin",
            "--grafana-password",
            "secret",
            "--alertmanager-base",
            "http://alert",
        ]
    )
    args.func(args)
    call = stub_run[-1]
    assert call["cmd"] == ["python", str(ops.OBS_CHECK)]
    env = call["kwargs"]["env"]
    assert env["PROM_BASE"] == "http://prom"
    assert env["GRAFANA_BASE"] == "http://grafana"
    assert env["GRAFANA_USER"] == "admin"
    assert env["GRAFANA_PASSWORD"] == "secret"
    assert env["ALERTMANAGER_BASE"] == "http://alert"


def test_arena_promote_command_builds_thresholds(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "arena",
            "promote",
            "strat_x",
            "--output-dir",
            "/tmp/pkg",
            "--min-trades",
            "80",
            "--min-sharpe",
            "0.4",
            "--max-drawdown",
            "20",
            "--force",
        ]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        str(ops.ARENA_PROMOTE),
        "strat_x",
        "--min-trades",
        "80",
        "--min-sharpe",
        "0.4",
        "--max-drawdown",
        "20.0",
        "--output-dir",
        "/tmp/pkg",
        "--force",
    ]


def test_arena_ledger_command_prints(monkeypatch, capsys):
    class DummyStorage:
        def ledger_for(self, strategy_id, limit):
            assert strategy_id == "strat_x"
            assert limit == 5
            return [
                {"ts": "2025-01-01T00:00:00Z", "pnl": 1.2345, "balance_after": 101.5, "reason": "ok"},
            ]

    monkeypatch.setattr(ops, "ArenaStorage", lambda: DummyStorage())
    parser = ops.build_parser()
    args = parser.parse_args(["arena", "ledger", "strat_x", "--limit", "5"])
    args.func(args)
    out = capsys.readouterr().out
    assert "1.2345" in out
    assert "motivo=ok" in out


def test_arena_ledger_command_exports_csv(monkeypatch, tmp_path):
    class DummyStorage:
        def ledger_for(self, strategy_id, limit):
            return [
                {"ts": "2025-01-01T00:00:00Z", "pnl": 2.5, "balance_after": 200.0, "reason": "export"},
            ]

    monkeypatch.setattr(ops, "ArenaStorage", lambda: DummyStorage())
    parser = ops.build_parser()
    dest = tmp_path / "ledger.csv"
    args = parser.parse_args(["arena", "ledger", "strat_x", "--csv", str(dest)])
    args.func(args)
    content = dest.read_text(encoding="utf-8")
    assert "export" in content
    assert "2.500000" in content


def test_arena_stats_command_text(monkeypatch, capsys):
    class DummyStorage:
        def ledger_summary(self, strategy_id, limit):
            return {
                "strategy_id": strategy_id,
                "total_trades": 10,
                "wins": 6,
                "losses": 4,
                "win_rate": 60.0,
                "total_pnl": 12.345,
                "avg_pnl": 1.2345,
                "final_balance": 112.34,
                "max_drawdown_pct": 8.5,
            }

    monkeypatch.setattr(ops, "ArenaStorage", lambda: DummyStorage())
    parser = ops.build_parser()
    args = parser.parse_args(["arena", "stats", "strat_x"])
    args.func(args)
    out = capsys.readouterr().out
    assert "Trades: 10" in out
    assert "Win rate: 60.00%" in out


def test_arena_stats_command_json(monkeypatch, capsys):
    class DummyStorage:
        def ledger_summary(self, strategy_id, limit):
            return {"strategy_id": strategy_id, "total_trades": 2}

    monkeypatch.setattr(ops, "ArenaStorage", lambda: DummyStorage())
    parser = ops.build_parser()
    args = parser.parse_args(["arena", "stats", "strat_y", "--json"])
    args.func(args)
    out = capsys.readouterr().out
    assert '"total_trades": 2' in out


def test_cerebro_train_command(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "train",
            "--mode",
            "real",
            "--dataset",
            "/tmp/data.jsonl",
            "--output-dir",
            "/tmp/models",
            "--epochs",
            "200",
            "--lr",
            "0.1",
            "--train-ratio",
            "0.7",
            "--min-auc",
            "0.6",
            "--min-win-rate",
            "0.55",
            "--seed",
            "7",
            "--dry-run",
            "--no-promote",
        ]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        "-m",
        "bot.cerebro.train",
        "--mode",
        "real",
        "--dataset",
        "/tmp/data.jsonl",
        "--output-dir",
        "/tmp/models",
        "--epochs",
        "200",
        "--lr",
        "0.1",
        "--train-ratio",
        "0.7",
        "--min-auc",
        "0.6",
        "--min-win-rate",
        "0.55",
        "--seed",
        "7",
        "--dry-run",
        "--no-promote",
    ]


def test_arena_promote_real_command(monkeypatch, stub_run, tmp_path):
    pkg_dir = tmp_path / "pkg"
    monkeypatch.setattr(ops, "export_strategy", lambda *a, **k: pkg_dir)
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "arena",
            "promote-real",
            "strat_q",
            "--min-trades",
            "80",
            "--min-sharpe",
            "0.5",
            "--max-drawdown",
            "25",
            "--source-mode",
            "test",
            "--target-mode",
            "real",
            "--min-auc",
            "0.6",
            "--min-win-rate",
            "0.55",
            "--skip-dataset-rotation",
        ]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        str(ops.PROMOTE_MODEL),
        "--source-mode",
        "test",
        "--target-mode",
        "real",
        "--min-auc",
        "0.6",
        "--min-win-rate",
        "0.55",
        "--skip-dataset-rotation",
    ]


def test_cerebro_ingest_command(stub_run):
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "ingest",
            "--symbols",
            "BTCUSDT,ETHUSDT",
            "--funding-symbols",
            "BTCUSDT",
            "--onchain-symbols",
            "ETHUSDT",
            "--require-sources",
            "market,funding",
            "--min-market-rows",
            "10",
            "--include-news",
            "--include-orderflow",
            "--include-funding",
            "--include-onchain",
            "--output",
            "tmp_logs/ingest.json",
            "--slack-webhook",
            "https://hooks.slack.test",
            "--slack-user",
            "ingest-bot",
            "--slack-timeout",
            "7",
            "--slack-proxy",
            "http://proxy.local:8080",
            "--prometheus-file",
            "/var/lib/node_exporter/cerebro_ingest.prom",
        ]
    )
    args.func(args)
    assert stub_run[-1]["cmd"] == [
        "python",
        str(ops.CEREBRO_INGEST),
        "--symbols",
        "BTCUSDT,ETHUSDT",
        "--funding-symbols",
        "BTCUSDT",
        "--onchain-symbols",
        "ETHUSDT",
        "--market-limit",
        "200",
        "--news-limit",
        "50",
        "--macro-limit",
        "20",
        "--max-tasks",
        "50",
        "--output",
        "tmp_logs/ingest.json",
        "--include-news",
        "--include-orderflow",
        "--include-funding",
        "--include-onchain",
        "--require-sources",
        "market,funding",
        "--min-market-rows",
        "10",
        "--slack-webhook",
        "https://hooks.slack.test",
        "--slack-user",
        "ingest-bot",
        "--slack-timeout",
        "7.0",
        "--slack-proxy",
        "http://proxy.local:8080",
        "--prometheus-file",
        "/var/lib/node_exporter/cerebro_ingest.prom",
    ]


def test_cerebro_autopilot_command_generates_dataset(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "autopilot",
            "--mode",
            "test",
            "--dataset",
            str(dataset_path),
            "--min-rows",
            "5",
            "--backfill-rows",
            "10",
            "--epochs",
            "100",
            "--lr",
            "0.1",
            "--log-file",
            str(tmp_path / "autopilot.log"),
        ]
    )

    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if "generate_cerebro_dataset" in str(cmd[1]):
            rows = []
            for idx in range(60):
                pnl = 1 if idx % 2 == 0 else -0.5
                rows.append(json.dumps({"symbol": "BTCUSDT", "decision": "LONG", "pnl": pnl, "features": {}}))
            dataset_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def fake_capture(cmd):
        commands.append(cmd)
        payload = {"metrics": {"auc": 0.7}, "status": "PROMOVIDO"}
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(ops, "_run", fake_run)
    monkeypatch.setattr(ops, "_run_capture_output", fake_capture)
    args.func(args)
    assert str(ops.GENERATE_DATASET) in commands[0][1]
    assert any("bot.cerebro.train" in part for part in commands[-1])


def test_cerebro_autopilot_dataset_check_can_be_skipped(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    rows = []
    for idx in range(60):
        pnl = -1 if idx % 2 == 0 else -0.2
        rows.append(json.dumps({"symbol": "BTCUSDT", "decision": "LONG", "pnl": pnl, "features": {}}))
    dataset_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "autopilot",
            "--mode",
            "test",
            "--dataset",
            str(dataset_path),
            "--min-rows",
            "1",
            "--skip-dataset-check",
        ]
    )

    def fake_run(cmd, **kwargs):
        return None

    def fake_capture(cmd):
        class Result:
            stdout = json.dumps({"metrics": {"auc": 0.7, "win_rate": 0.6}, "status": "PROMOVIDO"})

        return Result()

    monkeypatch.setattr(ops, "_run", fake_run)
    monkeypatch.setattr(ops, "_run_capture_output", fake_capture)
    args.func(args)


def test_cerebro_autopilot_enforces_dataset_age(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    rows = []
    for idx in range(60):
        pnl = 1 if idx % 2 == 0 else -0.5
        rows.append(json.dumps({"symbol": "BTCUSDT", "decision": "SHORT", "pnl": pnl, "features": {}}))
    dataset_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    old_time = time.time() - 7200
    os.utime(dataset_path, (old_time, old_time))
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "autopilot",
            "--mode",
            "test",
            "--dataset",
            str(dataset_path),
            "--min-rows",
            "5",
            "--max-dataset-age-minutes",
            "5",
            "--log-file",
            str(tmp_path / "autopilot.log"),
        ]
    )
    monkeypatch.setattr(ops, "_run_capture_output", lambda cmd: (_ for _ in ()).throw(AssertionError("no training")))
    with pytest.raises(SystemExit):
        args.func(args)


def test_cerebro_autopilot_prometheus_and_slack(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    payloads = []
    for idx in range(80):
        pnl = 1 if idx % 2 == 0 else -0.4
        payloads.append(json.dumps({"symbol": "ETHUSDT", "decision": "LONG", "pnl": pnl, "features": {}}))
    dataset_path.write_text("\n".join(payloads) + "\n", encoding="utf-8")
    prom_file = tmp_path / "metrics.prom"
    log_file = tmp_path / "autopilot.log"
    summary_file = tmp_path / "summary.jsonl"
    payload = {
        "metrics": {"auc": 0.71, "win_rate": 0.63, "samples_train": 80, "samples_test": 20},
        "status": "PROMOVIDO",
        "artifact": "/tmp/model.json",
    }
    monkeypatch.setattr(ops, "_run_capture_output", lambda cmd: SimpleNamespace(stdout=json.dumps(payload)))
    slack_calls = []
    monkeypatch.setattr(ops, "_post_slack", lambda webhook, text, username: slack_calls.append((webhook, text, username)))
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "autopilot",
            "--mode",
            "test",
            "--dataset",
            str(dataset_path),
            "--min-rows",
            "5",
            "--prometheus-file",
            str(prom_file),
            "--slack-webhook",
            "https://hooks.slack.test",
            "--slack-user",
            "autopilot-bot",
            "--log-file",
            str(log_file),
            "--summary-json",
            str(summary_file),
            "--summary-append",
        ]
    )
    args.func(args)
    content = prom_file.read_text(encoding="utf-8")
    assert "cerebro_autopilot_success 1" in content
    assert 'cerebro_autopilot_metric{name="auc"} 0.71' in content
    assert "cerebro_autopilot_dataset_win_rate" in content
    assert "cerebro_autopilot_dataset_age_hours" in content
    summary_lines = summary_file.read_text(encoding="utf-8").strip().splitlines()
    assert summary_lines
    summary_payload = json.loads(summary_lines[-1])
    assert summary_payload["dataset_stats"]["positives"] > 0
    assert slack_calls
    assert ":white_check_mark:" in slack_calls[0][1]
    assert "dataset:" in slack_calls[0][1]
    assert slack_calls[0][2] == "autopilot-bot"


def test_cerebro_autopilot_require_promote(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    rows = []
    for idx in range(60):
        pnl = 1 if idx % 2 == 0 else -0.5
        rows.append(json.dumps({"symbol": "BTCUSDT", "decision": "LONG", "pnl": pnl, "features": {}}))
    dataset_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    prom_file = tmp_path / "metrics.prom"
    payload = {
        "metrics": {"auc": 0.6, "win_rate": 0.55},
        "status": "SOLO_ENTRENADO",
    }
    monkeypatch.setattr(ops, "_run_capture_output", lambda cmd: SimpleNamespace(stdout=json.dumps(payload)))
    parser = ops.build_parser()
    args = parser.parse_args(
        [
            "cerebro",
            "autopilot",
            "--mode",
            "test",
            "--dataset",
            str(dataset_path),
            "--min-rows",
            "5",
            "--require-promote",
            "--prometheus-file",
            str(prom_file),
            "--log-file",
            str(tmp_path / "autopilot.log"),
        ]
    )
    with pytest.raises(SystemExit):
        args.func(args)
    content = prom_file.read_text(encoding="utf-8")
    assert "cerebro_autopilot_success 0" in content
