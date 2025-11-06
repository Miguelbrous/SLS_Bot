import json
import os
import secrets
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Literal
import copy

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Gauge, REGISTRY

from .alerts import collect_alerts
from .models import (
    AlertsResponse,
    AlertItem,
    DecisionsResponse,
    Health,
    LogResponse,
    PnLDailyItem,
    PnLDailyResponse,
    ServiceState,
    StatusResponse,
    SymbolPnL,
    DashboardSummaryResponse,
    DashboardMetric,
    DashboardIssue,
    DashboardTrade,
    DashboardChartResponse,
    DashboardCandle,
    DashboardTradeMarker,
    ArenaNote,
    ArenaNotesResponse,
    ArenaNotePayload,
    ObservabilitySummary,
    ObservabilityArena,
    ObservabilityBot,
    ObservabilityCerebro,
)
from .services import service_action, service_status
from .utils import tail_lines

try:
    from sls_bot.config_loader import load_config, CFG_PATH_IN_USE  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    load_config = None  # type: ignore
    CFG_PATH_IN_USE = None  # type: ignore

APP_DIR = Path(__file__).resolve().parent
BOT_DIR = APP_DIR.parent
PROJECT_ROOT = BOT_DIR.parent
_JSON_CACHE: Dict[str, tuple[float, Any]] = {}

CONTROL_USER = os.getenv("CONTROL_USER")
CONTROL_PASSWORD = os.getenv("CONTROL_PASSWORD")
PANEL_API_TOKENS_RAW = ",".join(
    filter(
        None,
        [
            os.getenv("PANEL_API_TOKENS"),
            os.getenv("PANEL_API_TOKEN"),
        ],
    )
)
TRUST_PROXY_BASIC = os.getenv("TRUST_PROXY_BASIC", "0").lower() in {"1", "true", "yes"}
PROXY_BASIC_HEADER = os.getenv("PROXY_BASIC_HEADER", "x-forwarded-user")
security = HTTPBasic(auto_error=False)


def _parse_origins() -> List[str]:
    env_val = os.getenv("ALLOWED_ORIGINS", "").strip()
    env_origins = [o.strip() for o in env_val.split(",") if o.strip()]
    if env_origins:
        return env_origins
    return ["http://localhost:3000"]


ALLOWED_ORIGINS = _parse_origins()
if load_config:
    try:
        BOT_CONFIG = load_config()
    except Exception:
        BOT_CONFIG = {}
else:
    BOT_CONFIG = {}


def _resolve_path(value: Any, default: Path) -> Path:
    if not value:
        return default
    try:
        candidate = Path(os.path.expandvars(str(value))).expanduser()
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        return candidate
    except Exception:
        return default


PATHS_CFG = BOT_CONFIG.get("paths") if isinstance(BOT_CONFIG, dict) else {}
if not isinstance(PATHS_CFG, dict):
    PATHS_CFG = {}
LOGS_DIR = _resolve_path(PATHS_CFG.get("logs_dir"), PROJECT_ROOT / "logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BRIDGE_LOG = Path(os.getenv("BRIDGE_LOG", LOGS_DIR / "bridge.log"))
DECISIONS_LOG = Path(os.getenv("DECISIONS_LOG", LOGS_DIR / "decisions.jsonl"))
PNL_LOG = Path(os.getenv("PNL_LOG", LOGS_DIR / "pnl.jsonl"))
PNL_SYMBOLS_JSON = Path(os.getenv("PNL_SYMBOLS_JSON", LOGS_DIR / "pnl_daily_symbols.json"))
CEREBRO_DECISIONS_LOG = Path(os.getenv("CEREBRO_DECISIONS_LOG", LOGS_DIR / "cerebro_decisions.jsonl"))
LOGS_ROOT = LOGS_DIR.parent
ARENA_DIR = PROJECT_ROOT / "bot" / "arena"
ARENA_RANKING = Path(os.getenv("ARENA_RANKING_PATH", ARENA_DIR / "ranking_latest.json"))
ARENA_STATE = Path(os.getenv("ARENA_STATE_PATH", ARENA_DIR / "cup_state.json"))
ARENA_DB = Path(os.getenv("ARENA_DB_PATH", ARENA_DIR / "arena.db"))

app = FastAPI(title="SLS Bot API", version="1.0.0")
Instrumentator().instrument(app).expose(app, include_in_schema=False)

def _get_or_create_gauge(name: str, description: str) -> Gauge:
    names_map = getattr(REGISTRY, "_names_to_collectors", None)
    if isinstance(names_map, dict) and name in names_map:
        existing = names_map[name]
        if isinstance(existing, Gauge):
            return existing
    return Gauge(name, description)


def _bind_gauge_function(gauge: Gauge, func) -> None:
    if getattr(gauge, "_sls_fn_bound", False):
        return
    try:
        gauge.set_function(func)
    except ValueError:
        return
    gauge._sls_fn_bound = True  # type: ignore[attr-defined]


ARENA_GOAL_GAUGE = _get_or_create_gauge("sls_arena_current_goal_eur", "Meta activa en la arena (EUR)")
ARENA_WINS_GAUGE = _get_or_create_gauge("sls_arena_total_wins", "Victorias acumuladas en la arena")
ARENA_STATE_AGE_GAUGE = _get_or_create_gauge(
    "sls_arena_state_age_seconds", "Segundos desde el último tick registrado"
)
ARENA_DRAWDOWN_GAUGE = _get_or_create_gauge("sls_arena_goal_drawdown_pct", "Drawdown vs meta de la arena (%)")
ARENA_TICKS_SINCE_WIN_GAUGE = _get_or_create_gauge(
    "sls_arena_ticks_since_win", "Ticks desde la última promoción"
)
BOT_DRAWDOWN_GAUGE = _get_or_create_gauge("sls_bot_drawdown_pct", "Drawdown actual del bot (%)")
CEREBRO_DECISIONS_RATE_GAUGE = _get_or_create_gauge(
    "sls_cerebro_decisions_per_min", "Decisiones validadas por minuto (últimos 15m)"
)

try:
    from cerebro.router import cerebro_router  # type: ignore

    app.include_router(cerebro_router)
except Exception:
    pass


def _parse_rotating_tokens(raw: str) -> List[Tuple[str, date | None]]:
    tokens: List[Tuple[str, date | None]] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "@" in chunk:
            token_val, exp_val = chunk.split("@", 1)
            token_val = token_val.strip()
            exp_val = exp_val.strip()
            if not token_val:
                continue
            try:
                expires = datetime.strptime(exp_val, "%Y-%m-%d").date()
            except Exception:
                expires = None
        else:
            token_val = chunk
            expires = None
        tokens.append((token_val, expires))
    return tokens


PANEL_TOKENS = _parse_rotating_tokens(PANEL_API_TOKENS_RAW)


def _is_panel_token_valid(value: str) -> bool:
    if not PANEL_TOKENS:
        return False
    today = datetime.now(timezone.utc).date()
    for token, expires in PANEL_TOKENS:
        if expires and today > expires:
            continue
        if secrets.compare_digest(value, token):
            return True
    return False


def _load_pnl_history() -> List[dict]:
    entries: List[dict] = []
    if not PNL_LOG.exists():
        return entries
    try:
        with PNL_LOG.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return entries
    return entries


def _load_symbol_breakdowns() -> Dict[str, dict]:
    try:
        if not PNL_SYMBOLS_JSON.exists():
            return {}
        return json.loads(PNL_SYMBOLS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_risk_state_payload() -> tuple[Dict[str, Any], Dict[str, Any]]:
    state_path = LOGS_DIR / "risk_state.json"
    base: Dict[str, Any] = {}
    details: Dict[str, Any] = {}
    if state_path.exists():
        try:
            base = json.loads(state_path.read_text(encoding="utf-8"))
            details = {
                "consecutive_losses": base.get("consecutive_losses"),
                "cooldown_until_ts": base.get("cooldown_until_ts"),
                "active_cooldown_reason": base.get("active_cooldown_reason"),
                "cooldown_history": base.get("cooldown_history", [])[-5:],
                "recent_results": base.get("recent_results", [])[-20:],
                "dynamic_risk": base.get("dynamic_risk"),
                "start_equity": base.get("start_equity"),
                "current_equity": base.get("last_entry_equity"),
            }
        except Exception:
            base = {}
            details = {}
    return base, details


def _load_jsonl(path: Path, limit: int = 200) -> List[dict]:
    rows: List[dict] = []
    for raw in tail_lines(path, limit):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return rows


def _load_json_file(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        cache_key = str(path.resolve())
        mtime = path.stat().st_mtime
        cached = _JSON_CACHE.get(cache_key)
        if cached and cached[0] == mtime:
            return copy.deepcopy(cached[1])
        data = json.loads(path.read_text(encoding="utf-8"))
        _JSON_CACHE[cache_key] = (mtime, data)
        return copy.deepcopy(data)
    except Exception:
        return fallback


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _update_arena_metrics(state: Dict[str, Any]) -> None:
    goal = float(state.get("current_goal") or 0.0)
    ARENA_GOAL_GAUGE.set(goal)
    wins = float(state.get("wins") or 0.0)
    ARENA_WINS_GAUGE.set(wins)
    ticks = float(state.get("ticks_since_win") or 0.0)
    ARENA_TICKS_SINCE_WIN_GAUGE.set(ticks)
    drawdown = state.get("drawdown_pct")
    if isinstance(drawdown, (int, float)):
        ARENA_DRAWDOWN_GAUGE.set(float(drawdown))
    last_tick = _parse_iso_datetime(state.get("last_tick_ts") or state.get("updated_at"))
    if last_tick:
        age = max(0.0, (datetime.now(timezone.utc) - last_tick).total_seconds())
        ARENA_STATE_AGE_GAUGE.set(age)
    else:
        ARENA_STATE_AGE_GAUGE.set(float("nan"))


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bot_drawdown_metric() -> float:
    base, _ = _load_risk_state_payload()
    start = _safe_float(
        base.get("start_equity")
        or base.get("start_balance")
        or base.get("starting_equity")
        or base.get("starting_balance")
    )
    current = _safe_float(base.get("last_entry_equity") or base.get("current_equity"))
    if start and current is not None and start > 0:
        return max(0.0, (start - current) / start * 100.0)
    return 0.0


def _cerebro_decisions_rate_metric() -> float:
    if not CEREBRO_DECISIONS_LOG.exists():
        return 0.0
    rows = _load_jsonl(CEREBRO_DECISIONS_LOG, limit=600)
    if not rows:
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    count = 0
    for payload in rows:
        ts = _parse_iso_datetime(str(payload.get("ts") or payload.get("timestamp")))
        if not ts or ts < cutoff:
            continue
        if payload.get("action") in {None, "NO_TRADE"}:
            continue
        count += 1
    return count / 15.0 if count else 0.0


_bind_gauge_function(BOT_DRAWDOWN_GAUGE, _bot_drawdown_metric)
_bind_gauge_function(CEREBRO_DECISIONS_RATE_GAUGE, _cerebro_decisions_rate_metric)


def _build_observability_summary() -> ObservabilitySummary:
    state = _load_json_file(ARENA_STATE, {}) or {}
    last_tick_ts = state.get("last_tick_ts") or state.get("updated_at")
    tick_age = None
    dt = _parse_iso_datetime(last_tick_ts)
    if dt:
        tick_age = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    arena = ObservabilityArena(
        current_goal=state.get("current_goal"),
        wins=state.get("wins"),
        ticks_since_win=state.get("ticks_since_win"),
        last_tick_ts=last_tick_ts,
        tick_age_seconds=tick_age,
    )
    bot_drawdown = _bot_drawdown_metric()
    cerebro_rate = _cerebro_decisions_rate_metric()
    bot_summary = ObservabilityBot(drawdown_pct=round(bot_drawdown, 4) if bot_drawdown is not None else None)
    cerebro_summary = ObservabilityCerebro(
        decisions_per_min=round(cerebro_rate, 4) if cerebro_rate is not None else None
    )
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return ObservabilitySummary(timestamp=timestamp, arena=arena, bot=bot_summary, cerebro=cerebro_summary)


def _recent_pnl_entries(limit: int = 10) -> List[DashboardTrade]:
    entries: List[DashboardTrade] = []
    if not PNL_LOG.exists():
        return entries
    for payload in reversed(_load_jsonl(PNL_LOG, limit * 3)):
        if payload.get("type") not in {None, "close"}:
            continue
        ts = str(payload.get("ts") or payload.get("timestamp") or "")
        symbol = str(payload.get("symbol") or payload.get("market") or "")
        pnl = payload.get("pnl")
        tf = payload.get("tf") or payload.get("timeframe")
        try:
            pnl_value = float(pnl) if pnl is not None else None
        except Exception:
            pnl_value = None
        entries.append(
            DashboardTrade(
                ts=ts or "",
                symbol=symbol,
                timeframe=tf or None,
                side=None,
                pnl=pnl_value,
            )
        )
        if len(entries) >= limit:
            break
    entries.reverse()
    return entries


def _explain_decision(metadata: Dict[str, Any] | None) -> str:
    if not metadata:
        return ""
    parts: List[str] = []
    macro = metadata.get("macro") or metadata.get("macro_pulse")
    if isinstance(macro, dict):
        direction = macro.get("direction")
        score = macro.get("score")
        if direction and direction != "neutral":
            parts.append(f"Macro {direction}")
        if isinstance(score, (int, float)):
            parts.append(f"score {score:+.2f}")
    news_sent = metadata.get("news_sentiment")
    if isinstance(news_sent, (int, float)) and abs(news_sent) > 0.05:
        parts.append(f"noticia {'alcista' if news_sent > 0 else 'bajista'} ({news_sent:+.2f})")
    if metadata.get("exploration_triggered"):
        parts.append("modo exploración")
    anomaly = metadata.get("anomaly")
    if isinstance(anomaly, dict) and anomaly.get("flag"):
        parts.append("anomalía detectada")
    session_guard = metadata.get("session_guard")
    if isinstance(session_guard, dict):
        reason = session_guard.get("reason")
        state = session_guard.get("state")
        if reason:
            parts.append(reason)
        elif state:
            parts.append(f"guardia {state}")
    ml_override = metadata.get("ml_override")
    if ml_override:
        parts.append("modelo ML sobre-escribió heurística")
    if not parts:
        return ""
    return " · ".join(parts)


def _recent_decisions(limit: int = 10, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> List[DashboardTrade]:
    rows: List[DashboardTrade] = []
    if not CEREBRO_DECISIONS_LOG.exists():
        return rows
    for payload in reversed(_load_jsonl(CEREBRO_DECISIONS_LOG, limit * 5)):
        action = payload.get("action")
        if action in {None, "NO_TRADE"}:
            continue
        sym = str(payload.get("symbol") or "")
        tf = str(payload.get("timeframe") or "")
        if symbol and sym.upper() != symbol.upper():
            continue
        if timeframe and tf and tf != timeframe:
            continue
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        reason = _explain_decision(meta)
        rows.append(
            DashboardTrade(
                ts=str(payload.get("ts") or ""),
                symbol=sym,
                timeframe=tf or None,
                side=action,
                confidence=float(payload.get("confidence") or 0.0) if payload.get("confidence") is not None else None,
                risk_pct=float(payload.get("risk_pct") or 0.0) if payload.get("risk_pct") is not None else None,
                reason=reason or None,
            )
        )
        if len(rows) >= limit:
            break
    rows.reverse()
    return rows


def _format_currency(value: float | None) -> str:
    if value is None:
        return "0.00"
    try:
        return f"{value:+.2f}"
    except Exception:
        return str(value)


def _iso_to_epoch_seconds(value: str | None) -> Optional[int]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _pnl_metrics() -> tuple[List[DashboardMetric], Dict[str, float]]:
    history = _load_pnl_history()
    day_map: Dict[str, float] = {}
    for entry in history:
        day = entry.get("day")
        if not day:
            ts_raw = entry.get("ts") or entry.get("timestamp")
            if isinstance(ts_raw, str) and len(ts_raw) >= 10:
                day = ts_raw[:10]
        if not day:
            continue
        try:
            value = float(entry.get("pnl_eur") or entry.get("pnl") or 0.0)
        except Exception:
            value = 0.0
        if entry.get("type") == "daily":
            day_map[day] = value
        else:
            day_map[day] = day_map.get(day, 0.0) + value

    today = datetime.now(timezone.utc).date()
    pnl_today = day_map.get(str(today), 0.0)
    pnl_week = 0.0
    for offset in range(7):
        key = str(today - timedelta(days=offset))
        pnl_week += day_map.get(key, 0.0)
    pnl_month = 0.0
    for offset in range(30):
        key = str(today - timedelta(days=offset))
        pnl_month += day_map.get(key, 0.0)
    pnl_total = sum(day_map.values())

    metrics = [
        DashboardMetric(name="PnL diario", value=pnl_today, formatted=_format_currency(pnl_today)),
        DashboardMetric(name="PnL 7 días", value=pnl_week, formatted=_format_currency(pnl_week)),
        DashboardMetric(name="PnL 30 días", value=pnl_month, formatted=_format_currency(pnl_month)),
        DashboardMetric(name="PnL total", value=pnl_total, formatted=_format_currency(pnl_total)),
    ]
    return metrics, day_map

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_control_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> None:
    proxy_principal = request.headers.get(PROXY_BASIC_HEADER) or request.headers.get(PROXY_BASIC_HEADER.lower())
    if TRUST_PROXY_BASIC and proxy_principal:
        return
    if not CONTROL_USER or not CONTROL_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CONTROL_USER y CONTROL_PASSWORD no están configurados",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(credentials.username, CONTROL_USER)
    pass_ok = secrets.compare_digest(credentials.password, CONTROL_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )


def require_panel_token(request: Request) -> None:
    if not PANEL_TOKENS:
        return
    header = request.headers.get("x-panel-token")
    if not header or not _is_panel_token_valid(header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Panel-Token inválido",
        )


@app.get("/health", response_model=Health)
def health():
    return Health(ok=True, time=str(datetime.now(timezone.utc)), pid=os.getpid())


@app.get("/status", response_model=StatusResponse)
def get_status(_: None = Depends(require_panel_token)):

    sls_active, sls_detail = service_status("sls-bot")
    services = {
        "sls-bot": ServiceState(active=sls_active, detail=sls_detail)
    }
    bybit_cfg = (BOT_CONFIG.get("bybit") if isinstance(BOT_CONFIG, dict) else {}) or {}
    risk_state_path = LOGS_DIR / "risk_state.json"
    risk_state: Dict[str, Any] = {}
    if risk_state_path.exists():
        try:
            risk_state = json.loads(risk_state_path.read_text(encoding="utf-8"))
        except Exception:
            risk_state = {}
    bot: Dict[str, Any] = {
        "config": {
            "env": BOT_CONFIG.get("env", "TESTNET") if isinstance(BOT_CONFIG, dict) else "TESTNET",
            "bybit": {
                "base_url": bybit_cfg.get("base_url"),
                "symbols": bybit_cfg.get("symbols"),
            },
            "mode": {
                "active": BOT_CONFIG.get("_active_mode"),
                "available": BOT_CONFIG.get("_available_modes"),
            },
        },
        "risk_state": risk_state,
        "config_file": CFG_PATH_IN_USE,
        "api_health": health().model_dump(),
    }
    # Try to enrich risk_state from bot logs if available
    state_file = LOGS_DIR / "risk_state.json"
    if state_file.exists():
        try:
            detailed_state = json.loads(state_file.read_text(encoding="utf-8"))
            bot["risk_state_details"] = {
                "consecutive_losses": detailed_state.get("consecutive_losses"),
                "cooldown_until_ts": detailed_state.get("cooldown_until_ts"),
                "active_cooldown_reason": detailed_state.get("active_cooldown_reason"),
                "cooldown_history": detailed_state.get("cooldown_history", [])[-5:],
                "recent_results": detailed_state.get("recent_results", [])[-5:],
                "dynamic_risk": detailed_state.get("dynamic_risk"),
                "start_equity": detailed_state.get("start_equity"),
                "current_equity": detailed_state.get("last_entry_equity"),
            }
        except Exception:
            pass
    return StatusResponse(services=services, bot=bot)


@app.post("/control/{service}/{action}")
def control_service(service: str, action: str, _: None = Depends(require_control_auth)):
    ok, detail = service_action(service, action)
    return {"ok": ok, "detail": detail}


@app.get("/logs/bridge", response_model=LogResponse)
def get_bridge_logs(limit: int = Query(200, ge=1, le=2000), _: None = Depends(require_panel_token)):

    lines = tail_lines(BRIDGE_LOG, limit)
    return LogResponse(lines=lines)


@app.get("/decisiones", response_model=DecisionsResponse)
def get_decisiones(limit: int = Query(20, ge=1, le=1000), _: None = Depends(require_panel_token)):

    rows: List[dict] = []
    try:
        if DECISIONS_LOG.exists():
            with DECISIONS_LOG.open("r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
            for line in all_lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return DecisionsResponse(rows=rows)


@app.get("/alerts", response_model=AlertsResponse)
def get_alerts(window_minutes: int = Query(60, ge=5, le=1440), _: None = Depends(require_panel_token)):
    payload = collect_alerts(
        bridge_log=BRIDGE_LOG,
        decisions_log=DECISIONS_LOG,
        window_minutes=window_minutes,
    )
    return AlertsResponse(**payload)


@app.get("/pnl/diario", response_model=PnLDailyResponse)
def pnl_diario(days: int = Query(7, ge=1, le=30), _: None = Depends(require_panel_token)):
    entries = _load_pnl_history()
    symbol_breakdowns = _load_symbol_breakdowns()
    daily_map: Dict[str, Dict[str, float]] = {}
    for entry in entries:
        day = entry.get("day")
        if not day:
            ts = entry.get("ts") or entry.get("timestamp")
            if isinstance(ts, str) and len(ts) >= 10:
                day = ts[:10]
        if not day:
            continue
        info = daily_map.setdefault(day, {"pnl": 0.0, "from_daily": False})
        if entry.get("type") == "daily":
            try:
                info["pnl"] = float(entry.get("pnl_eur") or entry.get("pnl") or 0.0)
            except Exception:
                info["pnl"] = 0.0
            info["from_daily"] = True
        else:
            try:
                info["pnl"] += float(entry.get("pnl") or 0.0)
            except Exception:
                continue

    out: List[PnLDailyItem] = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        key = str(d)
        info = daily_map.get(key)
        fills_day = symbol_breakdowns.get(key) if isinstance(symbol_breakdowns, dict) else None
        symbols_payload = []
        if fills_day:
            symbols_info = fills_day.get("symbols") or {}
            for symbol, data in sorted(symbols_info.items(), key=lambda kv: kv[0]):
                try:
                    pnl_value = float(data.get("pnl") or 0.0)
                except Exception:
                    pnl_value = 0.0
                try:
                    fees_value = float(data.get("fees") or 0.0)
                except Exception:
                    fees_value = 0.0
                trades_value = int(data.get("trades") or 0)
                symbols_payload.append(SymbolPnL(symbol=symbol, pnl_eur=pnl_value, fees_eur=fees_value, trades=trades_value))
            target_total = fills_day.get("total")
            try:
                total_pnl = float(target_total) if target_total is not None else sum(item.pnl_eur for item in symbols_payload)
            except Exception:
                total_pnl = sum(item.pnl_eur for item in symbols_payload)
            out.append(
                PnLDailyItem(
                    day=key,
                    pnl_eur=total_pnl,
                    from_fills=True,
                    symbols=symbols_payload,
                )
            )
            continue

        out.append(
            PnLDailyItem(
                day=key,
                pnl_eur=float(info["pnl"]) if info else 0.0,
                from_fills=False,
                symbols=[],
            )
        )
    return PnLDailyResponse(days=out)


@app.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(_: None = Depends(require_panel_token)):
    mode = BOT_CONFIG.get("_active_mode")
    services_state = {"sls-bot": service_status("sls-bot")}
    alerts_raw = collect_alerts(bridge_log=BRIDGE_LOG, decisions_log=DECISIONS_LOG, window_minutes=120)
    alerts: List[AlertItem] = [
        AlertItem(
            name=entry["name"],
            count=int(entry["count"]),
            severity=str(entry["severity"]),
            hint=str(entry["hint"]),
            latest=entry.get("latest"),
        )
        for entry in alerts_raw.get("alerts", [])
    ]

    metrics, day_map = _pnl_metrics()
    risk_state, risk_details = _load_risk_state_payload()

    recent_results = risk_details.get("recent_results") or []
    wins = sum(1 for row in recent_results if row.get("win") == 1)
    losses = sum(1 for row in recent_results if row.get("win") == -1)
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades else None
    if win_rate is not None:
        metrics.append(
            DashboardMetric(name="Win rate (ventana)", value=win_rate, formatted=f"{win_rate:.1f}%")
        )

    current_equity = risk_details.get("current_equity")
    if isinstance(current_equity, (int, float)):
        metrics.append(
            DashboardMetric(name="Equity estimada", value=current_equity, formatted=f"{current_equity:.2f}")
        )

    heartbeat_delay = alerts_raw.get("summary", {}).get("heartbeat_delay_seconds")
    issues: List[DashboardIssue] = []
    level: Literal["ok", "warning", "error"] = "ok"

    svc_active, svc_detail = services_state["sls-bot"]
    if not svc_active:
        level = "error"
        issues.append(
            DashboardIssue(
                severity="error",
                message=f"Servicio sls-bot inactivo ({svc_detail or 'sin detalle'})",
            )
        )

    critical_alert = next((a for a in alerts if a.severity == "critical"), None)
    warning_alerts = [a for a in alerts if a.severity == "warning"]
    if critical_alert:
        level = "error"
        issues.append(
            DashboardIssue(
                severity="error",
                message=f"{critical_alert.name}: {critical_alert.hint} (x{critical_alert.count})",
            )
        )
    elif warning_alerts:
        if level != "error":
            level = "warning"
        for warn in warning_alerts:
            issues.append(
                DashboardIssue(
                    severity="warning",
                    message=f"{warn.name}: {warn.hint} (x{warn.count})",
                )
            )

    if heartbeat_delay and heartbeat_delay > 180:
        if level != "error":
            level = "warning"
        issues.append(
            DashboardIssue(
                severity="warning",
                message=f"No hay heartbeat reciente (>{int(heartbeat_delay)}s)",
            )
        )

    cooldown_until = risk_details.get("cooldown_until_ts")
    now_ts = datetime.now(timezone.utc).timestamp()
    if isinstance(cooldown_until, (int, float)) and cooldown_until > now_ts:
        if level != "error":
            level = "warning"
        remaining = int(cooldown_until - now_ts)
        issues.append(
            DashboardIssue(
                severity="warning",
                message=f"Cooldown activo ({remaining // 60} min restantes)",
            )
        )

    # Detectar fallos de feeds RSS
    cerebro_log = LOGS_ROOT / "cerebro_service.log"
    for raw in tail_lines(cerebro_log, 200):
        if "RSS fetch failed" in raw:
            issues.append(
                DashboardIssue(
                    severity="warning",
                    message="Fallo al leer RSS (Binance); revisar conectividad o feed.",
                )
            )
            if level != "error":
                level = "warning"
            break

    summary_text = "Bot operativo"
    if level == "error":
        summary_text = "Bot en estado crítico"
    elif level == "warning":
        summary_text = "Bot con advertencias"
    if mode:
        summary_text += f" · modo {mode}"

    recent_trades = _recent_decisions(limit=12)
    recent_pnl = _recent_pnl_entries(limit=12)

    return DashboardSummaryResponse(
        level=level,
        summary=summary_text,
        mode=str(mode) if mode else None,
        updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        metrics=metrics,
        issues=issues,
        alerts=alerts,
        recent_trades=recent_trades,
        recent_pnl=recent_pnl,
    )


@app.get("/dashboard/chart", response_model=DashboardChartResponse)
def dashboard_chart(
    symbol: str = Query(..., min_length=2, max_length=30),
    timeframe: str = Query("15m", min_length=1, max_length=10),
    limit: int = Query(200, ge=50, le=1000),
    _: None = Depends(require_panel_token),
):
    try:
        from bot.sls_bot import ia_utils
    except Exception as exc:  # pragma: no cover - fallback para instalaciones parciales
        raise HTTPException(status_code=500, detail=f"ia_utils no disponible: {exc}") from exc

    try:
        df = ia_utils.fetch_ohlc(symbol, timeframe, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error obteniendo velas: {exc}") from exc

    candles: List[DashboardCandle] = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            try:
                ts_ms = float(row.get("ts") or row.get("start"))
                ts = int(ts_ms / 1000)
            except Exception:
                continue
            try:
                candles.append(
                    DashboardCandle(
                        time=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                    )
                )
            except Exception:
                continue

    trade_markers: List[DashboardTradeMarker] = []
    for trade in _recent_decisions(limit=50, symbol=symbol, timeframe=timeframe):
        ts = _iso_to_epoch_seconds(trade.ts)
        if ts is None:
            continue
        trade_markers.append(
            DashboardTradeMarker(
                time=ts,
                symbol=trade.symbol,
                timeframe=trade.timeframe,
                side=trade.side,
                label=trade.side,
                reason=trade.reason,
                confidence=trade.confidence,
                risk_pct=trade.risk_pct,
            )
        )

    candles.sort(key=lambda item: item.time)
    trade_markers.sort(key=lambda item: item.time)
    return DashboardChartResponse(candles=candles, trades=trade_markers)


@app.get("/arena/ranking")
def arena_ranking(_: None = Depends(require_panel_token)):
    ranking = _load_json_file(ARENA_RANKING, [])
    return {"count": len(ranking), "ranking": ranking}


@app.get("/arena/state")
def arena_state(_: None = Depends(require_panel_token)):
    state = _load_json_file(ARENA_STATE, {"current_goal": None, "wins": 0})
    _update_arena_metrics(state)
    return state


@app.get("/observability/summary", response_model=ObservabilitySummary)
def observability_summary(_: None = Depends(require_panel_token)):
    return _build_observability_summary()


@app.get("/arena/ledger")
def arena_ledger(
    strategy_id: str = Query(..., min_length=2, max_length=64),
    limit: int = Query(50, ge=10, le=200),
    _: None = Depends(require_panel_token),
):
    from bot.arena.storage import ArenaStorage

    storage = ArenaStorage(ARENA_DB)
    data = storage.ledger_for(strategy_id, limit=limit)
    return {"id": strategy_id, "entries": data}


@app.post("/arena/tick")
def arena_tick(_: None = Depends(require_panel_token)):
    from bot.arena.service import ArenaService

    service = ArenaService()
    service.tick()
    return {"status": "ok"}


@app.post("/arena/promote")
def arena_promote(
    strategy_id: str = Query(..., min_length=2, max_length=64),
    min_trades: int = Query(50, ge=10, le=1000),
    min_sharpe: float = Query(0.2, ge=0.0, le=5.0),
    max_drawdown: float = Query(35.0, ge=1.0, le=100.0),
    force: bool = Query(False),
    _: None = Depends(require_panel_token),
):
    from bot.arena.promote import export_strategy

    try:
        pkg_dir = export_strategy(
            strategy_id,
            min_trades=min_trades,
            min_sharpe=min_sharpe,
            max_drawdown=max_drawdown,
            force=force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "path": str(pkg_dir)}


@app.get("/arena/notes", response_model=ArenaNotesResponse)
def arena_notes(
    strategy_id: str = Query(..., min_length=2, max_length=64),
    limit: int = Query(20, ge=1, le=50),
    _: None = Depends(require_panel_token),
):
    from bot.arena.storage import ArenaStorage

    storage = ArenaStorage(ARENA_DB)
    notes = storage.notes_for(strategy_id, limit=limit)
    return {"notes": notes}


@app.post("/arena/notes", response_model=ArenaNote)
def arena_add_note(payload: ArenaNotePayload, _: None = Depends(require_panel_token)):
    from bot.arena.storage import ArenaStorage

    storage = ArenaStorage(ARENA_DB)
    record = storage.add_note(payload.strategy_id, payload.note, payload.author or "panel")
    return record
