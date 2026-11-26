"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402

Tổng toàn hệ thống theo ngày UTC, key cost:daily:YYYY-MM-DD (hết hạn sau 2 ngày).
Redis lỗi khi kiểm tra budget → 503 (fail-closed).
"""
import logging
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent.cost_guard")

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
COST_KEY_TTL_SECONDS = 2 * 24 * 3600


def _daily_key() -> str:
    return "cost:daily:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        spent = float(r.get(_daily_key()) or 0.0)
    except redis.exceptions.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable")
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "budget_exceeded",
                "spent_usd": round(spent, 6),
                "budget_usd": settings.daily_budget_usd,
                "resets": "00:00 UTC",
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    try:
        key = _daily_key()
        pipe = r.pipeline(transaction=True)
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, COST_KEY_TTL_SECONDS)
        pipe.execute()
    except redis.exceptions.RedisError:
        logger.error(
            "record_cost_failed",
            extra={"fields": {"event": "record_cost_failed", "cost_usd": cost}},
        )
    return cost
