from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from .service import get_cerebro

cerebro_router = APIRouter(prefix="/cerebro", tags=["cerebro"])

try:
    get_cerebro().start_loop()
except Exception:
    pass


@cerebro_router.get("/status")
def cerebro_status():
    cerebro = get_cerebro()
    if not cerebro.config.enabled:
        return {"ok": False, "enabled": False, "time": datetime.utcnow().isoformat() + "Z"}
    data = cerebro.get_status()
    data["time"] = datetime.utcnow().isoformat() + "Z"
    return data


@cerebro_router.post("/decide")
def cerebro_decide(payload: Dict[str, Any]):
    cerebro = get_cerebro()
    if not cerebro.config.enabled:
        raise HTTPException(status_code=503, detail="Cerebro deshabilitado")
    symbol = (payload.get("symbol") or "").upper()
    timeframe = payload.get("timeframe") or "15m"
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol requerido")
    cerebro.run_cycle()
    decision = cerebro.latest_decision(symbol, timeframe)
    if not decision:
        raise HTTPException(status_code=404, detail="sin decisión disponible")
    return decision.__dict__


@cerebro_router.post("/learn")
def cerebro_learn(payload: Dict[str, Any]):
    cerebro = get_cerebro()
    if not cerebro.config.enabled:
        raise HTTPException(status_code=503, detail="Cerebro deshabilitado")
    symbol = (payload.get("symbol") or "").upper()
    timeframe = payload.get("timeframe") or "15m"
    pnl = float(payload.get("pnl") or 0.0)
    features = payload.get("features") or {}
    decision = payload.get("decision") or "UNKNOWN"
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol requerido")
    cerebro.register_trade(symbol=symbol, timeframe=timeframe, pnl=pnl, features=features, decision=decision)
    return {"ok": True}


@cerebro_router.get("/decisions")
def cerebro_decisions(limit: int = Query(50, ge=1, le=200)):
    cerebro = get_cerebro()
    if not cerebro.config.enabled:
        raise HTTPException(status_code=503, detail="Cerebro deshabilitado")
    rows = cerebro.list_decisions(limit=limit)
    return {"rows": rows, "count": len(rows)}
