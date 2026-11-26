"""
Cost guard (tiêu chí 8).

Cộng dồn chi phí LLM của từng API key theo ngày vào Redis (`cost:<hash>:<YYYY-MM-DD>`).
Tổng chi phí trong ngày đạt DAILY_BUDGET_USD → HTTP 402. Sang ngày mới là key mới,
nên budget tự reset; key cũ tự hết hạn sau 2 ngày.
"""
import time

from fastapi import HTTPException

from app.config import settings
from app.rate_limiter import key_id
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _cost_key(api_key: str) -> str:
    return f"cost:{key_id(api_key)}:{time.strftime('%Y-%m-%d', time.gmtime())}"


def estimate_tokens(text: str) -> int:
    """Mock LLM không trả số token → ước lượng ~2 token / từ."""
    return max(1, len(text.split()) * 2)


def check_budget(api_key: str) -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    spent = float(r.get(_cost_key(api_key)) or 0.0)
    budget = settings.daily_budget_usd
    if spent >= budget:
        raise HTTPException(
            status_code=402,
            detail={"error": "Daily budget exceeded", "spent_usd": round(spent, 6),
                    "budget_usd": budget, "resets": "00:00 UTC"},
        )


def record_cost(api_key: str, input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000 * PRICE_INPUT_PER_1K
            + output_tokens / 1000 * PRICE_OUTPUT_PER_1K)
    key = _cost_key(api_key)
    pipe = r.pipeline(transaction=True)
    pipe.incrbyfloat(key, cost)          # cộng dồn atomic, an toàn khi nhiều worker
    pipe.expire(key, 2 * 24 * 3600)
    pipe.execute()
    return cost
