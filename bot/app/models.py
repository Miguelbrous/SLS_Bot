from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class Health(BaseModel):
    ok: bool
    time: str
    pid: int


class ServiceState(BaseModel):
    active: bool
    detail: str | None = None


class StatusResponse(BaseModel):
    services: Dict[str, ServiceState]
    bot: Dict[str, Any]


class LogResponse(BaseModel):
    lines: List[str]


class DecisionsResponse(BaseModel):
    rows: List[dict]


class SymbolPnL(BaseModel):
    symbol: str
    pnl_eur: float
    fees_eur: float | None = None
    trades: int | None = None


class PnLDailyItem(BaseModel):
    day: str
    pnl_eur: float
    from_fills: bool = False
    symbols: List[SymbolPnL] = Field(default_factory=list)


class PnLDailyResponse(BaseModel):
    days: List[PnLDailyItem]


class AlertItem(BaseModel):
    name: str
    count: int
    severity: str
    hint: str
    latest: Optional[str] = None


class AlertsResponse(BaseModel):
    alerts: List[AlertItem]
    summary: Dict[str, Any]
