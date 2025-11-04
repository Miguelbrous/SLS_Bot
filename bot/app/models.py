from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal


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


class DashboardIssue(BaseModel):
    severity: Literal["info", "warning", "error"]
    message: str


class DashboardMetric(BaseModel):
    name: str
    value: float | None = None
    formatted: str | None = None
    delta: float | None = None
    delta_formatted: str | None = None


class DashboardTrade(BaseModel):
    ts: str
    symbol: str
    timeframe: Optional[str] = None
    side: Optional[str] = None
    pnl: Optional[float] = None
    confidence: Optional[float] = None
    risk_pct: Optional[float] = None
    reason: Optional[str] = None


class DashboardSummaryResponse(BaseModel):
    level: Literal["ok", "warning", "error"]
    summary: str
    mode: Optional[str] = None
    updated_at: str
    metrics: List[DashboardMetric] = Field(default_factory=list)
    issues: List[DashboardIssue] = Field(default_factory=list)
    alerts: List[AlertItem] = Field(default_factory=list)
    recent_trades: List[DashboardTrade] = Field(default_factory=list)
    recent_pnl: List[DashboardTrade] = Field(default_factory=list)


class DashboardCandle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class DashboardTradeMarker(BaseModel):
    time: int
    symbol: str
    timeframe: Optional[str] = None
    side: Optional[str] = None
    label: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    risk_pct: Optional[float] = None


class DashboardChartResponse(BaseModel):
    candles: List[DashboardCandle]
    trades: List[DashboardTradeMarker]


class ArenaNote(BaseModel):
    strategy_id: str
    note: str
    author: Optional[str] = None
    ts: str


class ArenaNotePayload(BaseModel):
    strategy_id: str
    note: str
    author: Optional[str] = None


class ArenaNotesResponse(BaseModel):
    notes: List[ArenaNote]
