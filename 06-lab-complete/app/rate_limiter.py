"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)

Thuật toán: sliding window log trên Redis sorted set (score = thời điểm request).
Redis lỗi → 503 (fail-closed: không đếm được thì không cho gọi LLM).
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def _redis_key(api_key: str) -> str:
    return "rl:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    now = time.time()
    rkey = _redis_key(key)
    member = f"{now:.6f}-{uuid.uuid4().hex[:8]}"
    try:
        pipe = r.pipeline(transaction=True)
        pipe.zremrangebyscore(rkey, 0, now - WINDOW_SECONDS)
        pipe.zadd(rkey, {member: now})
        pipe.zcard(rkey)
        pipe.expire(rkey, WINDOW_SECONDS + 1)
        _, _, count, _ = pipe.execute()
        retry_after = None
        if count > limit:
            r.zrem(rkey, member)
            oldest = r.zrange(rkey, 0, 0, withscores=True)
            retry_after = (
                max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
                if oldest
                else WINDOW_SECONDS
            )
    except redis.exceptions.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "limit": limit,
                "window_seconds": WINDOW_SECONDS,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
    return None
