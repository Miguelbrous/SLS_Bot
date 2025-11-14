from __future__ import annotations
import requests, pandas as pd, numpy as np
from .config_loader import load_config

_cfg = load_config()
_BASE_URL = _cfg["bybit"]["base_url"].rstrip("/")

def _map_interval(marco: str) -> str:
    s = str(marco).lower().strip()
    if s.endswith("m"): return str(int(s[:-1]))
    if s.endswith("h"): return str(int(s[:-1]) * 60)
    if s in ("1d","d","day"): return "D"
    if s in ("1w","w","week"): return "W"
    return "15"

def fetch_ohlc(symbol: str, marco: str, limit: int = 1000) -> pd.DataFrame:
    iv = _map_interval(marco)
    url = f"{_BASE_URL}/v5/market/kline"
    r = requests.get(url, params={"category":"linear","symbol":symbol.upper(),"interval":iv,"limit":min(1000,int(limit))}, timeout=12)
    r.raise_for_status()
    data = r.json()
    if data.get("retCode") != 0: raise RuntimeError(data)
    rows = data["result"]["list"]
    df = pd.DataFrame(rows, columns=["start","open","high","low","close","volume","turnover"])
    for c in ["open","high","low","close","volume","turnover"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_numeric(df["start"], errors="coerce")
    df = df.sort_values("ts").reset_index(drop=True)
    df["typical"] = (df["high"] + df["low"] + df["close"]) / 3.0
    return df

def ema(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(span=length, adjust=False, min_periods=length).mean()

def rsi(c: pd.Series, length: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).rolling(length).mean()
    dn = (-d.clip(upper=0)).rolling(length).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100/(1+rs)).fillna(50)

def atr(h: pd.Series, l: pd.Series, c: pd.Series, length: int = 14) -> pd.Series:
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(length).mean().bfill()

def avwap_daily(df: pd.DataFrame) -> pd.Series:
    dt = pd.to_datetime(df["ts"], unit="ms", utc=True)
    day = dt.dt.date
    out = []
    for _, g in df.groupby(day, sort=False):
        tpv = g["typical"]*g["volume"]
        cv = g["volume"].cumsum().replace(0, np.nan)
        out.append(tpv.cumsum()/cv)
    return pd.concat(out, axis=0).reset_index(drop=True).ffill()

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = ema(df["close"], 20)
    df["ema_mid"]  = ema(df["close"], 50)
    df["ema_slow"] = ema(df["close"], 200)
    df["rsi"] = rsi(df["close"], 14)
    df["atr"] = atr(df["high"], df["low"], df["close"], 14)
    df["avwap"] = avwap_daily(df)
    df["range_pct"] = (df["high"] - df["low"]) / df["close"] * 10000
    df["ema_diff_bps"] = (df["ema_fast"] - df["ema_slow"]) / df["close"] * 10000
    df["dist_to_avwap_bps"] = (df["close"] - df["avwap"]) / df["close"] * 10000
    df["dist_to_ema200_bps"] = (df["close"] - df["ema_slow"]) / df["close"] * 10000
    hh = df["high"].rolling(20, min_periods=20).max()
    ll = df["low"].rolling(20, min_periods=20).min()
    df["breakout_up"] = (df["close"] > hh).astype(int)
    df["breakout_dn"] = (df["close"] < ll).astype(int)
    df["slope_ema_fast"] = df["ema_fast"].diff()
    return df.replace([np.inf,-np.inf], np.nan).dropna().reset_index(drop=True)

def latest_slice(symbol: str, marco: str, limit: int = 600):
    raw = fetch_ohlc(symbol, marco, limit=limit)
    df = compute_indicators(raw)
    return df, df.iloc[-1]
