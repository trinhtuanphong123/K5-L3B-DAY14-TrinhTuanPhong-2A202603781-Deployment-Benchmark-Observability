"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Yêu cầu:
  • Đọc REDIS_URL từ config
  • App vẫn phải KHỞI ĐỘNG ĐƯỢC khi Redis chưa sẵn sàng (đừng ping Redis lúc import)
  • redis_healthy() dùng cho GET /ready: Redis không kết nối được → False
"""
import redis

from app.config import settings

# redis.from_url không mở kết nối; kết nối chỉ xảy ra khi gọi lệnh đầu tiên.
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except (redis.exceptions.RedisError, OSError):
        return False
