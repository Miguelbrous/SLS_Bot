from __future__ import annotations
import os, joblib, numpy as np, pandas as pd
from typing import Dict, Any

try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.model_selection import train_test_split

from .ia_utils import fetch_ohlc, compute_indicators

_MODELS_DIR = "/opt/sls_bot/models"
_FEATURES = ["rsi","atr","range_pct","ema_diff_bps","dist_to_avwap_bps","dist_to_ema200_bps",
             "breakout_up","breakout_dn","slope_ema_fast","ema_fast","ema_mid","ema_slow","close","volume"]

def _future_return(df: pd.DataFrame, horizon: int) -> pd.Series:
    fwd = df["close"].shift(-horizon)
    return (fwd - df["close"]) / df["close"]

def _prep_dataset(symbol: str, marco: str, thr: float, horizon: int, limit: int) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, marco, limit=limit+500)
    df = compute_indicators(raw)
    df["fret"] = _future_return(df, horizon=horizon)
    df["y_up"] = (df["fret"] > thr).astype(int)
    df = df.dropna().reset_index(drop=True)
    return df

def train_model(symbol: str, marco: str, thr: float = 0.005, horizon: int = 20, limit: int = 3000) -> Dict[str, Any]:
    os.makedirs(_MODELS_DIR, exist_ok=True)
    df = _prep_dataset(symbol, marco, thr, horizon, limit)
    if len(df) < 500:
        raise RuntimeError(f"Datos insuficientes para entrenar: {len(df)}")

    X = df[_FEATURES].astype(float).values
    y = df["y_up"].astype(int).values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=max(0.2, min(0.3, 800/len(df))), shuffle=False)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    if _HAS_XGB:
        model = XGBClassifier(
            n_estimators=300, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
            n_jobs=2, random_state=42
        )
        model.fit(X_train_s, y_train)
    else:
        model = LogisticRegression(max_iter=200)
        model.fit(X_train_s, y_train)

    proba = model.predict_proba(X_test_s)[:,1] if hasattr(model,"predict_proba") \
            else 1.0/(1.0+np.exp(-model.decision_function(X_test_s)))

    auc = float(roc_auc_score(y_test, proba))
    acc = float(accuracy_score(y_test, (proba>=0.5).astype(int)))

    base = os.path.join(_MODELS_DIR, f"ia_model_{symbol.upper()}_{marco}")
    joblib.dump(model,  base + ".pkl")
    joblib.dump(scaler, base + ".scaler.pkl")
    joblib.dump({
        "symbol": symbol.upper(), "marco": marco, "thr_label": float(thr),
        "horizon": int(horizon), "features": list(_FEATURES),
        "n_train": int(len(X_train)), "n_test": int(len(X_test))
    }, base + ".meta.pkl")

    return {"ok": True, "metrics": {"auc": round(auc,4), "accuracy": round(acc,4),
                                     "n_train": int(len(X_train)), "n_test": int(len(X_test))},
            "paths": {"model": base + ".pkl", "scaler": base + ".scaler.pkl", "meta": base + ".meta.pkl"}}
