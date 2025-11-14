#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

from bot.config_loader import load_config
from bot.arena.registry import ArenaRegistry
from bot.arena.models import StrategyProfile, StrategyStats

ROOT_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
STATE_PATH = LOGS_DIR / "demo_emitter_state.json"
HISTORY_PATH = LOGS_DIR / "demo_emitter_history.jsonl"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "demo_emitter.json"
SAMPLE_CONFIG_PATH = ROOT_DIR / "config" / "demo_emitter.sample.json"

DEFAULTS: Dict[str, Any] = {
    "webhook_url": os.getenv("DEMO_EMITTER_WEBHOOK") or os.getenv("SLS_WEBHOOK_URL"),
    "panel_token": os.getenv("DEMO_EMITTER_TOKEN") or os.getenv("PANEL_API_TOKEN"),
    "signature_secret": os.getenv("WEBHOOK_SHARED_SECRET"),
    "symbol_pool": ["BTCUSDT", "ETHUSDT"],
    "default_timeframe": "15m",
    "min_risk_pct": 0.5,
    "max_risk_pct": 1.5,
    "target_daily_trades": 20,
    "batch_size": 3,
    "interval_seconds": 60,
    "max_price_slippage_pct": 0.15,
    "dry_run": False
}


class DemoEmitter:
    def __init__(self, config: Dict[str, Any], loop: bool = True):
        self.config = config
        self.loop = loop
        self.registry = ArenaRegistry()
        self.session = requests.Session()
        self.cfg_bybit = load_config().get("bybit", {})
        self.state = self._load_state()
        self.logger = logging.getLogger("demo_emitter")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    def _load_state(self) -> Dict[str, Any]:
        today = datetime.utcnow().date().isoformat()
        if STATE_PATH.exists():
            try:
                state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        else:
            state = {}
        if state.get("date") != today:
            state = {"date": today, "trades_sent": 0, "failures": 0}
        return state

    def _save_state(self) -> None:
        STATE_PATH.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _risk_blocked(self) -> bool:
        risk_path = LOGS_DIR / "risk_state.json"
        if not risk_path.exists():
            return False
        try:
            data = json.loads(risk_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        if data.get("blocked"):
            return True
        cooldown = data.get("cooldown_until_ts")
        if cooldown and cooldown > time.time():
            return True
        return False

    def _pick_profiles(self) -> List[StrategyProfile]:
        profiles = self.registry.all()
        winners = [p for p in profiles if p.mode in {"champion", "race"}]
        if not winners:
            winners = [p for p in profiles if p.mode in {"training"}]
        if not winners:
            return []
        winners.sort(key=lambda p: (p.stats.balance if p.stats else 0.0), reverse=True)
        batch = self.config.get("batch_size", 3)
        return winners[:batch]

    def _decide_side(self, stats: StrategyStats | None) -> str:
        if not stats:
            return random.choice(["LONG", "SHORT"])
        if stats.wins >= stats.losses:
            return "LONG"
        return "SHORT"

    def _risk_pct(self, stats: StrategyStats | None) -> float:
        base = self.config.get("min_risk_pct", 0.5)
        ceiling = self.config.get("max_risk_pct", 1.5)
        if not stats:
            return round(random.uniform(base, ceiling), 3)
        span = max(ceiling - base, 0.1)
        factor = min(max(stats.sharpe_ratio, -1.0), 2.5) / 2.5
        return round(base + span * max(factor, random.random()), 3)

    def _build_signal(self, profile: StrategyProfile) -> Dict[str, Any]:
        stats = profile.stats or StrategyStats(balance=5.0, goal=100.0)
        side = self._decide_side(stats)
        signal = "SLS_LONG_ENTRY" if side == "LONG" else "SLS_SHORT_ENTRY"
        symbol_pool = self.config.get("symbol_pool") or self.cfg_bybit.get("symbols", ["BTCUSDT"])
        symbol = random.choice(symbol_pool)
        payload: Dict[str, Any] = {
            "signal": signal,
            "symbol": symbol,
            "tf": profile.timeframe or self.config.get("default_timeframe", "15m"),
            "timestamp": datetime.utcnow().isoformat(),
            "session": "demo-emitter",
            "side": side,
            "risk_score": round(stats.sharpe_ratio, 3),
            "risk_pct": self._risk_pct(stats),
            "strategy_id": profile.id,
            "leverage": int(self.cfg_bybit.get("default_leverage", 10)),
            "move_sl_to_be_on_tp1": True,
            "tp1_close_pct": 50,
            "order_type": "Market"
        }
        return payload

    def _send_signal(self, payload: Dict[str, Any]) -> bool:
        if self.config.get("dry_run"):
            self.logger.info("[DRY-RUN] %s", json.dumps(payload))
            return True
        token = self.config.get("panel_token")
        if not token:
            raise RuntimeError("DEMO_EMITTER_TOKEN o PANEL_API_TOKEN no configurado")
        body = json.dumps(payload, separators=(",", ":"))
        headers = {
            "Content-Type": "application/json",
            "X-Panel-Token": token.strip()
        }
        secret = self.config.get("signature_secret")
        if secret:
            signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            header_name = os.getenv("WEBHOOK_SIGNATURE_HEADER", "x-webhook-signature")
            headers[header_name] = signature
        url = self.config.get("webhook_url")
        if not url:
            raise RuntimeError("Config demo_emitter: falta webhook_url")
        resp = self.session.post(url, data=body, headers=headers, timeout=20)
        if resp.status_code >= 400:
            self.logger.error("Webhook error %s: %s", resp.status_code, resp.text[:200])
            self.state["failures"] = self.state.get("failures", 0) + 1
            self._save_state()
            return False
        self._log_history(payload, resp.json())
        self.logger.info("Signal sent (%s %s)", payload["signal"], payload["symbol"])
        return True

    def _log_history(self, payload: Dict[str, Any], response: Dict[str, Any]) -> None:
        HISTORY_PATH.parent.mkdir(exist_ok=True, parents=True)
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "payload": payload,
            "response": response
        }
        with HISTORY_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def _tick(self) -> None:
        if self._risk_blocked():
            self.logger.warning("Bot en cooldown segun risk_state.json; esperando...")
            time.sleep(self.config.get("interval_seconds", 60))
            return
        profiles = self._pick_profiles()
        if not profiles:
            self.logger.warning("No hay estrategias elegibles en arena/registry.json")
            time.sleep(self.config.get("interval_seconds", 60))
            return
        for profile in profiles:
            if self.state.get("trades_sent", 0) >= self.config.get("target_daily_trades", 10):
                self.logger.info("Meta diaria alcanzada (%s trades)", self.state.get("trades_sent"))
                return
            payload = self._build_signal(profile)
            if self._send_signal(payload):
                self.state["trades_sent"] = self.state.get("trades_sent", 0) + 1
                self._save_state()
            time.sleep(self.config.get("interval_seconds", 60))

    def run(self) -> None:
        self.logger.info("Demo emitter iniciado (target diario: %s)", self.config.get("target_daily_trades"))
        while True:
            today = datetime.utcnow().date().isoformat()
            if self.state.get("date") != today:
                self.state = {"date": today, "trades_sent": 0, "failures": 0}
                self._save_state()
            self._tick()
            if not self.loop:
                break


def load_demo_config(path: Path | None) -> Dict[str, Any]:
    path = path or (DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else SAMPLE_CONFIG_PATH)
    cfg = dict(DEFAULTS)
    if path and path.exists():
        user_cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in user_cfg.items() if v not in (None, "")})
    else:
        logging.warning("No se encontro %s; usando defaults", path)
    return cfg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emisor demo de senales para SLS Bot")
    parser.add_argument("--config", type=Path, default=None, help="Ruta opcional al JSON de configuracion")
    parser.add_argument("--once", action="store_true", help="Envia un solo batch y termina")
    parser.add_argument("--dry-run", action="store_true", help="No envia llamadas HTTP, solo loguea")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    config = load_demo_config(args.config)
    if args.dry_run:
        config["dry_run"] = True
    emitter = DemoEmitter(config=config, loop=not args.once)
    emitter.run()
