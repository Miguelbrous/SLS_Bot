from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time, timezone
from typing import List, Literal, Optional, Sequence

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _ensure_tzaware(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo:
        return dt
    return dt.replace(tzinfo=timezone.utc)


@dataclass
class NewsPulse:
    sentiment: float = 0.0
    latest_title: str | None = None
    latest_url: str | None = None
    latest_ts: datetime | None = None
    ttl_minutes: int = 45

    def age_minutes(self, now: datetime) -> float | None:
        ts = _ensure_tzaware(self.latest_ts)
        if not ts:
            return None
        delta = now - ts
        return delta.total_seconds() / 60.0

    def is_fresh(self, now: datetime, max_age_minutes: Optional[int] = None) -> bool:
        limit = max_age_minutes if max_age_minutes is not None else self.ttl_minutes
        if limit <= 0:
            return False
        age = self.age_minutes(now)
        return age is not None and age <= limit

    def direction(self, threshold: float = 0.05) -> str:
        if self.sentiment >= threshold:
            return "bullish"
        if self.sentiment <= -threshold:
            return "bearish"
        return "neutral"


POSITIVE_KEYWORDS = {
    "adoption",
    "approval",
    "bull",
    "etf",
    "growth",
    "launch",
    "partnership",
    "record",
    "surge",
    "upgrade",
}

NEGATIVE_KEYWORDS = {
    "ban",
    "bear",
    "breach",
    "crackdown",
    "dip",
    "down",
    "hack",
    "lawsuit",
    "regulation",
    "shutdown",
}


def summarize_news_items(items: Sequence[dict], now: datetime, ttl_minutes: int = 45) -> NewsPulse:
    """Heuristica simple para estimar sentimiento + frescura de noticias."""
    if not items:
        return NewsPulse(ttl_minutes=ttl_minutes)

    scores: List[float] = []
    latest_ts: datetime | None = None
    latest_title: str | None = None
    latest_url: str | None = None

    for raw in items:
        title = (raw.get("title") or "").strip()
        url = raw.get("url")
        published_at = raw.get("published_at") or raw.get("ts") or raw.get("time")
        if isinstance(published_at, (int, float)):
            ts = datetime.fromtimestamp(float(published_at), tz=timezone.utc)
        elif isinstance(published_at, str):
            try:
                ts = datetime.fromisoformat(published_at)
            except ValueError:
                ts = None
        else:
            ts = published_at
        ts = _ensure_tzaware(ts) or now

        if (not latest_ts) or ts > latest_ts:
            latest_ts = ts
            latest_title = title
            latest_url = url

        base_sentiment = raw.get("sentiment")
        if isinstance(base_sentiment, (int, float)):
            scores.append(float(base_sentiment))
            continue

        lower = title.lower()
        pos_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in lower)
        neg_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in lower)
        if pos_hits or neg_hits:
            score = (pos_hits - neg_hits) / max(pos_hits + neg_hits, 1)
            scores.append(score)

    sentiment = sum(scores) / len(scores) if scores else 0.0
    sentiment = max(-1.0, min(1.0, sentiment))
    return NewsPulse(
        sentiment=sentiment,
        latest_title=latest_title,
        latest_url=latest_url,
        latest_ts=latest_ts,
        ttl_minutes=ttl_minutes,
    )


@dataclass
class SessionGuardConfig:
    name: str
    timezone: str
    open_time: str
    pre_open_minutes: int = 30
    post_open_minutes: int = 30
    wait_for_news_minutes: int = 45
    require_news_to_resume: bool = True
    risk_multiplier_after_news: float = 0.7
    close_positions_minutes: int = 10

    @classmethod
    def from_dict(cls, data: dict) -> "SessionGuardConfig":
        return cls(
            name=data.get("name") or "Unnamed Session",
            timezone=data.get("timezone") or "UTC",
            open_time=data.get("open_time") or "00:00",
            pre_open_minutes=int(data.get("pre_open_minutes") or 30),
            post_open_minutes=int(data.get("post_open_minutes") or 30),
            wait_for_news_minutes=int(data.get("wait_for_news_minutes") or 45),
            require_news_to_resume=bool(data.get("require_news_to_resume", True)),
            risk_multiplier_after_news=float(data.get("risk_multiplier_after_news") or 0.7),
            close_positions_minutes=int(data.get("close_positions_minutes") or 10),
        )

    def open_time_obj(self) -> time:
        hour, minute = (self.open_time or "00:00").split(":")
        return time(hour=int(hour), minute=int(minute))


@dataclass
class SessionGuardResult:
    session_name: str
    state: Literal["pre_open", "news_wait", "news_ready"]
    reason: str
    block_trade: bool
    should_close_positions: bool
    minutes_to_open: float | None
    minutes_since_open: float | None
    risk_multiplier: float
    news_direction: str | None
    news_is_fresh: bool
    window_start_ts: float
    window_end_ts: float

    def to_metadata(self) -> dict:
        return {
            "session_name": self.session_name,
            "state": self.state,
            "reason": self.reason,
            "block_trade": self.block_trade,
            "should_close_positions": self.should_close_positions,
            "minutes_to_open": self.minutes_to_open,
            "minutes_since_open": self.minutes_since_open,
            "risk_multiplier": self.risk_multiplier,
            "news_direction": self.news_direction,
            "news_is_fresh": self.news_is_fresh,
            "window_start_ts": self.window_start_ts,
            "window_end_ts": self.window_end_ts,
        }


class MarketSessionGuard:
    def __init__(self, configs: Sequence[SessionGuardConfig]):
        self.sessions = list(configs)

    def evaluate(self, now: datetime, news_pulse: NewsPulse | None = None) -> Optional[SessionGuardResult]:
        if not self.sessions or ZoneInfo is None:
            return None

        candidates: List[SessionGuardResult] = []
        for cfg in self.sessions:
            res = self._evaluate_single(cfg, now, news_pulse)
            if res:
                candidates.append(res)

        if not candidates:
            return None

        def _score(res: SessionGuardResult) -> float:
            if res.minutes_to_open is not None and res.minutes_to_open >= 0:
                return res.minutes_to_open
            if res.minutes_since_open is not None:
                return res.minutes_since_open
            return float("inf")

        return min(candidates, key=_score)

    def _evaluate_single(
        self, cfg: SessionGuardConfig, now: datetime, news_pulse: NewsPulse | None
    ) -> Optional[SessionGuardResult]:
        tz = ZoneInfo(cfg.timezone) if ZoneInfo else timezone.utc
        local_now = now.astimezone(tz)
        open_time = cfg.open_time_obj()
        pre_delta = timedelta(minutes=max(cfg.pre_open_minutes, 0))
        post_delta = timedelta(minutes=max(cfg.post_open_minutes, 0))

        for day_offset in (-1, 0, 1):
            open_dt = datetime.combine(local_now.date() + timedelta(days=day_offset), open_time, tzinfo=tz)
            window_start = open_dt - pre_delta
            window_end = open_dt + post_delta
            if window_start <= local_now <= window_end:
                return self._build_result(cfg, local_now, open_dt, window_start, window_end, now, news_pulse)
        return None

    def _build_result(
        self,
        cfg: SessionGuardConfig,
        local_now: datetime,
        open_dt_local: datetime,
        window_start_local: datetime,
        window_end_local: datetime,
        now_utc: datetime,
        news_pulse: NewsPulse | None,
    ) -> SessionGuardResult:
        before_open = local_now < open_dt_local
        minutes_to_open = (open_dt_local - local_now).total_seconds() / 60.0 if before_open else None
        minutes_since_open = (local_now - open_dt_local).total_seconds() / 60.0 if not before_open else None
        news_is_fresh = news_pulse.is_fresh(now_utc, cfg.wait_for_news_minutes) if news_pulse else False
        news_direction = news_pulse.direction() if news_pulse else None

        if before_open:
            reason = f"{cfg.name}: pre-apertura ({minutes_to_open:.0f}m) -> cerrar o reducir exposicion"
            return SessionGuardResult(
                session_name=cfg.name,
                state="pre_open",
                reason=reason,
                block_trade=True,
                should_close_positions=True,
                minutes_to_open=minutes_to_open,
                minutes_since_open=None,
                risk_multiplier=0.0,
                news_direction=None,
                news_is_fresh=False,
                window_start_ts=window_start_local.astimezone(timezone.utc).timestamp(),
                window_end_ts=window_end_local.astimezone(timezone.utc).timestamp(),
            )

        if cfg.require_news_to_resume and not news_is_fresh:
            reason = f"{cfg.name}: apertura reciente -> esperando noticia fresca (<= {cfg.wait_for_news_minutes}m)"
            return SessionGuardResult(
                session_name=cfg.name,
                state="news_wait",
                reason=reason,
                block_trade=True,
                should_close_positions=False,
                minutes_to_open=None,
                minutes_since_open=minutes_since_open,
                risk_multiplier=0.0,
                news_direction=news_direction,
                news_is_fresh=False,
                window_start_ts=window_start_local.astimezone(timezone.utc).timestamp(),
                window_end_ts=window_end_local.astimezone(timezone.utc).timestamp(),
            )

        reason = f"{cfg.name}: apertura reciente, solo trading si la noticia es {news_direction or 'neutral'}"
        return SessionGuardResult(
            session_name=cfg.name,
            state="news_ready",
            reason=reason,
            block_trade=False,
            should_close_positions=False,
            minutes_to_open=None,
            minutes_since_open=minutes_since_open,
            risk_multiplier=max(cfg.risk_multiplier_after_news, 0.1),
            news_direction=news_direction,
            news_is_fresh=news_is_fresh,
            window_start_ts=window_start_local.astimezone(timezone.utc).timestamp(),
            window_end_ts=window_end_local.astimezone(timezone.utc).timestamp(),
        )
