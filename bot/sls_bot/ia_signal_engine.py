from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np

from .config_loader import load_config
from .ia_utils import latest_slice
from .strategies import get_scalping_strategy

_cfg = load_config()
_MODELS_DIR = "/opt/sls_bot/models"
_FEATURES = [
    "rsi",
    "atr",
    "range_pct",
    "ema_diff_bps",
    "dist_to_avwap_bps",
    "dist_to_ema200_bps",
    "breakout_up",
    "breakout_dn",
    "slope_ema_fast",
    "ema_fast",
    "ema_mid",
    "ema_slow",
    "close",
    "volume",
]


def _scalping_applicable(marco: str) -> bool:
    strategy_cfg = (_cfg.get("strategies") or {}).get("scalping") or {}
    if not strategy_cfg.get("enabled"):
        return False
    allowed_modes = {str(m).lower() for m in strategy_cfg.get("modes", ["test"])}
    active_mode = str(_cfg.get("_active_mode") or "").lower()
    if allowed_modes and active_mode and active_mode not in allowed_modes:
        return False
    allowed_tf = [str(tf).lower() for tf in strategy_cfg.get("timeframes", [])]
    if not allowed_tf:
        return True
    marco_norm = str(marco).lower()
    if marco_norm in allowed_tf:
        return True
    return bool(strategy_cfg.get("force_primary_timeframe", True))


def _try_scalping(symbol: str, marco: str, riesgo_pct_user: float | None, leverage_user: int | None):
    strategy_cfg = (_cfg.get("strategies") or {}).get("scalping") or {}
    if not _scalping_applicable(marco):
        return None
    engine = get_scalping_strategy(strategy_cfg)
    return engine.decide(symbol=symbol, marco=marco, riesgo_pct_user=riesgo_pct_user, leverage_user=leverage_user)

def _load_model(symbol: str, marco: str):
    base = os.path.join(_MODELS_DIR, f"ia_model_{symbol.upper()}_{marco}")
    model_p = base + ".pkl"
    scaler_p = base + ".scaler.pkl"
    meta_p   = base + ".meta.pkl"
    if not os.path.exists(model_p):
        return None, None, {"trained": False}
    model  = joblib.load(model_p)
    scaler = joblib.load(scaler_p) if os.path.exists(scaler_p) else None
    meta   = joblib.load(meta_p) if os.path.exists(meta_p) else {}
    meta["trained"] = True
    return model, scaler, meta

def _rule_scores(s) -> Dict[str,float]:
    long_s = 0.0; short_s = 0.0
    if s.close > s.ema_slow: long_s += 0.25
    if s.close < s.ema_slow: short_s += 0.25
    if s.ema_fast > s.ema_mid > s.ema_slow: long_s += 0.15
    if s.ema_fast < s.ema_mid < s.ema_slow: short_s += 0.15
    if s.rsi >= 55: long_s += 0.20
    if s.rsi <= 45: short_s += 0.20
    if s.close > s.avwap: long_s += 0.15
    else: short_s += 0.15
    if s.breakout_up == 1: long_s += 0.15
    if s.breakout_dn == 1: short_s += 0.15
    atr_bps = float(s.atr / s.close * 10000.0)
    if atr_bps > 120: long_s *= 0.9; short_s *= 0.9
    return {"long": min(long_s,1.0), "short": min(short_s,1.0)}

def decide(symbol: str, marco: str, riesgo_pct_user: float | None = None, leverage_user: int | None = None
          ) -> Tuple[Dict[str,Any], Dict[str,Any], Dict[str,Any]]:
    ia_cfg = _cfg.get("ia", {}); bybit_cfg = _cfg.get("bybit", {})
    risk_default = float(ia_cfg.get("riesgo_pct", 0.75))
    lev_default  = int(bybit_cfg.get("default_leverage", 5))
    thr_enter    = float(ia_cfg.get("proba_enter", 0.60))
    w_rules, w_ml = 0.6, 0.4

    scalping_result = _try_scalping(symbol, marco, riesgo_pct_user, leverage_user)
    if scalping_result is not None:
        scores = scalping_result.evidences.get("scores", {})
        rules = {
            "long": float(scores.get("long", 0.0)),
            "short": float(scores.get("short", 0.0)),
        }
        evid = {
            "rules": rules,
            "ml": {"proba_up": scores.get("confidence_norm"), "trained": False},
            "scalping": scalping_result.evidences,
        }
        meta_out = {
            "weights": {"rules": 1.0, "ml": 0.0},
            "thr_enter": scalping_result.metadata.get("confidence_threshold", thr_enter),
            "model_meta": {"trained": False, "strategy": "scalping"},
            "strategy": scalping_result.metadata,
        }
        return scalping_result.payload, evid, meta_out

    df, s = latest_slice(symbol, marco)
    scores = _rule_scores(s)
    rules_long, rules_short = scores["long"], scores["short"]

    model, scaler, meta = _load_model(symbol, marco)
    proba_up = None
    if meta.get("trained"):
        x = np.array([[float(s.get(k, np.nan)) for k in _FEATURES]], dtype=float)
        if scaler is not None:
            try: x = scaler.transform(x)
            except Exception: pass
        try:
            if hasattr(model,"predict_proba"):
                proba_up = float(model.predict_proba(x)[0,1])
            else:
                score = float(model.decision_function(x)[0]); proba_up = 1/(1+np.exp(-score))
        except Exception:
            proba_up = None
    if proba_up is None:
        w_rules, w_ml = 1.0, 0.0; proba_up = 0.5

    long_w  = w_rules*rules_long  + w_ml*proba_up
    short_w = w_rules*rules_short + w_ml*(1.0-proba_up)
    conf = max(long_w, short_w)
    lado = "LONG" if long_w >= short_w else "SHORT"
    decision = lado if conf >= thr_enter else "NO_TRADE"

    riesgo_pct = float(riesgo_pct_user if riesgo_pct_user is not None else risk_default)
    leverage   = int(leverage_user   if leverage_user   is not None else lev_default)

    resumen = (f"Tendencia: {'alcista' if s.close > s.ema_slow else 'bajista'} | "
               f"RSI={float(s.rsi):.1f} | AVWAP={'soporte' if s.close> s.avwap else 'resistencia'} | "
               f"Rules(L/S)={rules_long:.2f}/{rules_short:.2f} | ML_up={proba_up:.2f} | Ensemble={conf:.2f}")

    webhook = {}
    if decision in ("LONG","SHORT"):
        webhook = {"signal": f"SLS_{decision}_ENTRY", "symbol": symbol.upper(), "tf": marco,
                   "risk_pct": riesgo_pct, "leverage": leverage, "post_only": False,
                   "tp1_close_pct": 50, "move_sl_to_be_on_tp1": True}

    payload = {"simbolo": symbol.upper(), "marco": marco, "modo": ia_cfg.get("modo","asesor"),
               "decision": decision, "confianza_pct": round(conf*100,1), "riesgo_pct": riesgo_pct,
               "leverage": leverage, "resumen": resumen, "webhook_body": webhook,
               "notas": ("Sin señal suficiente" if decision=="NO_TRADE" else None)}
    evid = {"rules":{"long":rules_long,"short":rules_short},
            "ml":{"proba_up":proba_up,"trained":meta.get("trained",False)}}
    meta_out = {"weights":{"rules":w_rules,"ml":w_ml},"thr_enter":thr_enter,"model_meta":meta}
    return payload, evid, meta_out
