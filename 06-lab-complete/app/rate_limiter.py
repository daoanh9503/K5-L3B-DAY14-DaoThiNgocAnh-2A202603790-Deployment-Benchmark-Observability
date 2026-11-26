"""
Rate limiting (tiêu chí 7) — sliding window trên Redis sorted set.

Mỗi API key có một sorted set `ratelimit:<hash>`, mỗi phần tử là một request,
score = thời điểm (giây). Vì state nằm trong Redis nên mọi worker / instance dùng
chung, và vẫn còn sau khi restart agent.
"""
import hashlib
import math
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def key_id(api_key: str) -> str:
    """Không lưu API key gốc trong Redis — chỉ lưu hash ngắn của nó."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    redis_key = f"ratelimit:{key_id(key)}"
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex}"

    # MULTI/EXEC: 4 lệnh chạy nguyên khối, các worker không chen ngang nhau
    pipe = r.pipeline(transaction=True)
    pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)  # bỏ request cũ hơn 60s
    pipe.zadd(redis_key, {member: now})                         # ghi request này
    pipe.zcard(redis_key)                                       # đếm trong cửa sổ
    pipe.expire(redis_key, WINDOW_SECONDS + 1)                  # tự dọn key khi không dùng
    _, _, count, _ = pipe.execute()

    if count > limit:
        r.zrem(redis_key, member)  # request bị từ chối không tính vào hạn mức
        oldest = r.zrange(redis_key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, math.ceil(oldest[0][1] + WINDOW_SECONDS - now))
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded", "limit": limit,
                    "window_seconds": WINDOW_SECONDS, "retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after),
                     "X-RateLimit-Limit": str(limit),
                     "X-RateLimit-Remaining": "0"},
        )
