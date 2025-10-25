from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict
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

# ==== CARGA CONFIG ====
cfg = load_config()

ROOT_DEFAULT = Path(__file__).resolve().parents[2]
paths_cfg = cfg.get("paths", {}) if isinstance(cfg, dict) else {}

def _path_or_default(key: str, default: Path) -> Path:
    val = paths_cfg.get(key)
    if not val:
        return default
    try:
        return Path(val)
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


def _append_bridge_log(message: str) -> None:
    try:
        BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with BRIDGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.utcnow().isoformat()} {message}\n")
    except Exception:
        pass


def _append_pnl_entry(entry: dict) -> None:
    entry.setdefault("ts", datetime.utcnow().isoformat() + "Z")
    _append_jsonl(PNL_LOG, entry)


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


def _append_decision_log(symbol: str, side: str, sig: Signal, qty: str, order_info: dict, price_used: float | None) -> None:
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
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
    notional = balance_usdt * (risk_pct/100.0) * lev
    return notional / price_ref

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
        "active_cooldown_reason": None
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
            "active_cooldown_reason": None
        }
        _save_state(st)
        append_evento(EXCEL_DIR, {
            "FechaHora": datetime.utcnow().isoformat(),
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
        "ts": datetime.utcnow().isoformat(),
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
        "FechaHora": datetime.utcnow().isoformat(),
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

# ----- ENDPOINTS BÁSICOS -----
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

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

# ----- WEBHOOK -----
@app.post(cfg.get("server", {}).get("webhook_path", "/webhook"))
def webhook(sig: Signal):
    try:
        if sig.signal not in ("SLS_LONG_ENTRY", "SLS_SHORT_ENTRY", "SLS_EXIT", "SLS_UPDATE"):
            return {"status": "ignored", "reason": "unknown signal"}

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
            before = balance
            resp = _close_position_reduce_only(sig.symbol)
            after = bb.get_balance()
            epsilon = float(cfg.get("risk", {}).get("pnl_epsilon", 0.05))
            last_entry = float(st.get("last_entry_equity") or before)
            pnl = after - last_entry
            if pnl < -epsilon:
                st["consecutive_losses"] = int(st.get("consecutive_losses", 0)) + 1
            elif pnl > epsilon:
                st["consecutive_losses"] = 0
            _save_state(st)

            try:
                append_evento(EXCEL_DIR, {
                    "FechaHora": datetime.utcnow().isoformat(),
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

            st = _register_trade_result(st, pnl)
            _save_state(st)
            loss_cooldown_minutes = int(cfg.get("risk", {}).get("cooldown_loss_minutes", 30))
            if _loss_streak_reached(st):
                _start_cooldown("loss_streak", loss_cooldown_minutes, extra={
                    "recent_results": len(st.get("recent_results") or []),
                    "threshold": int(cfg.get("risk", {}).get("cooldown_loss_streak", 0))
                })

            return {"status": "ok", "close_resp": resp, "pnl_from_last_entry": round(pnl, 4),
                    "consecutive_losses": st.get("consecutive_losses", 0)}

        # ====== APERTURA ======
        side = sig.side or ("LONG" if "LONG" in sig.signal else "SHORT")
        symbol = sig.symbol.upper()

        price_live = bb.get_mark_price(symbol) or (60000.0 if "BTC" in symbol else 3000.0)
        qty_raw = _calc_qty_base(balance, sig.risk_pct or 1.0, sig.leverage or 10, price_live)
        qty_num, qty_str, filters = _quantize_qty(symbol, qty_raw)
        tick = filters["tick"]

        api_key = cfg["bybit"]["api_key"]
        api_secret = cfg["bybit"]["api_secret"]
        url = f"{BASE_URL}/v5/order/create"

        # helper para SL/TP válidos (>0)
        def _add_tp_sl(payload: dict):
            if sig.sl is not None and sig.sl > 0:
                payload["stopLoss"] = str(_quantize_price(sig.sl, tick))
            tp_raw = sig.tp2 if (sig.tp2 and sig.tp2 > 0) else (sig.tp1 if (sig.tp1 and sig.tp1 > 0) else None)
            if tp_raw is not None:
                payload["takeProfit"] = str(_quantize_price(tp_raw, tick))
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

        # Guardar equity en la entrada
        st["last_entry_equity"] = balance
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
            "FechaHora": datetime.utcnow().isoformat(),
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
            "FechaHora": datetime.utcnow().isoformat(),
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
    now_iso = datetime.utcnow().isoformat() + "Z"
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
    end_dt = datetime.utcnow()
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
