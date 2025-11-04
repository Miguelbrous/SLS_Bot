from __future__ import annotations

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
