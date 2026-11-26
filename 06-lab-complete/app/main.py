"""
Production AI Agent — Part 6 Final Project.

Chạy:   uvicorn app.main:app --workers 2
Chấm:   python check_production_ready.py
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ──────────────────────────────────────────────────────────
# Structured logging (tiêu chí 10): mỗi dòng log là 1 JSON object
# ──────────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        # json.dumps tự escape dấu " và xuống dòng → luôn là JSON hợp lệ trên 1 dòng
        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("agent")
    log.handlers[:] = [handler]
    log.setLevel(settings.log_level)
    log.propagate = False  # không lặp lại qua root logger
    return log


logger = _setup_logging()


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


# ──────────────────────────────────────────────────────────
# Lifespan: startup + graceful shutdown (tiêu chí 11)
#
# Không tự đăng ký signal handler cho SIGTERM: uvicorn đã có sẵn. Khi nhận SIGTERM,
# uvicorn ngừng nhận kết nối mới, chờ request đang chạy xong, rồi mới chạy phần
# sau `yield` bên dưới để dọn dẹp, cuối cùng thoát với exit code 0.
# ──────────────────────────────────────────────────────────
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("startup", environment=settings.environment, port=settings.port,
              rate_limit_per_minute=settings.rate_limit_per_minute,
              daily_budget_usd=settings.daily_budget_usd,
              api_key_configured=bool(settings.agent_api_key))
    if not settings.agent_api_key:
        log_event("AGENT_API_KEY is not set — /ask will reject every request",
                  level=logging.WARNING)
    yield
    log_event("shutdown", detail="in-flight requests finished, closing Redis pool")
    r.close()


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


# ──────────────────────────────────────────────────────────
# Middleware: log mỗi request (không log nội dung câu hỏi, không log API key)
# ──────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log_event("request", method=request.method, path=request.url.path,
              status=response.status_code,
              ms=round((time.perf_counter() - start) * 1000, 1))
    return response


# ──────────────────────────────────────────────────────────
# Xử lý lỗi: mã lỗi rõ ràng, không lộ stack trace ra client
# ──────────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "msg": e["msg"]}
              for e in exc.errors()]
    return JSONResponse(status_code=422,
                        content={"error": "Invalid request", "details": errors})


@app.exception_handler(redis.RedisError)
async def redis_unavailable(request: Request, exc: redis.RedisError):
    log_event("redis_error", level=logging.ERROR, path=request.url.path,
              error=type(exc).__name__)
    return JSONResponse(status_code=503,
                        content={"error": "Service temporarily unavailable"},
                        headers={"Retry-After": "5"})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Stack trace chỉ nằm trong log server, client chỉ thấy thông báo chung
    logger.error("unhandled_error", exc_info=exc,
                 extra={"fields": {"path": request.url.path}})
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ──────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=100)


@app.get("/")
def root():
    return {"app": "Production AI Agent", "environment": settings.environment,
            "endpoints": ["/health", "/ready", "POST /ask"]}


@app.get("/health")
def health():
    """Liveness (tiêu chí 4): process còn sống → luôn 200, KHÔNG phụ thuộc Redis.
    Nếu /health fail khi Redis chết, platform sẽ restart agent liên tục mà không
    giải quyết được gì."""
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}


@app.get("/ready")
def ready():
    """Readiness (tiêu chí 5): chỉ nhận traffic khi kết nối được Redis, không thì 503
    để load balancer tạm ngừng gửi request vào instance này."""
    if not redis_healthy():
        return JSONResponse(status_code=503,
                            content={"ready": False, "redis": "unreachable"})
    return {"ready": True, "redis": "ok"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)          # 429 khi vượt RATE_LIMIT_PER_MINUTE (tiêu chí 7)
    check_budget(api_key)              # 402 khi hết DAILY_BUDGET_USD (tiêu chí 8)

    answer = llm_ask(body.question)

    cost = record_cost(api_key, estimate_tokens(body.question), estimate_tokens(answer))
    log_event("llm_call", question_chars=len(body.question),
              answer_chars=len(answer), cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
