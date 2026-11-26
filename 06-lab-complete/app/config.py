"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Các biến (đều có mặc định hợp lý khi chạy local):
  PORT, ENVIRONMENT, AGENT_API_KEY, REDIS_URL,
  RATE_LIMIT_PER_MINUTE, DAILY_BUDGET_USD, LOG_LEVEL

Không hard-code secret: AGENT_API_KEY mặc định rỗng (app sẽ từ chối mọi request /ask).
Giá trị không ép kiểu được (vd PORT=abc) → ValueError ngay lúc khởi động (fail fast).
"""
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )
    daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "1.0"))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())


settings = Settings()
