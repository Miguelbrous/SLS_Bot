from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class StrategyDefaults(BaseModel):
    id: str
    interval_seconds: int
    server: str
    leverage: int
    max_errors: int
    signature_secret: Optional[str]
    signature_header: str


class Settings(BaseSettings):
    slsbot_mode: str = Field("test", env="SLSBOT_MODE")
    slsbot_config: Path = Field(Path("./config/config.json"), env="SLSBOT_CONFIG")
    strategy_id: str = Field("scalp_rush_v1", env="STRATEGY_ID")
    strategy_interval_seconds: int = Field(30, env="STRATEGY_INTERVAL_SECONDS")
    strategy_server: str = Field("http://127.0.0.1:8080", env="STRATEGY_SERVER")
    strategy_leverage: int = Field(20, env="STRATEGY_LEVERAGE")
    strategy_max_errors: int = Field(5, env="STRATEGY_MAX_ERRORS")
    webhook_shared_secret: Optional[str] = Field(None, env="WEBHOOK_SHARED_SECRET")
    webhook_signature_header: str = Field("X-Webhook-Signature", env="WEBHOOK_SIGNATURE_HEADER")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"

    @property
    def strategy(self) -> StrategyDefaults:
        return StrategyDefaults(
            id=self.strategy_id,
            interval_seconds=self.strategy_interval_seconds,
            server=self.strategy_server,
            leverage=self.strategy_leverage,
            max_errors=self.strategy_max_errors,
            signature_secret=self.webhook_shared_secret,
            signature_header=self.webhook_signature_header,
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
