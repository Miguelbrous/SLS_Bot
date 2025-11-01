import json
import os
import secrets
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .alerts import collect_alerts
from .models import (
    AlertsResponse,
    DecisionsResponse,
    Health,
    LogResponse,
    PnLDailyItem,
    PnLDailyResponse,
    ServiceState,
    StatusResponse,
    SymbolPnL,
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
LOGS_DIR = _resolve_path(PATHS_CFG.get("logs_dir"), PROJECT_ROOT / "logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BRIDGE_LOG = Path(os.getenv("BRIDGE_LOG", LOGS_DIR / "bridge.log"))
DECISIONS_LOG = Path(os.getenv("DECISIONS_LOG", LOGS_DIR / "decisions.jsonl"))
PNL_LOG = Path(os.getenv("PNL_LOG", LOGS_DIR / "pnl.jsonl"))
PNL_SYMBOLS_JSON = Path(os.getenv("PNL_SYMBOLS_JSON", LOGS_DIR / "pnl_daily_symbols.json"))

app = FastAPI(title="SLS Bot API", version="1.0.0")

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


