# Deployment Information

## Public URL
https://k5-l3b-day14-daothingocanh-2a202603790-deploymen-production.up.railway.app

## Platform
**Railway** (project `aware-charisma`, environment `production`, region `iad`)

| Service | Nguồn | Vai trò |
|---|---|---|
| `K5-L3B-Day14-...` (agent) | `06-lab-complete/` (Dockerfile multi-stage, `railway.toml`) | FastAPI agent Part 6 |
| `Redis` | Railway Redis database | State của rate limit + cost guard |

- Root Directory của service agent: `06-lab-complete` → Railway đọc `railway.toml` (builder `DOCKERFILE`, `healthcheckPath = "/health"`).
- Deploy bằng Railway CLI: `cd 06-lab-complete && railway up`. Service cũng nối với repo GitHub (nhánh `main`) nên mỗi lần push sẽ build lại.

## Test Commands

Đặt biến trước (PowerShell / bash):
```bash
BASE=https://k5-l3b-day14-daothingocanh-2a202603790-deploymen-production.up.railway.app
# AGENT_API_KEY: key đã đặt trên Railway (không ghi trong repo)
```

### 4 lệnh tự kiểm CP6 (chỉ in mã HTTP, không lộ key)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

### Kết quả đo được (2026-11-26)
| Request | Mong đợi | Thực tế |
|---|---:|---:|
| `GET /health` | 200 | **200** — `{"status":"ok","uptime_seconds":13.8}` |
| `GET /ready` (Redis kết nối được) | 200 | **200** |
| `POST /ask` không có key | 401 | **401** |
| `POST /ask` key sai | 401 | **401** |
| `POST /ask` có key đúng | 200 | **200** — `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) ..."}` |
| `POST /ask` body sai (`{"oops":1}`) | 4xx | **422** |

### Health Check
```bash
curl $BASE/health
# {"status":"ok","uptime_seconds":...}
```

### API Test (with authentication)
```bash
curl -X POST $BASE/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set
Đặt trên Railway (tab **Variables** của service agent), **không** ghi trong code hay repo:

| Biến | Giá trị |
|---|---|
| `AGENT_API_KEY` | secret ngẫu nhiên 32 ký tự (chỉ lưu trên Railway và máy cá nhân) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` — tham chiếu tới service Redis |
| `ENVIRONMENT` | `production` |
| `PORT` | Railway tự cấp; `CMD` trong Dockerfile đọc `${PORT:-8000}` |

Các biến còn lại (`RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, …) dùng giá trị mặc định trong `app/config.py`, xem `.env.example`.

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
