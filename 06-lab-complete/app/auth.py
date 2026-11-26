"""
API Key authentication (tiêu chí 6).

  • Client gửi header  X-API-Key: <key>
  • Key phải trùng biến môi trường AGENT_API_KEY
  • Thiếu hoặc sai key → HTTP 401
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

# auto_error=False: tự trả 401 thay vì để FastAPI trả 403 khi thiếu header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency cho FastAPI — dùng trong /ask: Depends(verify_api_key)."""
    expected = settings.agent_api_key
    # compare_digest: so sánh thời gian hằng, tránh đoán key qua thời gian phản hồi.
    # expected rỗng (quên đặt AGENT_API_KEY) → từ chối tất cả.
    # So sánh bytes: compare_digest với str chứa ký tự non-ASCII ném TypeError → 500 thay vì 401.
    if not api_key or not expected or not hmac.compare_digest(
        api_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
