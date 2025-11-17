from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
import os
import secrets
import time, hmac, hashlib, json, requests
import threading, math

from .config_loader import load_config, CFG_PATH_IN_USE
from .bybit import BybitClient
from .excel_writer import (
    append_operacion, append_evento,
    compute_resumen_diario, upsert_resumen_diario
)

try:
    from cerebro import get_cerebro  # type: ignore
except Exception:
    get_cerebro = None  # type: ignore

# ==== CARGA CONFIG ====
cfg = load_config()
cerebro_cfg = cfg.get("cerebro") if isinstance(cfg, dict) else {}
CEREBRO_ENABLED = bool((cerebro_cfg or {}).get("enabled", False))
CEREBRO_DEFAULT_TF = ((cerebro_cfg or {}).get("timeframes") or ["15m"])[0]

ROOT_DEFAULT = Path(__file__).resolve().parents[2]
paths_cfg = cfg.get("paths", {}) if isinstance(cfg, dict) else {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


def utc_now_iso(z_suffix: bool = False) -> str:
    iso_value = utc_now().isoformat()
    return iso_value.replace("+00:00", "Z") if z_suffix else iso_value


def _path_or_default(key: str, default: Path) -> Path:
    val = paths_cfg.get(key)
    if not val:
        return default
    try:
        path_val = Path(os.path.expandvars(str(val))).expanduser()
        if not path_val.is_absolute():
            path_val = (ROOT_DEFAULT / path_val).resolve()
        return path_val
    except Exception:
        return default

ROOT = _path_or_default("root", ROOT_DEFAULT)
EXCEL_DIR = _path_or_default("excel_dir", ROOT / "excel")
LOGS_DIR = _path_or_default("logs_dir", ROOT / "logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DECISIONS_LOG = LOGS_DIR / "decisions.jsonl"
BRIDGE_LOG = LOGS_DIR / "bridge.log"
PNL_LOG = LOGS_DIR / "pnl.jsonl"
PNL_SYMBOLS_JSON = LOGS_DIR / "pnl_daily_symbols.json"
SCALP_TELEMETRY_LOG = LOGS_DIR / "scalp_telemetry.jsonl"
SCALP_DAILY_LOG = LOGS_DIR / "scalp_daily.jsonl"
ALERTS_LOG = LOGS_DIR / "alerts.log"

# ==== CLIENTE BYBIT (pybit) ====
bb = BybitClient(
    api_key=cfg["bybit"]["api_key"],
    api_secret=cfg["bybit"]["api_secret"],
    base_url=cfg["bybit"]["base_url"],
    account_type=cfg["bybit"].get("account_type", "UNIFIED")
)

BASE_URL = cfg["bybit"]["base_url"].rstrip("/")

# ==== FASTAPI ====
app = FastAPI(title="SLS Bot Webhook")


def _parse_origins() -> list[str]:
    env_val = os.getenv("ALLOWED_ORIGINS", "").strip()
    env_origins = [o.strip() for o in env_val.split(",") if o.strip()]
    panel_cfg = cfg.get("panel") or {}
    cfg_origins = []
    if isinstance(panel_cfg, dict):
        cfg_origins = [o for o in panel_cfg.get("allowed_origins", []) if isinstance(o, str) and o]
    origins = env_origins or cfg_origins
    if not origins:
        origins = ["http://localhost:3000"]
    return origins


ALLOWED_ORIGINS = _parse_origins()

control_cfg = cfg.get("auth") or {}
CONTROL_USER = os.getenv("CONTROL_USER") or control_cfg.get("control_user")
CONTROL_PASSWORD = os.getenv("CONTROL_PASSWORD") or control_cfg.get("control_password")
security = HTTPBasic()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_control_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    if not CONTROL_USER or not CONTROL_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CONTROL_USER y CONTROL_PASSWORD no están configurados en el backend",
        )
    user_ok = secrets.compare_digest(credentials.username, CONTROL_USER)
    pass_ok = secrets.compare_digest(credentials.password, CONTROL_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )

def _append_jsonl(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass



def _coerce_float(value, fallback=0.0):
    try:
        if value is None:
            return float(fallback)
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)

def _append_bridge_log(message: str) -> None:
    try:
        BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with BRIDGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{utc_now_naive().isoformat()} {message}\n")
    except Exception:
        pass


def _append_pnl_entry(entry: dict) -> None:
    entry.setdefault("ts", utc_now_iso(z_suffix=True))
    _append_jsonl(PNL_LOG, entry)


def _append_scalp_telemetry(entry: dict) -> None:
    entry.setdefault("ts", utc_now_iso(z_suffix=True))
    _append_jsonl(SCALP_TELEMETRY_LOG, entry)


def _needs_scalp_push(meta: dict | None, st: dict) -> bool:
    if not meta or meta.get("strategy") != "scalping_v1":
        return False
    min_trades = int(meta.get("min_trades_per_day") or 0)
    daily_target_pct = float(meta.get("daily_target_pct") or 0.0)
    trades_done = int(st.get("scalp_trades_today") or 0)
    profit_done = float(st.get("scalp_profit_today") or 0.0)
    start_eq = float(st.get("start_equity") or 0.0)
    target_profit = start_eq * (daily_target_pct / 100.0) if daily_target_pct > 0 and start_eq > 0 else None
    if target_profit is not None and profit_done >= target_profit:
        st["scalp_objective_met"] = True
    objective_met = bool(st.get("scalp_objective_met"))

    if min_trades and trades_done < min_trades:
        return True
    if target_profit is not None and not objective_met:
        return True
    return False


def _bump_scalp_entry(st: dict, forced: bool) -> None:
    st["scalp_trades_today"] = int(st.get("scalp_trades_today") or 0) + 1
    if forced:
        st["scalp_forced_entries"] = int(st.get("scalp_forced_entries") or 0) + 1
    _save_state(st)


def _bump_scalp_pnl(st: dict, pnl: float) -> None:
    st["scalp_profit_today"] = float(st.get("scalp_profit_today") or 0.0) + float(pnl)
    _save_state(st)


def _evaluate_scalp_objectives(st: dict, meta: Optional[dict]) -> None:
    if not meta or meta.get("strategy") != "scalping_v1":
        return
    target_pct = float(meta.get("daily_target_pct") or 0.0)
    if target_pct <= 0:
        return
    start_eq = float(st.get("start_equity") or 0.0)
    target_profit = start_eq * (target_pct / 100.0) if start_eq > 0 else 0.0
    if target_profit <= 0:
        return
    profit_done = float(st.get("scalp_profit_today") or 0.0)
    if profit_done >= target_profit and not st.get("scalp_objective_met"):
        st["scalp_objective_met"] = True
        _append_alert("Objetivo diario de scalping alcanzado", {
            "profit": profit_done,
            "target": target_profit,
        })
        _save_state(st)


def _append_alert(message: str, details: Optional[dict] = None) -> None:
    payload = {
        "ts": utc_now_iso(z_suffix=True),
        "message": message,
        "details": details or {},
    }
    _append_jsonl(ALERTS_LOG, payload)


def _append_scalp_daily_summary(st: dict) -> None:
    payload = {
        "date": st.get("date"),
        "trades": st.get("scalp_trades_today"),
        "forced_entries": st.get("scalp_forced_entries"),
        "profit": st.get("scalp_profit_today"),
    }
    _append_jsonl(SCALP_DAILY_LOG, payload)


def _load_symbol_pnl_cache() -> dict:
    try:
        if not PNL_SYMBOLS_JSON.exists():
            return {}
        return json.loads(PNL_SYMBOLS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_symbol_pnl_cache(payload: dict) -> None:
    try:
        PNL_SYMBOLS_JSON.parent.mkdir(parents=True, exist_ok=True)
        PNL_SYMBOLS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ----- MODELOS -----
class Confirmations(BaseModel):
    ema_trend_1h: Optional[str] = None
    rsi: Optional[float] = None
    fvg: Optional[str] = None
    order_block: Optional[str] = None
    volume_state: Optional[str] = None
    atr: Optional[float] = None

class Signal(BaseModel):
    signal: str
    symbol: str
    tf: Optional[str] = None
    timestamp: Optional[str] = None
    session: Optional[str] = None
    price: Optional[float] = None
    side: Optional[str] = None
    risk_score: Optional[float] = 1
    risk_pct: Optional[float] = 1.0
    leverage: Optional[int] = cfg["bybit"]["default_leverage"]
    size_mode: Optional[str] = "percent_equity"
    max_dd_day: Optional[float] = cfg.get("risk", {}).get("daily_max_dd_pct", 4.0)
    sl: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp1_close_pct: Optional[int] = 50
    move_sl_to_be_on_tp1: Optional[bool] = True
    post_only: Optional[bool] = True
    confirmations: Optional[Confirmations] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    dry_run: Optional[bool] = False
    strategy_meta: Optional[dict] = None


def _append_decision_log(symbol: str, side: str, sig: Signal, qty: str, order_info: dict, price_used: float | None) -> None:
    entry = {
        "ts": utc_now_iso(z_suffix=True),
        "symbol": symbol,
        "side": side,
        "confidence": float(sig.risk_score or 1),
        "risk_pct": sig.risk_pct,
        "leverage": sig.leverage,
        "tf": sig.tf,
        "session": sig.session,
        "qty": qty,
        "price": price_used,
        "order_id": order_info.get("orderId"),
    }
    _append_jsonl(DECISIONS_LOG, entry)

# ----- UTILS BÁSICAS -----
QTY_STEP = {"BTCUSDT": 0.001, "ETHUSDT": 0.01}
def _qty_step_for(symbol: str) -> float: return QTY_STEP.get(symbol.upper(), 0.001)

def _calc_qty_base(balance_usdt: float, risk_pct: float, lev: int, price_ref: float) -> float:
    if not price_ref or price_ref <= 0:
        return 0.0
    notional = balance_usdt * (risk_pct / 100.0) * lev
    return notional / price_ref


def _calc_stop_tp(symbol: str, side: str, price: float, atr: float) -> Tuple[float, float]:
    if atr <= 0:
        atr = price * 0.005  # fallback 0.5%
    sl_mult = float(cfg.get('risk', {}).get('sl_atr_multiple', 1.5))
    tp_mult = float(cfg.get('risk', {}).get('tp_atr_multiple', 2.0))
    if side == 'LONG':
        stop_loss = max(0.0, price - atr * sl_mult)
        take_profit = price + atr * tp_mult
    else:
        stop_loss = price + atr * sl_mult
        take_profit = max(0.0, price - atr * tp_mult)
    return stop_loss, take_profit


def _maybe_apply_cerebro(sig: Signal, price_live: float, st: dict) -> Optional[dict]:
    if not (CEREBRO_ENABLED and get_cerebro and sig.tf):
        return None
    try:
        cerebro = get_cerebro()
    except Exception:
        return None
    try:
        cerebro.run_cycle()
        decision = cerebro.latest_decision(sig.symbol.upper(), sig.tf or CEREBRO_DEFAULT_TF)
    except Exception:
        return None
    if not decision:
        return None
    info = {
        "action": decision.action,
        "confidence": decision.confidence,
        "risk_pct": decision.risk_pct,
        "leverage": decision.leverage,
        "stop_loss": decision.stop_loss,
        "take_profit": decision.take_profit,
        "timeframe": decision.timeframe,
        "symbol": decision.symbol,
        "metadata": decision.metadata,
    }
    if decision.action == "NO_TRADE":
        st["last_cerebro_decision"] = info
        _save_state(st)
        return {"blocked": True, "reason": "cerebro_no_trade"}

    sig.risk_pct = decision.risk_pct or sig.risk_pct
    sig.leverage = decision.leverage or sig.leverage
    sig.stop_loss = decision.stop_loss
    sig.take_profit = decision.take_profit
    st["last_cerebro_decision"] = info
    _save_state(st)
    return {"blocked": False}


def _notify_cerebro_learn(symbol: str, tf: Optional[str], pnl: float, st: dict) -> None:
    if not (CEREBRO_ENABLED and get_cerebro):
        return
    info = st.get("last_cerebro_decision")
    if not info:
        return
    try:
        cerebro = get_cerebro()
        metadata = info.get("metadata") or {}
        session_guard = metadata.get("session_guard") or {}
        features = {
            "confidence": info.get("confidence"),
            "risk_pct": info.get("risk_pct"),
            "leverage": info.get("leverage"),
            "news_sentiment": metadata.get("news_sentiment"),
            "session_guard_state": session_guard.get("state"),
            "session_guard_risk_multiplier": session_guard.get("risk_multiplier"),
            "memory_win_rate": metadata.get("memory_win_rate"),
            "ml_score": metadata.get("ml_score"),
        }
        cerebro.register_trade(
            symbol=symbol.upper(),
            timeframe=tf or info.get("timeframe") or CEREBRO_DEFAULT_TF,
            pnl=pnl,
            features=features,
            decision=info.get("action", "UNKNOWN"),
        )
    except Exception:
        pass
    st["last_cerebro_decision"] = None
    _save_state(st)

# ====== SINCRONIZACIÓN DE TIEMPO V5 ======
_TIME_OFFSET_MS = 0  # server_ms - local_ms

def _sync_server_time():
    global _TIME_OFFSET_MS
    try:
        r = requests.get(f"{BASE_URL}/v5/market/time", timeout=8)
        r.raise_for_status()
        data = r.json()
        server_ms = int(data.get("time") or int(data["result"]["timeSecond"]) * 1000)
        local_ms  = int(time.time() * 1000)
        _TIME_OFFSET_MS = server_ms - local_ms
    except Exception:
        _TIME_OFFSET_MS = 0

def _ts_ms() -> int:
    return int(time.time() * 1000 + _TIME_OFFSET_MS)

def _sign_v5(api_key: str, api_secret: str, payload_str: str, recv_window: str = "120000"):
    ts = str(_ts_ms())
    prehash = ts + api_key + recv_window + payload_str
    sign = hmac.new(api_secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    return ts, sign, recv_window

if os.getenv("SLS_SKIP_TIME_SYNC") != "1":
    _sync_server_time()

# ====== FILTROS DEL INSTRUMENTO Y NORMALIZACIÓN ======
def _decimals_from_step(step: float) -> int:
    s = f"{step:.10f}".rstrip("0")
    if "." in s:
        return len(s.split(".")[1])
    return 0

def _get_instrument_filters(symbol: str) -> Dict[str, float]:
    default_step = _qty_step_for(symbol)
    try:
        r = bb.session.get_instruments_info(category="linear", symbol=symbol)
        it = r.get("result", {}).get("list", [])[0]
        pf = it.get("priceFilter", {}) or {}
        lf = it.get("lotSizeFilter", {}) or {}
        tick = float(pf.get("tickSize") or 0.1)
        step = float(lf.get("qtyStep") or default_step)
        minq = float(lf.get("minOrderQty") or step)
        maxq = float(lf.get("maxOrderQty") or 1e9)
    except Exception:
        tick, step, minq, maxq = 0.1, default_step, default_step, 1e9
    return {"tick": tick, "step": step, "min": minq, "max": maxq, "dec": _decimals_from_step(step)}

def _floor_to(x: float, step: float) -> float:
    if step <= 0:
        return x
    return math.floor((x + 1e-12) / step) * step

def _quantize_qty(symbol: str, qty_raw: float) -> Tuple[float, str, Dict[str, float]]:
    f = _get_instrument_filters(symbol)
    step, minq, maxq, dec = f["step"], f["min"], f["max"], f["dec"]
    q = minq if qty_raw <= 0 else _floor_to(qty_raw, step)
    if q < minq: q = minq
    if q > maxq: q = maxq
    qty_str = f"{q:.{dec}f}".rstrip("0").rstrip(".") or "0"
    return q, qty_str, f

def _quantize_price(price_raw: float, tick: float) -> float:
    if price_raw is None or price_raw <= 0 or tick <= 0:
        return price_raw
    return _floor_to(price_raw, tick)

# ====== GESTIÓN TP1 + SL->BE ======
def _get_symbol_filters_simple(symbol: str) -> Tuple[float, float]:
    f = _get_instrument_filters(symbol)
    return f["tick"], f["step"]

def _create_order_signed(payload: dict) -> dict:
    api_key = cfg["bybit"]["api_key"]
    api_secret = cfg["bybit"]["api_secret"]
    url = f"{BASE_URL}/v5/order/create"
    payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    last_exc = None
    for i in range(3):
        try:
            ts, sign, recv_window = _sign_v5(api_key, api_secret, payload_str, "120000")
            headers = {
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-SIGN": sign,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN-TYPE": "2",
                "Content-Type": "application/json",
            }
            r = requests.post(url, headers=headers, data=payload_str, timeout=12)
            data = r.json()
            if data.get("retCode") == 0:
                return data
            msg = str(data).lower()
            if any(s in msg for s in ("timeout", "temporar", "try again", "service")) and i < 2:
                _sync_server_time()
                time.sleep(0.6 + i * 0.5)
                continue
            return data
        except Exception as e:
            last_exc = e
            _sync_server_time()
            time.sleep(0.6 + i * 0.5)
    raise last_exc if last_exc else RuntimeError("create order failed")

def _autopilot_tp1_and_be(symbol: str, opened_side: str,
                          close_pct: int = 50, tp1_pct: float = 1.0,
                          be_offset_bps: float = 2.0, timeout_s: int = 900):
    try:
        tick, lot = _get_symbol_filters_simple(symbol)
        t0 = time.time()
        size = 0.0
        entry = None
        while time.time() - t0 < timeout_s:
            r = bb.session.get_positions(category="linear", symbol=symbol)
            if r.get("retCode") == 0:
                for p in r.get("result", {}).get("list", []):
                    sz = float(p.get("size", "0") or "0")
                    if sz > 0:
                        size = sz
                        entry = float(p.get("avgPrice") or p.get("entryPrice") or 0.0)
                        break
            if size > 0 and entry and entry > 0:
                break
            time.sleep(1.2)
        if not (size > 0 and entry and entry > 0):
            return

        tp_qty_raw = size * (close_pct / 100.0)
        tp_qty = _floor_to(tp_qty_raw, lot)
        if tp_qty < lot:
            return

        if opened_side.upper() == "LONG":
            close_side = "Sell"
            tp_price_raw = entry * (1.0 + tp1_pct / 100.0)
            be_price_raw = entry * (1.0 + be_offset_bps / 10000.0)
        else:
            close_side = "Buy"
            tp_price_raw = entry * (1.0 - tp1_pct / 100.0)
            be_price_raw = entry * (1.0 - be_offset_bps / 10000.0)

        tp_price = _floor_to(tp_price_raw, tick)
        be_price = _floor_to(be_price_raw, tick)

        tp_payload = {
            "category": "linear",
            "symbol": symbol,
            "side": close_side,
            "orderType": "Limit",
            "qty": str(tp_qty),
            "price": str(tp_price),
            "reduceOnly": True,
            "isLeverage": 1
        }
        _create_order_signed(tp_payload)

        target_size = _floor_to(max(lot, size - tp_qty), lot)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            r = bb.session.get_positions(category="linear", symbol=symbol)
            if r.get("retCode") == 0:
                for p in r.get("result", {}).get("list", []):
                    sz = float(p.get("size", "0") or "0")
                    if sz > 0:
                        if sz <= target_size + (lot / 1000.0):
                            try:
                                bb.session.set_trading_stop(
                                    category="linear",
                                    symbol=symbol,
                                    stopLoss=str(be_price)
                                )
                            except Exception:
                                pass
                            return
            time.sleep(2.0)
    except Exception:
        return

# ====== RISK STATE (cooldown + DD intradía) ======
_STATE_FILE = LOGS_DIR / "risk_state.json"

def _now_ts() -> int:
    return int(time.time())

def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.load(open(_STATE_FILE, "r", encoding="utf-8"))
        except Exception:
            pass
    return {
        "date": _today_str(),
        "start_equity": 0.0,
        "consecutive_losses": 0,
        "cooldown_until_ts": 0,
        "last_entry_equity": None,
        "blocked_reason": None,
        "recent_results": [],
        "cooldown_history": [],
        "active_cooldown_reason": None,
        "last_cerebro_decision": None,
        "dynamic_risk": {"enabled": False},
    }

def _save_state(st: dict):
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)

def _reset_daily_if_needed():
    st = _load_state()
    if st.get("date") != _today_str() or float(st.get("start_equity") or 0.0) <= 0.0:
        start_eq = bb.get_balance()
        st = {
            "date": _today_str(),
            "start_equity": float(start_eq),
            "consecutive_losses": 0,
            "cooldown_until_ts": 0,
            "last_entry_equity": None,
            "blocked_reason": None,
            "recent_results": [],
            "cooldown_history": [],
            "active_cooldown_reason": None,
            "last_cerebro_decision": None,
            "dynamic_risk": {"enabled": False},
            "scalp_trades_today": 0,
            "scalp_profit_today": 0.0,
            "scalp_forced_entries": 0,
            "scalp_forced_loss_streak": 0,
            "scalp_open_forced": False,
            "scalp_open_strategy_meta": None,
            "scalp_objective_met": False,
        }
        _save_state(st)
        append_evento(EXCEL_DIR, {
            "FechaHora": utc_now_naive().isoformat(),
            "Tipo": "RESET_DAILY",
            "Detalle": f"Equity inicial del día: {start_eq}"
        })
    return st

def _current_drop_pct(cur_eq: float, st: dict) -> float:
    se = float(st.get("start_equity") or 0.0)
    if se <= 0:
        return 0.0
    return max(0.0, (se - float(cur_eq)) / se * 100.0)

def _enforce_dd_guard(cur_eq: float, st: dict):
    limit = float(cfg.get("risk", {}).get("daily_max_dd_pct", 4.0))
    dd_mins = int(cfg.get("risk", {}).get("dd_cooldown_minutes", 120))
    drop = _current_drop_pct(cur_eq, st)
    if drop >= limit:
        _start_cooldown("drawdown", dd_mins, extra={
            "drop_pct": drop,
            "limit_pct": limit
        })

def _is_blocked(st: dict) -> Tuple[bool, Optional[str], int]:
    now = _now_ts()
    until = int(st.get("cooldown_until_ts") or 0)
    if until > now:
        return True, (st.get("blocked_reason") or "cooldown"), until
    if st.get("blocked_reason"):
        st["blocked_reason"] = None
        st["active_cooldown_reason"] = None
        _save_state(st)
    return False, None, 0

def _append_cooldown_history(st: dict, reason: str, minutes: int, extra: Optional[dict] = None):
    hist = st.get("cooldown_history") or []
    hist.append({
        "ts": utc_now_naive().isoformat(),
        "reason": reason,
        "minutes": minutes,
        "extra": extra or {},
    })
    st["cooldown_history"] = hist[-30:]


def _start_cooldown(reason: str, minutes: int, extra: Optional[dict] = None):
    st = _load_state()
    st["cooldown_until_ts"] = _now_ts() + minutes * 60
    st["blocked_reason"] = reason
    st["active_cooldown_reason"] = reason
    _append_cooldown_history(st, reason, minutes, extra)
    _save_state(st)
    append_evento(EXCEL_DIR, {
        "FechaHora": utc_now_naive().isoformat(),
        "Tipo": "COOLDOWN",
        "Detalle": json.dumps({
            "reason": reason,
            "minutes": minutes,
            "extra": extra or {}
        }, ensure_ascii=False)
    })


def _register_trade_result(st: dict, pnl: float) -> dict:
    now = _now_ts()
    epsilon = float(cfg.get("risk", {}).get("pnl_epsilon", 0.05))
    results = st.get("recent_results") or []
    results.append({
        "ts": now,
        "pnl": pnl,
        "win": 1 if pnl > epsilon else (-1 if pnl < -epsilon else 0),
    })
    window_minutes = int(cfg.get("risk", {}).get("cooldown_loss_window_minutes", 120))
    window_seconds = max(5, window_minutes) * 60
    filtered = [r for r in results if now - int(r.get("ts", now)) <= window_seconds]
    st["recent_results"] = filtered[-50:]
    return st


def _loss_streak_reached(st: dict) -> bool:
    threshold = int(cfg.get("risk", {}).get("cooldown_loss_streak", 0))
    if threshold <= 0:
        return False
    epsilon = float(cfg.get("risk", {}).get("pnl_epsilon", 0.05))
    results = st.get("recent_results") or []
    streak = 0
    for entry in reversed(results):
        pnl = float(entry.get("pnl") or 0.0)
        if pnl < -epsilon:
            streak += 1
        elif pnl > epsilon:
            break
        else:
            continue
        if streak >= threshold:
            return True
    return False


def _dynamic_risk_multiplier(st: dict, balance: float) -> Tuple[float, dict]:
    dyn_cfg = (cfg.get("risk", {}).get("dynamic_risk") or {})
    if not dyn_cfg or not dyn_cfg.get("enabled"):
        return 1.0, {"enabled": False}
    start_eq = float(st.get("start_equity") or balance or 0.0)
    if start_eq <= 0:
        return 1.0, {"enabled": False}
    drop_pct = _current_drop_pct(balance, st)
    tiers = dyn_cfg.get("drawdown_tiers") or [
        {"drawdown": 0.0, "multiplier": 1.0},
        {"drawdown": 1.0, "multiplier": 0.8},
        {"drawdown": 2.0, "multiplier": 0.6},
        {"drawdown": 3.5, "multiplier": 0.4},
    ]
    tiers = sorted(tiers, key=lambda item: float(item.get("drawdown") or 0.0))
    multiplier = tiers[0].get("multiplier", 1.0)
    for tier in tiers:
        if drop_pct >= float(tier.get("drawdown") or 0.0):
            multiplier = float(tier.get("multiplier") or multiplier)
        else:
            break
    ceiling_pct = float(dyn_cfg.get("equity_ceiling_pct") or 0.0)
    if ceiling_pct > 0 and balance >= start_eq * (1 + ceiling_pct / 100.0):
        multiplier = max(multiplier, float(dyn_cfg.get("multiplier_above_ceiling") or multiplier))
    multiplier = min(float(dyn_cfg.get("max_multiplier") or 1.5), multiplier)
    multiplier = max(float(dyn_cfg.get("min_multiplier") or 0.2), multiplier)
    return multiplier, {
        "enabled": True,
        "drawdown_pct": drop_pct,
        "start_equity": start_eq,
        "current_equity": balance,
    }


def _apply_dynamic_risk(sig: Signal, balance: float, st: dict) -> None:
    mult, meta = _dynamic_risk_multiplier(st, balance)
    if not meta.get("enabled"):
        st["dynamic_risk"] = {"enabled": False}
        return
    base = float(sig.risk_pct or 1.0)
    adjusted = max(0.05, base * mult)
    sig.risk_pct = adjusted
    st["dynamic_risk"] = {
        "enabled": True,
        "multiplier": mult,
        "base_risk_pct": base,
        "adjusted_risk_pct": adjusted,
        "drawdown_pct": meta.get("drawdown_pct"),
        "start_equity": meta.get("start_equity"),
        "current_equity": meta.get("current_equity"),
        "applied_ts": _now_ts(),
    }


def _apply_guardrails(sig: Signal, price_live: float, st: dict) -> dict | None:
    guard_cfg = (cfg.get("risk", {}).get("guardrails") or {})
    if not guard_cfg:
        return None
    symbol = sig.symbol.upper()
    guard_state = {"hits": []}
    st_hits = st.setdefault("guardrail_hits", [])

    def _record(hit: dict) -> None:
        hit["ts"] = _now_ts()
        st_hits.append(hit)
        guard_state["hits"].append(hit)

    max_global = float(guard_cfg.get("max_risk_pct") or 0)
    if max_global and sig.risk_pct and sig.risk_pct > max_global:
        sig.risk_pct = max_global
        _record({"type": "cap_global_risk", "value": max_global})

    per_symbol = (guard_cfg.get("per_symbol") or {}).get(symbol, {})
    max_symbol_risk = per_symbol.get("max_risk_pct")
    if max_symbol_risk and sig.risk_pct and sig.risk_pct > max_symbol_risk:
        sig.risk_pct = max_symbol_risk
        _record({"type": "cap_symbol_risk", "symbol": symbol, "value": max_symbol_risk})
    max_symbol_lev = per_symbol.get("max_leverage")
    if max_symbol_lev and sig.leverage and sig.leverage > max_symbol_lev:
        sig.leverage = max_symbol_lev
        _record({"type": "cap_symbol_leverage", "symbol": symbol, "value": max_symbol_lev})

    min_conf = float(guard_cfg.get("min_confidence") or 0)
    confidence = float(sig.risk_score or 0)
    if min_conf and confidence < min_conf:
        hit = {"type": "block_confidence", "required": min_conf, "value": confidence}
        _record(hit)
        return {"blocked": True, "reason": "guardrails.confidence", "details": hit}

    vol_cfg = guard_cfg.get("volatility") or {}
    atr = getattr(getattr(sig, "confirmations", None) or object(), "atr", None)
    max_atr_pct = float(vol_cfg.get("max_atr_pct") or 0)
    if max_atr_pct and atr and price_live:
        atr_pct = (atr / price_live) * 100
        if atr_pct > max_atr_pct:
            hit = {"type": "block_volatility", "atr_pct": round(atr_pct, 3), "max_atr_pct": max_atr_pct}
            _record(hit)
            return {"blocked": True, "reason": "guardrails.volatility", "details": hit}

    if guard_state["hits"]:
        return guard_state
    return None

# ----- ENDPOINTS BÁSICOS -----
@app.get("/health")
def health():
    return {"ok": True, "time": utc_now_naive().isoformat()}

@app.get("/whoami")
def whoami():
    ak = (cfg["bybit"].get("api_key") or "")
    masked = f"{ak[:4]}...{ak[-4:]}" if ak else None
    return {
        "config_path": CFG_PATH_IN_USE,
        "env": cfg.get("env"),
        "base_url": cfg["bybit"]["base_url"],
        "api_key_masked": masked
    }

@app.get("/diag")
def diag():
    try:
        bal = bb.get_balance()
        return {"ok": True, "saldo_usdt": bal}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/risk")
def risk_state():
    st = _reset_daily_if_needed()
    cur = bb.get_balance()
    drop = _current_drop_pct(cur, st)
    blocked, reason, until = _is_blocked(st)
    remain = max(0, until - _now_ts()) if blocked else 0
    return {
        "date": st.get("date"),
        "start_equity": st.get("start_equity"),
        "current_equity": cur,
        "dd_drop_pct": round(drop, 4),
        "consecutive_losses": st.get("consecutive_losses", 0),
        "blocked": blocked,
        "blocked_reason": reason,
        "cooldown_until_ts": until,
        "cooldown_remaining_s": remain,
        "limits": {
            "daily_max_dd_pct": cfg.get("risk", {}).get("daily_max_dd_pct"),
            "cooldown_after_losses": cfg.get("risk", {}).get("cooldown_after_losses"),
            "cooldown_minutes": cfg.get("risk", {}).get("cooldown_minutes"),
            "dd_cooldown_minutes": cfg.get("risk", {}).get("dd_cooldown_minutes")
        }
    }

# ---- DEBUG qty ----
@app.get("/debug/qty")
def debug_qty(symbol: str = Query(...), risk: float = 1.0, lev: int = 10):
    bal = bb.get_balance()
    price = bb.get_mark_price(symbol) or (60000.0 if "BTC" in symbol.upper() else 3000.0)
    raw = _calc_qty_base(bal, risk, lev, price)
    qnum, qstr, f = _quantize_qty(symbol, raw)
    return {"symbol": symbol.upper(), "balance": bal, "price_ref": price,
            "risk_pct": risk, "leverage": lev, "raw_qty": raw,
            "normalized_qty_num": qnum, "normalized_qty_str": qstr, "filters": f}

# ====== CIERRE reduceOnly (SLS_EXIT) ======
def _close_position_reduce_only(symbol: str):
    try:
        r = bb.session.get_positions(category="linear", symbol=symbol)
        if r.get("retCode") != 0:
            return {"error": r}

        size = 0.0
        opened_side = None
        for p in r.get("result", {}).get("list", []):
            sz = float(p.get("size", "0") or "0")
            if sz > 0:
                size = sz
                opened_side = "LONG" if p.get("side") == "Buy" else "SHORT"
                break

        if size <= 0 or not opened_side:
            return {"note": "no open position"}

        side_close = "Sell" if opened_side == "LONG" else "Buy"
        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": side_close,
            "orderType": "Market",
            "qty": str(size),
            "reduceOnly": True,
            "isLeverage": 1
        }

        payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        ts, sign, recv = _sign_v5(cfg["bybit"]["api_key"], cfg["bybit"]["api_secret"], payload_str, "120000")
        headers = {
            "X-BAPI-API-KEY": cfg["bybit"]["api_key"],
            "X-BAPI-SIGN": sign,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json",
        }
        cr = requests.post(f"{BASE_URL}/v5/order/create", headers=headers, data=payload_str, timeout=10).json()
        return cr
    except Exception as e:
        return {"error": str(e)}


class ScalpPositionManager:
    def __init__(self):
        self._positions: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def register(self, *, symbol: str, side: str, ttl_minutes: float, expected_price: float,
                 latency_ms: float, strategy_meta: dict) -> None:
        entry = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "start_ts": time.time(),
            "ttl_s": max(60.0, float(ttl_minutes) * 60.0),
            "expected_price": float(expected_price),
            "latency_ms": latency_ms,
            "strategy_meta": strategy_meta,
        }
        with self._lock:
            self._positions[entry["symbol"]] = entry
        self._ensure_loop()
        threading.Thread(target=self._capture_fill_snapshot, args=(entry,), daemon=True).start()

    def _ensure_loop(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                time.sleep(5)
                now = time.time()
                targets: list[dict] = []
                with self._lock:
                    for symbol, entry in list(self._positions.items()):
                        pos = self._fetch_position(symbol)
                        if not pos or pos.get("size", 0.0) <= 0:
                            self._positions.pop(symbol, None)
                            continue
                        if now - entry["start_ts"] >= entry["ttl_s"]:
                            targets.append(entry)
                            self._positions.pop(symbol, None)
                for entry in targets:
                    resp = _close_position_reduce_only(entry["symbol"])
                    _append_bridge_log(
                        f"scalp_guard ttl_close symbol={entry['symbol']} ttl_s={entry['ttl_s']:.0f} resp={resp}"
                    )
                    telemetry = {
                        "symbol": entry["symbol"],
                        "side": entry["side"],
                        "reason": "ttl_expired",
                        "max_hold_minutes": entry["ttl_s"] / 60.0,
                        "strategy": entry["strategy_meta"].get("strategy"),
                        "forced_entry": entry["strategy_meta"].get("forced_entry"),
                        "telemetry": resp,
                    }
                    _append_scalp_telemetry(telemetry)

        self._thread = threading.Thread(target=_loop, daemon=True, name="scalp-ttl-guard")
        self._thread.start()

    def _fetch_position(self, symbol: str) -> Optional[dict]:
        try:
            resp = bb.session.get_positions(category="linear", symbol=symbol)
            if resp.get("retCode") != 0:
                return None
            for row in resp.get("result", {}).get("list", []):
                size = float(row.get("size") or 0)
                if size > 0:
                    return {"size": size, "avg_price": float(row.get("avgPrice") or 0.0)}
        except Exception:
            return None
        return None

    def _capture_fill_snapshot(self, entry: dict) -> None:
        time.sleep(4)
        pos = self._fetch_position(entry["symbol"])
        if not pos or pos.get("avg_price", 0) <= 0:
            return
        avg_price = pos["avg_price"]
        expected = entry["expected_price"] or avg_price
        slippage_bps = ((avg_price - expected) / expected) * 10000 if expected else 0.0
        telemetry = {
            "symbol": entry["symbol"],
            "side": entry["side"],
            "expected_price": expected,
            "fill_price": avg_price,
            "slippage_bps": round(slippage_bps, 3),
            "latency_ms": round(entry.get("latency_ms", 0.0), 2),
            "strategy": entry["strategy_meta"].get("strategy"),
            "forced_entry": entry["strategy_meta"].get("forced_entry"),
            "max_hold_minutes": entry["ttl_s"] / 60.0,
        }
        _append_scalp_telemetry(telemetry)


_SCALP_MANAGER = ScalpPositionManager()

# ----- WEBHOOK -----
@app.post(cfg.get("server", {}).get("webhook_path", "/webhook"))
def webhook(sig: Signal):
    try:
        if sig.signal not in ("SLS_LONG_ENTRY", "SLS_SHORT_ENTRY", "SLS_EXIT", "SLS_UPDATE"):
            return {"status": "ignored", "reason": "unknown signal"}
        if sig.dry_run:
            action = "exit" if sig.signal == "SLS_EXIT" else sig.signal
            return {"status": "dry_run", "action": action}

        # ====== RESET DIARIO & GUARDAS ======
        st = _reset_daily_if_needed()
        balance = bb.get_balance()
        _enforce_dd_guard(balance, st)
        st = _load_state()

        # Bloqueos previos a operar
        blocked, reason, until = _is_blocked(st)
        if sig.signal in ("SLS_LONG_ENTRY", "SLS_SHORT_ENTRY") and blocked:
            return {
                "status": "blocked",
                "reason": reason,
                "cooldown_until_ts": until,
                "cooldown_remaining_s": max(0, until - _now_ts())
            }

        # ====== CIERRE ======
        if sig.signal == "SLS_EXIT":
            if sig.dry_run:
                return {"status": "dry_run", "action": "exit"}
            before = _coerce_float(balance, 0.0)
            resp = _close_position_reduce_only(sig.symbol)
            after_raw = bb.get_balance()
            after = _coerce_float(after_raw, before)
            epsilon = float(cfg.get("risk", {}).get("pnl_epsilon", 0.05))
            last_entry = _coerce_float(st.get("last_entry_equity"), before)
            pnl = after - last_entry
            if pnl < -epsilon:
                st["consecutive_losses"] = int(st.get("consecutive_losses", 0)) + 1
            elif pnl > epsilon:
                st["consecutive_losses"] = 0
            _save_state(st)

            try:
                append_evento(EXCEL_DIR, {
                    "FechaHora": utc_now_naive().isoformat(),
                    "Tipo": "CLOSE",
                    "Detalle": json.dumps({
                        "symbol": sig.symbol.upper(),
                        "tf": sig.tf,
                        "before": last_entry,
                        "after": after,
                        "pnl": pnl
                    }, ensure_ascii=False)
                })
            except Exception:
                pass

            _append_pnl_entry({
                "type": "close",
                "symbol": sig.symbol.upper(),
                "tf": sig.tf,
                "pnl": pnl,
                "before": last_entry,
                "after": after,
            })
            _append_bridge_log(f"close {sig.symbol.upper()} pnl={pnl:.4f} after={after}")

            nloss = int(cfg.get("risk", {}).get("cooldown_after_losses", 2))
            mins  = int(cfg.get("risk", {}).get("cooldown_minutes", 60))
            if st["consecutive_losses"] >= nloss:
                _start_cooldown("losses", mins)

        forced_open = bool(st.get("scalp_open_forced"))
        open_meta = st.get("scalp_open_strategy_meta") or {}
        st["scalp_open_forced"] = False
        st["scalp_open_strategy_meta"] = None
        st = _register_trade_result(st, pnl)
        _bump_scalp_pnl(st, pnl)
        _evaluate_scalp_objectives(st, open_meta)
        if forced_open:
            limit = int(open_meta.get("forced_loss_backoff") or 0)
            backoff_minutes = int(open_meta.get("forced_backoff_minutes") or 30)
            if pnl < -epsilon:
                st["scalp_forced_loss_streak"] = int(st.get("scalp_forced_loss_streak") or 0) + 1
            else:
                st["scalp_forced_loss_streak"] = 0
            if limit and st.get("scalp_forced_loss_streak", 0) >= limit:
                _append_alert("Activando backoff por pérdidas forzadas", {
                    "streak": st.get("scalp_forced_loss_streak"),
                    "limit": limit,
                    "minutes": backoff_minutes,
                })
                _save_state(st)
                _start_cooldown("scalp_forced_losses", backoff_minutes, extra={"streak": st.get("scalp_forced_loss_streak")})
                st = _load_state()
                st["scalp_forced_loss_streak"] = 0
        else:
            st["scalp_forced_loss_streak"] = 0
        _save_state(st)
        loss_cooldown_minutes = int(cfg.get("risk", {}).get("cooldown_loss_minutes", 30))
        if _loss_streak_reached(st):
            _start_cooldown("loss_streak", loss_cooldown_minutes, extra={
                "recent_results": len(st.get("recent_results") or []),
                "threshold": int(cfg.get("risk", {}).get("cooldown_loss_streak", 0))
            })
        _notify_cerebro_learn(sig.symbol, sig.tf, pnl, st)

        return {"status": "ok", "close_resp": resp, "pnl_from_last_entry": round(pnl, 4),
                "consecutive_losses": st.get("consecutive_losses", 0)}

        # ====== APERTURA ======
        side = sig.side or ("LONG" if "LONG" in sig.signal else "SHORT")
        symbol = sig.symbol.upper()
        if not sig.tf:
            sig.tf = CEREBRO_DEFAULT_TF

        strategy_meta = sig.strategy_meta or {}
        force_scalp = False
        if strategy_meta.get("strategy") == "scalping_v1" and not strategy_meta.get("forced_entry"):
            if _needs_scalp_push(strategy_meta, st):
                force_scalp = True
                strategy_meta["forced_entry"] = True
                strategy_meta["force_reason"] = "daily_objective"
                sig.strategy_meta = strategy_meta
                _append_alert("Scalping forzado por objetivos diarios", {
                    "symbol": symbol,
                    "trades_done": st.get("scalp_trades_today"),
                    "profit": st.get("scalp_profit_today"),
                })

        price_live = bb.get_mark_price(symbol) or (60000.0 if "BTC" in symbol else 3000.0)
        cere_decision = None if force_scalp else _maybe_apply_cerebro(sig, price_live, st)
        if cere_decision and cere_decision.get("blocked"):
            return {"status": "filtered", "reason": cere_decision.get("reason", "cerebro")}
        _apply_dynamic_risk(sig, balance, st)
        guardrail = _apply_guardrails(sig, price_live, st)
        if guardrail and guardrail.get("blocked") and not force_scalp:
            _save_state(st)
            return {"status": "filtered", "reason": guardrail.get("reason", "guardrails"), "details": guardrail}
        if guardrail and guardrail.get("blocked") and force_scalp:
            _append_bridge_log(f"scalp_guard overridden symbol={symbol} reason={guardrail.get('reason')}")
        if force_scalp:
            min_risk = float(strategy_meta.get("min_risk_pct") or 0.25)
            sig.risk_pct = max(float(sig.risk_pct or min_risk), min_risk)
        _save_state(st)
        qty_raw = _calc_qty_base(balance, sig.risk_pct or 1.0, sig.leverage or 10, price_live)
        qty_num, qty_str, filters = _quantize_qty(symbol, qty_raw)
        tick = filters["tick"]

        api_key = cfg["bybit"]["api_key"]
        api_secret = cfg["bybit"]["api_secret"]
        url = f"{BASE_URL}/v5/order/create"

        # helper para SL/TP válidos (>0)
        def _add_tp_sl(payload: dict):
            sl_value = sig.stop_loss if (sig.stop_loss and sig.stop_loss > 0) else sig.sl
            if sl_value is not None and sl_value > 0:
                payload["stopLoss"] = str(_quantize_price(sl_value, tick))
            tp_value = sig.take_profit if (sig.take_profit and sig.take_profit > 0) else None
            if tp_value is None:
                tp_value = sig.tp2 if (sig.tp2 and sig.tp2 > 0) else (sig.tp1 if (sig.tp1 and sig.tp1 > 0) else None)
            if tp_value is not None:
                payload["takeProfit"] = str(_quantize_price(tp_value, tick))
                payload["tpSlMode"]   = "Full"

        # LIMIT vs MARKET
        if sig.post_only and sig.price:
            price_ref = _quantize_price(sig.price, tick)
            payload = {
                "category": "linear",
                "symbol": symbol,
                "side": "Buy" if side == "LONG" else "Sell",
                "orderType": "Limit",
                "qty": qty_str,
                "price": str(price_ref),
                "timeInForce": "PostOnly",
                "isLeverage": 1
            }
            _add_tp_sl(payload)
        else:
            payload = {
                "category": "linear",
                "symbol": symbol,
                "side": "Buy" if side == "LONG" else "Sell",
                "orderType": "Market",
                "qty": qty_str,
                "isLeverage": 1
            }
            _add_tp_sl(payload)

        # leverage tolerante
        try:
            bb.set_leverage(symbol, sig.leverage or 10, sig.leverage or 10)
        except Exception:
            pass

        # ---- Crear orden con reintentos + fallback Market→Limit IOC ----
        payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        order_started = time.time()
        last_exc = None
        placed = None
        for i in range(4):
            try:
                ts, sign, recv_window = _sign_v5(api_key, api_secret, payload_str, "120000")
                headers = {
                    "X-BAPI-API-KEY": api_key,
                    "X-BAPI-SIGN": sign,
                    "X-BAPI-TIMESTAMP": ts,
                    "X-BAPI-RECV-WINDOW": recv_window,
                    "X-BAPI-SIGN-TYPE": "2",
                    "Content-Type": "application/json",
                }
                r = requests.post(url, headers=headers, data=payload_str, timeout=15)
                data = r.json()
                if data.get("retCode") == 0:
                    placed = data["result"]
                    break

                msg = str(data).lower()
                # Fallback para "maximum buying/minimum selling price" (ej. 30228)
                if payload.get("orderType") == "Market" and (
                    "maximum buying price" in msg or "minimum selling price" in msg or "30228" in msg
                ):
                    # Reintento como Limit IOC cerca del mark
                    mark = bb.get_mark_price(symbol) or price_live
                    if (side.upper() == "LONG"):
                        px = _quantize_price(mark * 1.001, tick)
                    else:
                        px = _quantize_price(mark * 0.999, tick)
                    payload_limit = dict(payload)
                    payload_limit["orderType"] = "Limit"
                    payload_limit["timeInForce"] = "IOC"
                    payload_limit["price"] = str(px)
                    payload_str = json.dumps(payload_limit, separators=(",", ":"), ensure_ascii=False)
                    # no incrementamos i aquí; dejamos que el bucle lo reintente
                    continue

                if any(s in msg for s in ("timeout", "temporar", "try again", "service")) and i < 3:
                    _sync_server_time()
                    time.sleep(0.6 + i * 0.6)
                    continue

                raise RuntimeError(data)
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                if any(s in msg for s in ("timeout", "temporar", "try again", "service")) and i < 3:
                    _sync_server_time()
                    time.sleep(0.6 + i * 0.6)
                    continue
                raise
        else:
            raise last_exc
        latency_ms = (time.time() - order_started) * 1000.0

        # Guardar equity en la entrada
        st["last_entry_equity"] = balance
        st["scalp_open_forced"] = bool(strategy_meta.get("forced_entry"))
        st["scalp_open_strategy_meta"] = strategy_meta if strategy_meta else None
        _save_state(st)

        # TP1 parcial + SL->BE
        if sig.move_sl_to_be_on_tp1 and (sig.tp1_close_pct or 50) > 0:
            threading.Thread(
                target=_autopilot_tp1_and_be,
                args=(symbol, side),
                kwargs={"close_pct": int(sig.tp1_close_pct or 50), "tp1_pct": 1.0, "be_offset_bps": 2.0},
                daemon=True
            ).start()

        # Log / Excel / Panel
        append_operacion(EXCEL_DIR, {
            "FechaHora": utc_now_naive().isoformat(),
            "Sesion": sig.session or "",
            "Simbolo": symbol,
            "TF": sig.tf or "",
            "Tipo": side,
            "Riesgo(%)": sig.risk_pct or 1.0,
            "Leverage": sig.leverage or 10,
            "Modo Tamano": "percent_equity",
            "Capital abrir(EUR)": 0,
            "Nocional(USDT)": round((sig.risk_pct or 1.0)/100 * balance * (sig.leverage or 10), 2),
            "Precio entrada": sig.price or 0,
            "SL": sig.sl or 0,
            "TP1": sig.tp1 or 0,
            "TP2": sig.tp2 or 0,
            "%cerrado TP1": sig.tp1_close_pct or 0,
            "RiskScore": sig.risk_score or 1,
            "Confirmaciones": str(sig.confirmations.dict() if sig.confirmations else {}),
            "Comentario": f"orderId={placed.get('orderId','')} qty={qty_str}"
        })
        _append_decision_log(symbol, side, sig, qty_str, placed or {}, sig.price or price_live)
        if strategy_meta.get("strategy") == "scalping_v1":
            st_scalp = _load_state()
            _bump_scalp_entry(st_scalp, bool(strategy_meta.get("forced_entry")))
            _save_state(st_scalp)
        strategy_meta = sig.strategy_meta or {}
        if strategy_meta.get("strategy") == "scalping_v1":
            hold_minutes = float(strategy_meta.get("max_hold_minutes") or 45)
            expected_price = float(payload.get("price") or price_live)
            try:
                _SCALP_MANAGER.register(
                    symbol=symbol,
                    side=side,
                    ttl_minutes=hold_minutes,
                    expected_price=expected_price,
                    latency_ms=latency_ms,
                    strategy_meta=strategy_meta,
                )
            except Exception:
                pass
        _append_bridge_log(f"order {side} {symbol} qty={qty_str} price={sig.price or price_live}")

        return {
            "status": "ok",
            "placed": placed,
            "qty": qty_str,
            "order_type": placed.get("orderType", payload.get("orderType")),
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

# ====== RESUMEN DIARIO ======
@app.get("/daily/summary")
def daily_summary(date: Optional[str] = None, write: bool = True):
    if not date:
        date = _today_str()
    start_eq = None
    end_eq = None
    if date == _today_str():
        st = _reset_daily_if_needed()
        start_eq = float(st.get("start_equity") or 0.0)
        end_eq = bb.get_balance()
    eps = float(cfg.get("risk", {}).get("pnl_epsilon", 0.05))
    resumen = compute_resumen_diario(EXCEL_DIR, date, start_eq, end_eq, eps)
    if write:
        upsert_resumen_diario(EXCEL_DIR, resumen)
        append_evento(EXCEL_DIR, {
            "FechaHora": utc_now_naive().isoformat(),
            "Tipo": "RESUMEN_AUTOMATICO" if date == _today_str() else "RESUMEN_REBUILD",
            "Detalle": json.dumps(resumen, ensure_ascii=False)
        })
        try:
            pnl_eur = float(resumen.get("PnL €") or resumen.get("PnL �'�") or 0.0)
        except Exception:
            pnl_eur = 0.0
        _append_pnl_entry({
            "type": "daily",
            "day": date,
            "pnl_eur": pnl_eur,
            "pnl_pct": resumen.get("PnL %"),
            "start": resumen.get("Start Equity"),
            "end": resumen.get("End Equity"),
            "trades": resumen.get("Trades"),
        })
        _append_scalp_daily_summary(_load_state())
    return {"status": "ok", "summary": resumen}

def _daily_scheduler():
    while True:
        now = datetime.now()
        target = now.replace(hour=23, minute=59, second=45, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        time.sleep((target - now).total_seconds())
        try:
            daily_summary(write=True)
            _append_scalp_daily_summary(_load_state())
        except Exception:
            pass

try:
    threading.Thread(target=_daily_scheduler, daemon=True).start()
except Exception:
    pass


def _collect_closed_pnl_entries(start_ms: int, end_ms: int) -> list[dict]:
    """Descarga el histórico de closed PnL de Bybit entre start/end usando paginación."""
    rows: list[dict] = []
    cursor: str | None = None
    for _ in range(30):  # evita bucles infinitos
        resp = bb.get_closed_pnl(start_time=start_ms, end_time=end_ms, cursor=cursor, limit=200)
        if resp.get("retCode") != 0:
            break
        result = resp.get("result") or {}
        batch = result.get("list") or []
        rows.extend(batch)
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return rows


def _aggregate_closed_pnl(entries: list[dict]) -> dict[str, dict]:
    """Agrupa por día y símbolo para generar breakdown real a partir de fills."""
    aggregated: dict[str, dict] = {}
    now_iso = utc_now_iso(z_suffix=True)
    for entry in entries:
        ts_raw = entry.get("createdTime") or entry.get("updatedTime") or entry.get("execTime")
        symbol = entry.get("symbol")
        if not ts_raw or not symbol:
            continue
        try:
            ts_ms = int(ts_raw)
        except Exception:
            continue
        day = datetime.utcfromtimestamp(ts_ms / 1000).date().isoformat()
        pnl_val = entry.get("closedPnl") or entry.get("pnl") or 0.0
        fees_val = entry.get("cumCommission") or entry.get("fees") or 0.0
        try:
            pnl = float(pnl_val)
        except Exception:
            pnl = 0.0
        try:
            fees = float(fees_val)
        except Exception:
            fees = 0.0
        ref = aggregated.setdefault(day, {"total": 0.0, "symbols": {}, "refreshed_at": now_iso})
        ref["total"] += pnl
        sym = ref["symbols"].setdefault(symbol, {"pnl": 0.0, "fees": 0.0, "trades": 0})
        sym["pnl"] += pnl
        sym["fees"] += fees
        sym["trades"] += 1
    return aggregated


def _sync_symbol_pnl(days_back: int = 30) -> None:
    """Reconstruye los últimos `days_back` días con datos reales de Bybit."""
    end_dt = utc_now()
    start_dt = end_dt - timedelta(days=days_back)
    entries = _collect_closed_pnl_entries(
        int(start_dt.timestamp() * 1000),
        int(end_dt.timestamp() * 1000),
    )
    aggregated = _aggregate_closed_pnl(entries)
    if not aggregated:
        return
    cache = _load_symbol_pnl_cache()
    cache.update(aggregated)
    # conserva solo los últimos 90 días para evitar archivos gigantes
    keys = sorted(cache.keys())
    if len(keys) > 90:
        for day in keys[:-90]:
            cache.pop(day, None)
    _save_symbol_pnl_cache(cache)


def _pnl_symbol_worker():
    interval = max(600, int(os.getenv("PNL_SYMBOL_SYNC_SECONDS", "1800")))
    while True:
        try:
            _sync_symbol_pnl()
        except Exception as exc:
            _append_bridge_log(f"pnl_sync_error={exc}")
        time.sleep(interval)


try:
    threading.Thread(target=_pnl_symbol_worker, daemon=True).start()
except Exception:
    pass


def _bridge_heartbeat():
    interval = max(5, int(os.getenv("BRIDGE_HEARTBEAT_SEC", "10")))
    while True:
        try:
            balance = bb.get_balance()
        except Exception:
            balance = None
        st = _load_state()
        cooldown = st.get("cooldown_until_ts")
        cooldown_left = max(0, (cooldown or 0) - _now_ts()) if cooldown else 0
        _append_bridge_log(f"heartbeat balance={balance} cooldown_s={cooldown_left}")
        time.sleep(interval)


try:
    threading.Thread(target=_bridge_heartbeat, daemon=True).start()
except Exception:
    pass
