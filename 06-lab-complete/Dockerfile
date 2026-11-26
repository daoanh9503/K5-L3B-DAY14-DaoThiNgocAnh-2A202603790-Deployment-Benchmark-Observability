# ============================================================
# Production Dockerfile — multi-stage
#   Stage builder: cài dependencies vào virtualenv /opt/venv
#   Stage runtime: image slim sạch, chỉ copy venv + code, chạy bằng user non-root
# ============================================================

# ── Stage 1: builder ──────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# requirements trước code → sửa code không phải cài lại thư viện (layer cache)
COPY requirements.txt .
RUN pip install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app/ ./app/
COPY --chown=app:app utils/ ./utils/

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4)" || exit 1

# `exec` thay thế shell → uvicorn là PID 1, nhận SIGTERM trực tiếp khi `docker stop`.
# Shell chỉ dùng để đọc ${PORT} do Railway/Render cấp.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
