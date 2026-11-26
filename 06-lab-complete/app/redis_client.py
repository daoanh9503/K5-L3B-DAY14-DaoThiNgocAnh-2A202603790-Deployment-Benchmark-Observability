"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

redis.from_url() KHÔNG mở kết nối ngay, chỉ tạo connection pool. Kết nối thật chỉ
xảy ra ở lệnh đầu tiên → app vẫn khởi động được khi Redis chưa sẵn sàng.
Timeout ngắn để /ready trả 503 nhanh thay vì treo khi Redis chết.
"""
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready: True nếu ping được Redis, False nếu không kết nối được."""
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
