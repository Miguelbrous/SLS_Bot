from typing import Dict, Optional

from pybit.unified_trading import HTTP


class BybitClient:
    """
    Cliente Bybit (Unified Trading v5) usando el SDK oficial `pybit`.
    Acepta endpoints custom (demo/paper trading) además de testnet/mainnet.
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str, account_type: str = "UNIFIED"):
        normalized = (base_url or "").strip()
        lowered = normalized.lower()
        is_testnet = "testnet" in lowered
        http_kwargs = {
            "api_key": api_key,
            "api_secret": api_secret,
            "testnet": is_testnet,
        }

        if normalized:
            init_params = HTTP.__init__.__code__.co_varnames  # type: ignore[attr-defined]
            if "endpoint" in init_params:
                http_kwargs["endpoint"] = normalized  # pybit >= 5.12 permite endpoint custom
            elif "domain" in init_params:
                http_kwargs["domain"] = normalized

        self.session = HTTP(**http_kwargs)
        self.account_type = account_type

    # ----------------- UTIL: PRECIO -----------------
    def get_mark_price(self, symbol: str) -> Optional[float]:
        """Devuelve un precio de referencia (mark/last) para 'symbol' (linear)."""
        try:
            r = self.session.get_tickers(category="linear", symbol=symbol)
            if r.get("retCode") != 0:
                return None
            lst = r.get("result", {}).get("list", [])
            if not lst:
                return None
            it = lst[0]
            price_s = it.get("markPrice") or it.get("lastPrice")
            return float(price_s) if price_s not in (None, "", " ") else None
        except Exception:
            return None

    # ----------------- BALANCE -----------------
    def get_balance(self) -> float:
        """Devuelve balance de USDT como float. Tolerante a respuestas vacías y prueba UNIFIED/CONTRACT."""
        def _f(x) -> float:
            try:
                if x in (None, "", " "):
                    return 0.0
                return float(x)
            except Exception:
                return 0.0

        for acc in [self.account_type, "UNIFIED", "CONTRACT"]:
            try:
                resp = self.session.get_wallet_balance(accountType=acc, coin="USDT")
                if resp.get("retCode") != 0:
                    continue
                lst = resp.get("result", {}).get("list", [])
                if not lst:
                    continue
                coins = lst[0].get("coin", [])
                for c in coins:
                    if c.get("coin") == "USDT":
                        v = (
                            _f(c.get("availableToWithdraw")) or
                            _f(c.get("availableBalance")) or
                            _f(c.get("walletBalance")) or
                            _f(c.get("equity"))
                        )
                        return v
            except Exception:
                continue
        return 0.0

    # ----------------- LEVERAGE -----------------
    def set_leverage(self, symbol: str, buy: int, sell: int, category: str = "linear"):
        """Setea el apalancamiento para el símbolo. Ignora 'leverage not modified'."""
        resp = self.session.set_leverage(
            category=category,
            symbol=symbol,
            buyLeverage=str(buy),
            sellLeverage=str(sell),
        )
        rc = resp.get("retCode")
        msg = str(resp.get("retMsg", "")).lower()
        if rc not in (0, None) and "not modified" not in msg:
            raise RuntimeError(resp)
        return resp

    # ----------------- CLOSED PnL / FILLS -----------------
    def get_closed_pnl(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict:
        """
        Envuelve `get_closed_pnl` para poder sincronizar fills reales.
        Devuelve el payload crudo de Bybit para que el caller maneje paginación.
        """
        params: Dict[str, object] = {
            "category": category,
            "limit": limit,
        }
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if cursor:
            params["cursor"] = cursor
        return self.session.get_closed_pnl(**params)
