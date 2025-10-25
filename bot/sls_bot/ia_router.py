from fastapi import APIRouter
from pathlib import Path
import csv, joblib
from datetime import datetime, timezone
from .ia_models import IASignalRequest, IASignalResponse, LearnEvent
from .ia_signal_engine import decide
from .ia_train import train_model

router = APIRouter(tags=["IA"])
LOG_DIR = Path("/opt/sls_bot/logs/ia"); LOG_DIR.mkdir(parents=True, exist_ok=True)
LEARN_CSV = LOG_DIR / "ia_learn_log.csv"
MODELS_DIR = Path("/opt/sls_bot/models")

@router.post("/signal", response_model=IASignalResponse)
def ia_signal(req: IASignalRequest):
    payload, _, _ = decide(symbol=req.simbolo.upper(), marco=req.marco,
                           riesgo_pct_user=req.riesgo_pct, leverage_user=req.leverage)
    payload["modo"] = req.modo
    return payload

@router.post("/learn")
def ia_learn(evt: LearnEvent):
    is_new = not LEARN_CSV.exists()
    with LEARN_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["ts","simbolo","marco","etiqueta_setup","lado","pnl","mfe","mae","slippage_bps","fees_bps","notas"])
        w.writerow([datetime.now(timezone.utc).isoformat(), evt.simbolo.upper(), evt.marco, evt.etiqueta_setup,
                    evt.lado, evt.pnl, evt.mfe or "", evt.mae or "", evt.slippage_bps or "", evt.fees_bps or "", evt.notas or ""])
    return {"ok": True, "logged": str(LEARN_CSV)}

@router.get("/status")
def ia_status():
    return {"ok": True,"time": datetime.now(timezone.utc).isoformat(),
            "models_dir": str(MODELS_DIR), "learn_log_path": str(LEARN_CSV)}

@router.post("/train")
def ia_train_endpoint(simbolo: str, marco: str, thr: float = 0.005, horizon: int = 20, limit: int = 3000):
    return train_model(simbolo.upper(), marco, thr=thr, horizon=horizon, limit=limit)

@router.get("/model")
def ia_model_info(simbolo: str, marco: str):
    base = MODELS_DIR / f"ia_model_{simbolo.upper()}_{marco}"
    meta_f = base.with_suffix(".meta.pkl")
    if not meta_f.exists(): return {"ok": False, "msg": "modelo no encontrado"}
    meta = joblib.load(meta_f)
    return {"ok": True, "meta": meta, "paths": {"model": str(base.with_suffix(".pkl")),
            "scaler": str(base.with_suffix(".scaler.pkl")), "meta": str(meta_f)}}
