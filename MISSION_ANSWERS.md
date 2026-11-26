# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (≥ 5, kèm dòng code trong `develop/app.py`)
1. **Secret hardcode trong code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-..."` và `DATABASE_URL` chứa mật khẩu `password123`. Push lên GitHub là lộ key ngay, và secret nằm mãi trong lịch sử git dù xoá file sau đó.
2. **Log ra secret** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` đưa key vào log. Log thường được gửi tới hệ thống tập trung, nhiều người đọc được.
3. **Dùng `print()` thay vì logging có cấu trúc** (dòng 33, 38): không có level, không có timestamp, không parse được bằng máy, và in nguyên câu hỏi/câu trả lời của user (rủi ro lộ dữ liệu).
4. **Config cố định trong code** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500`. Muốn đổi giữa dev/staging/production phải sửa code và deploy lại.
5. **Không có health check / readiness** (dòng 42): platform không biết agent đã treo để restart, load balancer không biết khi nào được gửi traffic vào.
6. **Bind `host="localhost"`** (dòng 51): chỉ nhận kết nối từ chính máy đó; chạy trong container thì bên ngoài không gọi vào được. Production phải bind `0.0.0.0`.
7. **Port cố định 8000** (dòng 52): Railway/Render cấp port qua biến `PORT`, app không đọc thì platform không route được.
8. **`reload=True` luôn bật** (dòng 53): chế độ dev, tốn tài nguyên theo dõi file và có thể tự restart giữa chừng trong production.
9. **Không xử lý shutdown**: không có lifespan/xử lý SIGTERM, khi platform tắt container thì request đang chạy có thể bị cắt ngang.

### Exercise 1.2: Kết quả gọi bản develop
```text
$ python app.py
Starting agent on localhost:8000...
INFO:     Will watch for changes in these directories: ['/mnt/c/Users/ADMIN/K5-L3-Day14-Deployment-Agent-Benchmark-Observability/01-localhost-vs-production/develop']
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [1519] using WatchFiles
INFO:     Started server process [1521]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
INFO:     127.0.0.1:55096 - "POST /ask?question=Hello HTTP/1.1" 200 OK
INFO:     127.0.0.1:59304 - "POST /ask HTTP/1.1" 422 Unprocessable Content
INFO:     127.0.0.1:58356 - "GET /health HTTP/1.1" 404 Not Found
```
- `POST /ask?question=Hello` → **200 OK**.
- Log cho thấy thêm: `reload=True` bật trình theo dõi file (`Started reloader process ... using WatchFiles`) ngay cả khi chạy thật.
- Gửi JSON body `{"question":"Hello"}` → **422**, vì bản develop nhận `question` qua query string.
- `GET /health` → **404**, bản develop không có health check.
- Log server in ra `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`, tức secret bị lộ trong log.
- **Nhận xét:** app chạy được, nhưng chưa production-ready: lộ secret, không health check, chỉ chạy trên localhost với port cố định.

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config  | Hardcode trong code (`DEBUG`, `MAX_TOKENS`, port) | Đọc từ env vars qua `config.py` (12-Factor) | Một image chạy được ở mọi môi trường, đổi cấu hình không cần sửa code hay build lại |
| Secrets | Key + mật khẩu DB ghi thẳng trong code, còn in ra log | Lấy từ env (`.env` không commit), không log secret | Tránh lộ key qua GitHub và log; đổi key không cần deploy lại code |
| Health check | Không có (`/health` → 404) | `/health` (liveness) + `/ready` (readiness) → 200 | Platform tự restart khi agent treo; load balancer chỉ gửi traffic khi agent sẵn sàng |
| Logging | `print()` tự do, in cả secret | Log JSON có time/level, chỉ ghi metadata (độ dài câu hỏi) | Máy parse/tìm kiếm được trên Loki/Datadog, không lộ dữ liệu nhạy cảm |
| Host / Port | `localhost:8000` cố định | `0.0.0.0` + `PORT` từ env | Chạy được trong container và trên cloud nơi platform cấp port |
| Reload / Debug | `reload=True` luôn bật | Chỉ bật khi `DEBUG=true` | Production ổn định, không tự restart ngoài ý muốn |
| Shutdown | Đột ngột, không xử lý | Graceful: `lifespan` dọn dẹp khi nhận SIGTERM | Không cắt ngang request đang chạy khi deploy hoặc scale down |

### Quan sát thêm khi chạy bản production
- **Lỗi thứ tự logging:** khi thiếu `OPENAI_API_KEY`, `config.py:45` gọi `logging.warning()` lúc import. Lệnh này tự tạo cấu hình log mặc định (mức WARNING), nên `logging.basicConfig(...)` ở `app.py:28` không còn tác dụng, và mọi log JSON mức INFO bị ẩn. Chạy với `OPENAI_API_KEY=dummy` thì log JSON hiện đúng.
- **SIGTERM vs Ctrl+C:** gửi SIGTERM (`pkill -TERM -f "python app.py"`, giống cách Railway/Render/`docker stop` làm), app in `Agent shutting down gracefully...` → `Shutdown complete`, thoát sạch. Bấm Ctrl+C (SIGINT) trên Python 3.14 + uvicorn 0.30 thì shutdown vẫn xong, nhưng sau đó in thêm traceback `KeyboardInterrupt` vô hại.
- **`handle_sigterm` chạy cuối cùng:** dòng `Received SIGTERM` xuất hiện sau `Finished server process`, vì uvicorn đặt bộ xử lý tín hiệu riêng, tắt server xong mới chuyển tín hiệu cho handler của app. Vì vậy dọn dẹp nên đặt trong `lifespan`, không đặt trong handler đó.
- **Log chưa phải JSON hợp lệ:** trường `msg` chứa chuỗi JSON lồng mà không escape dấu `"`, nên công cụ đọc log sẽ parse lỗi. Cần một JSON formatter dùng `json.dumps` cho cả dòng (sẽ áp dụng ở Part 6).

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:** `python:3.11` (dòng 8, `FROM python:3.11`). Đây là bản Python **đầy đủ** chạy trên Debian, kèm sẵn nhiều công cụ build (gcc, git, header thư viện…). Tiện vì cài gì cũng được, nhưng nặng: riêng bước tải base image mất 75.3s, có một layer 237 MB, và image cuối nặng 1.67 GB. Production nên dùng bản `-slim`.
2. **Working directory:** `/app` (dòng 11, `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy trong thư mục này, nên `COPY app.py .` đặt file vào `/app/app.py` và `CMD ["python", "app.py"]` tìm thấy file. Nếu thư mục chưa có, `WORKDIR` tự tạo.
3. **Vì sao `COPY requirements.txt` trước `COPY` code:** Vì Docker build từng dòng thành từng layer và lưu cache lại. Khi build lại, nếu một dòng và các file nó copy không đổi, Docker dùng lại cache. Nhưng nếu một layer thay đổi thì mọi layer phía sau đều phải build lại. `requirements.txt` ít khi đổi, còn code thì đổi liên tục. Đặt requirements + `pip install` **trước** code thì khi chỉ sửa `app.py`, layer `pip install` vẫn `CACHED`, chỉ các bước copy code chạy lại, build mất vài giây. Nếu `COPY . .` đứng trước thì mỗi lần sửa một dòng code đều phải cài lại toàn bộ thư viện (18.4s ở bài này, lâu hơn nhiều với thư viện nặng). Bằng chứng: lần build stack ở Exercise 2.4, mọi layer đều `CACHED` và build chỉ mất 4.3s.
4. **CMD vs ENTRYPOINT:**
   - `CMD` là lệnh **mặc định**, bị **thay thế** khi gõ lệnh khác sau tên image. Thử: `docker run --rm my-agent:develop python --version` → container chỉ in phiên bản Python, không bật server, vì `python --version` đã thay `CMD ["python", "app.py"]`.
   - `ENTRYPOINT` là lệnh **luôn chạy**. Phần gõ sau tên image chỉ được **nối thêm** làm tham số. Muốn đổi phải dùng `docker run --entrypoint ...`.
   - Dùng chung: `ENTRYPOINT ["python"]` + `CMD ["app.py"]` → `docker run image` chạy `python app.py`; `docker run image other.py` chạy `python other.py`.
   - Dockerfile develop chỉ dùng `CMD`, nên dễ ghi đè để debug (vd `docker run -it my-agent:develop bash`).
### Exercise 2.2: Kết quả gọi container
```text
$ docker run --rm -d --name agent-dev -p 8000:8000 my-agent:develop
b4519d04e04bfb17de4373cafc89b78e4ad181f0594e139add0ff2f3bd8e5e26

$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"status":"ok","uptime_seconds":14.4,"container":true}

$ docker images my-agent:develop
IMAGE              ID             DISK USAGE   CONTENT SIZE
my-agent:develop   3b1c9c886162       1.67GB          426MB
```
- `/ask` và `/health` đều trả **200** từ trong container.
- Build lần đầu mất 148.8s, trong đó tải base image `python:3.11` mất 75.3s (một layer nặng 237 MB).
- Image develop: **1.67 GB** dung lượng trên đĩa (DISK USAGE), **426 MB** dung lượng nén (CONTENT SIZE).

### Exercise 2.3: Image size comparison (đo bằng `docker images`)
```text
$ docker images | grep my-agent
my-agent:advanced    b00968bd4d1f        240MB         57.4MB
my-agent:develop     3b1c9c886162       1.67GB          426MB
```

| Image | Base | DISK USAGE | CONTENT SIZE (nén) | Thời gian build lần đầu |
|---|---|---:|---:|---:|
| `my-agent:develop` | `python:3.11` | 1.67 GB (~1670 MB) | 426 MB | 148.8 s |
| `my-agent:advanced` | `python:3.11-slim`, multi-stage | 240 MB | 57.4 MB | 93.9 s |

- Develop: 1670 MB
- Production: 240 MB
- Difference: giảm (1670 − 240) / 1670 ≈ **85.6%** (theo dung lượng nén: (426 − 57.4) / 426 ≈ 86.5%)

**Multi-stage hoạt động thế nào** (`02-docker/production/Dockerfile`):
- **Stage 1 — `builder`** (`FROM python:3.11-slim AS builder`): cài công cụ build `gcc`, `libpq-dev` (bước `apt-get install`, 47.8s), rồi `pip install --user -r requirements.txt` để thư viện nằm gọn trong `/root/.local`. Stage này chỉ để **build**, không dùng để deploy.
- **Stage 2 — `runtime`** (`FROM python:3.11-slim AS runtime`): bắt đầu lại từ một image slim **sạch**, tạo user `appuser` (non-root), rồi chỉ lấy đúng thứ cần để **chạy**:
  - `COPY --from=builder /root/.local /home/appuser/.local`: thư viện đã cài sẵn từ stage 1
  - `main.py` và `utils/mock_llm.py`
  - Thêm `HEALTHCHECK`, `USER appuser`, `CMD uvicorn ... --workers 2`.

**Vì sao image nhỏ hơn ~85%:**
1. **Base slim thay vì bản đầy đủ:** `python:3.11-slim` chỉ có phần tối thiểu để chạy Python, còn `python:3.11` kèm cả bộ công cụ build và thư viện hệ thống.
2. **Image cuối chỉ gồm stage cuối:** gcc, `libpq-dev`, cache của `apt` ở stage `builder` **bị bỏ lại**, không đi vào image `runtime`. Chỉ thư mục `.local` chứa package đã cài được copy sang.
3. **Copy có chọn lọc:** chỉ copy `main.py` và `mock_llm.py`, không `COPY . .` cả repo.

**Lợi ích thêm ngoài dung lượng:** ít package hơn nên ít lỗ hổng bảo mật hơn; chạy bằng user non-root nên nếu app bị chiếm quyền thì kẻ tấn công không có quyền root trong container; image nhỏ nên pull/deploy nhanh hơn (57.4 MB so với 426 MB khi tải).

**Stage 1 (`builder`, dòng 16–29) làm gì:** dựng môi trường để *cài* thư viện. Stage này cài công cụ biên dịch `gcc` và `libpq-dev` bằng `apt-get` (bước `[builder 3/5]`, mất 47.8 s), rồi `pip install --user` toàn bộ `requirements.txt` vào `/root/.local` (bước `[builder 5/5]`). Image của stage này chỉ dùng trong lúc build, không đem đi deploy.

**Stage 2 (`runtime`, dòng 36–72) làm gì:** dựng image để *chạy*. Stage này bắt đầu lại từ một base `python:3.11-slim` sạch, tạo user `appuser`, và chỉ chép sang đúng thư mục thư viện đã cài xong từ Stage 1 (`[runtime 4/8] COPY --from=builder /root/.local ...`), cùng `main.py` và `utils/mock_llm.py`. Sau đó stage này chuyển sang `USER appuser`, thêm `HEALTHCHECK` và chạy uvicorn.

**Vì sao image nhỏ hơn:**
1. **Image cuối chỉ chứa những gì có trong stage cuối.** `gcc`, `libpq-dev`, cache của `apt` và các file tạm khi build chỉ tồn tại ở Stage 1 nên bị bỏ lại. Stage 2 chỉ nhận kết quả là các package đã cài.
2. **Base `slim` thay cho bản đầy đủ.** `python:3.11` mang theo trình biên dịch, header và nhiều thư viện hệ thống mà app không cần khi chạy. `python:3.11-slim` chỉ giữ phần tối thiểu để chạy Python. Đây là phần đóng góp lớn nhất vào mức giảm 85.6%.
3. **`pip install --no-cache-dir`** không lưu cache tải gói vào image.

**Lợi ích phụ:** ít phần mềm thừa thì ít lỗ hổng bảo mật hơn, ví dụ kẻ tấn công không có sẵn `gcc` trong container. Image nhỏ thì kéo về và khởi động nhanh hơn khi deploy hoặc scale. Chạy bằng `appuser` thay vì root nên nếu app bị chiếm quyền, kẻ tấn công cũng bị giới hạn quyền trong container.

### Exercise 2.4: Docker Compose stack
Chạy bằng `docker compose -p k5-day14-docker up -d --build` trong `02-docker/production/` (đã `touch .env.local`).

**Services được start** (`docker compose -p k5-day14-docker ps`):
```text
NAME                       IMAGE                   SERVICE   STATUS                PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up (healthy)          8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up                    0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up (healthy)          6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          redis     Up (healthy)          6379/tcp
```

**Sơ đồ service:**
```text
                 Host (laptop)
                      │  :80 / :443  (chỉ nginx mở cổng ra ngoài)
                      ▼
 ┌──────────────── network "internal" (bridge) ────────────────┐
 │   nginx  ──proxy_pass──▶  agent:8000  ──▶  redis:6379        │
 │  (reverse proxy,          (FastAPI,    └──▶ qdrant:6333      │
 │   rate limit 10r/s,        uvicorn                           │
 │   security headers)        2 workers)                        │
 └──────────────────────────────────────────────────────────────┘
   volumes: redis_data, qdrant_data (dữ liệu còn sau khi restart)
```
- Các service gọi nhau bằng **tên service** (`agent`, `redis`, `qdrant`) qua DNS nội bộ của network `internal`.
- `agent` chỉ khởi động khi `redis` và `qdrant` đã **healthy** (`depends_on: condition: service_healthy`). Log `up` cho thấy redis và qdrant Healthy trước, rồi agent và nginx mới Started.
- `agent`, `redis`, `qdrant` không publish cổng ra host (cột PORTS chỉ có `8000/tcp`, `6379/tcp`, không có `0.0.0.0:`). Bên ngoài chỉ vào được qua nginx.

**Kết quả test qua Nginx:**
```text
$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":83.4,"version":"2.0.0","timestamp":"2026-11-26T13:40:48.083727"}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```
- Header `Server: nginx` (không lộ version) và 3 header bảo mật chứng tỏ request đi qua Nginx rồi mới tới agent.
- Lần build image agent chỉ mất 4.3s vì mọi layer đều `CACHED` từ lần build `my-agent:advanced` trước, minh hoạ đúng câu 3 của Exercise 2.1.
- Cảnh báo `the attribute version is obsolete`: Compose v2 bỏ qua trường `version:`, không ảnh hưởng.

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6
- Nền tảng: **Railway** (Exercise 3.1), deploy thư mục `06-lab-complete/` (agent Part 6), không phải app mẫu `03-cloud-deployment/`.
- URL: https://k5-l3b-day14-daothingocanh-2a202603790-deploymen-production.up.railway.app
- Service: agent (build từ `Dockerfile` multi-stage theo `railway.toml`) + **Redis** của Railway. Biến `AGENT_API_KEY`, `REDIS_URL=${{Redis.REDIS_URL}}`, `ENVIRONMENT=production` đặt trên Railway, không ghi trong code. Chi tiết: [DEPLOYMENT.md](DEPLOYMENT.md).
- Screenshot: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

**Kết quả 4 lệnh tự kiểm CP6:**
```text
health        : 200
ready         : 200
ask no key    : 401
ask with key  : 200
```
(thêm: key sai → 401, body sai `{"oops":1}` → 422)

**Sự cố khi deploy và cách sửa:**
1. Lần build đầu (Railway tự build từ GitHub) **lỗi**: chưa đặt Root Directory nên Railway build từ gốc repo (dùng `Dockerfile` khác ở gốc). Sửa: đặt Root Directory = `06-lab-complete`.
2. `/ask` có key trả **500** thay vì 200. Log: `TypeError: comparing strings with non-ASCII characters is not supported` ở `app/auth.py`. Nguyên nhân: giá trị key truyền qua stdin bị PowerShell 5.1 chèn ký tự BOM, và `hmac.compare_digest(str, str)` ném lỗi khi chuỗi có ký tự non-ASCII. Sửa cả hai: đặt lại key sạch, và so sánh dạng bytes (`compare_digest(api_key.encode(), expected.encode())`). Nhờ vậy client gửi header lạ cũng nhận 401 chứ không làm app lỗi 500.

### So sánh `railway.toml` và `render.yaml`
| Khía cạnh | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Cấu hình **một service** (build + deploy) | **Blueprint cả hạ tầng**: khai báo nhiều service (web + Key Value/Redis) |
| Cách build | `builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `dockerfilePath`, `rootDir: 06-lab-complete` |
| Thư mục gốc | Không khai trong file, đặt Root Directory trên service (hoặc chạy `railway up` trong thư mục) | `rootDir` ghi ngay trong file |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Render tự restart, không cấu hình trong file |
| Redis | **Không** khai trong file, phải tự thêm database và tham chiếu `${{Redis.REDIS_URL}}` | Khai luôn service `keyvalue`, `REDIS_URL` lấy bằng `fromService ... property: connectionString` |
| Secret | Không có cơ chế trong file, đặt bằng dashboard/CLI (`railway variable set`) | `generateValue: true` (Render tự sinh `AGENT_API_KEY`) hoặc `sync: false` (điền tay khi tạo) |
| Biến thường | Đặt ngoài file | Ghi trực tiếp (`ENVIRONMENT`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`) |

**Vì sao khác:** Railway coi file config là phần *build/deploy của một service*, còn hạ tầng (database, biến, domain) quản lý trên project bằng dashboard/CLI. Render Blueprint là *Infrastructure as Code* đầy đủ: một file mô tả mọi service và cách chúng nối với nhau, nên tạo lại toàn bộ stack chỉ bằng một lần "New Blueprint". Đổi lại, `railway.toml` ngắn và linh hoạt hơn, còn `render.yaml` tái lập được hạ tầng chính xác hơn.

### Exercise 3.3: Pipeline Cloud Run (3–5 dòng, đọc `cloudbuild.yaml` + `service.yaml`)
1. **Trigger:** push lên `main` kích hoạt Cloud Build chạy `cloudbuild.yaml`.
2. **Test → Build → Push:** bước `test` chạy `pytest` trong `python:3.11-slim`; chỉ khi pass mới `docker build` image gắn 2 tag (`$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cache), rồi `docker push` lên Container Registry (`waitFor` bảo đảm đúng thứ tự).
3. **Deploy:** `gcloud run deploy` lấy đúng image `$COMMIT_SHA` lên Cloud Run region `asia-southeast1`: public, 1–10 instance (min 1 để tránh cold start), 512 MiB/1 CPU, timeout 60 s; `ENVIRONMENT=production` qua env, `OPENAI_API_KEY` lấy từ **Secret Manager** chứ không hardcode.
4. **`service.yaml`** là bản IaC (Knative) của chính service đó (`gcloud run services replace`): `containerConcurrency: 80`, autoscaling 1–10, resource requests/limits, secret `OPENAI_API_KEY` + `AGENT_API_KEY` từ Secret Manager, `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready` — Cloud Run chỉ đưa traffic vào khi instance đã sẵn sàng.

## Part 4: API Security

### Exercise 4.1: API Key authentication (bản develop)
Chạy: `AGENT_API_KEY=secret-key-123 python app.py` trong `04-api-gateway/develop/`.

```text
# Log server
INFO:     127.0.0.1:36220 - "POST /ask HTTP/1.1" 401 Unauthorized   ← không có header X-API-Key
INFO:     127.0.0.1:47846 - "POST /ask HTTP/1.1" 403 Forbidden      ← X-API-Key: wrong
INFO:     127.0.0.1:50550 - "POST /ask HTTP/1.1" 200 OK             ← X-API-Key: secret-key-123
```

- **Key được check ở đâu:** hàm `verify_api_key` (`develop/app.py` dòng 39–54) đọc header `X-API-Key` qua `APIKeyHeader`, được gắn vào `/ask` bằng `Depends(verify_api_key)` (dòng 70). `/` và `/health` không gắn nên vẫn public.
- **Sai key thì sao:** thiếu key → **401** ("Missing API key"); có key nhưng sai → **403** ("Invalid API key"). Request bị chặn trước khi chạy vào hàm `/ask`, không tốn tiền gọi LLM. (Part 6 yêu cầu cả hai trường hợp đều trả 401.)
- **Rotate key:** key đọc từ biến môi trường `AGENT_API_KEY` (dòng 35), nên đổi key = đặt giá trị mới trên platform rồi restart, không sửa code. Hạn chế: chỉ có 1 key, đổi là mọi client cũ bị chặn ngay; muốn rotate không gián đoạn thì cho phép 2 key cùng lúc (cũ + mới) trong một khoảng chuyển tiếp.
- **Lưu ý:** dòng 91 `print(f"API Key: {API_KEY}")` in key ra log khi khởi động, đây lại là anti-pattern lộ secret giống Part 1.

Output phía client (`curl -i`):
```text
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2: JWT authentication (bản production)
Chạy `python app.py` trong `04-api-gateway/production/`, tài khoản `student` / `demo123`.

```text
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<đã che>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9, ...}}
```

**JWT flow:**
1. Client gửi username/password tới `POST /auth/token`. Server kiểm tra (`authenticate_user`) rồi ký token bằng `JWT_SECRET`, thuật toán HS256 (`create_token`).
2. Token gồm 3 phần `header.payload.signature`. Payload chứa `sub` (username), `role`, `iat` (lúc tạo), `exp` (hết hạn sau 60 phút). Payload chỉ mã hoá base64, **ai cũng đọc được**, nên không bỏ mật khẩu vào token.
3. Mỗi request gửi `Authorization: Bearer <token>`. `verify_token` kiểm tra chữ ký và hạn dùng: sai chữ ký hoặc hết hạn → 401. Đúng → lấy luôn `username`, `role` từ token, **không cần tra database**, nên nhiều instance đều xác thực được (stateless).
4. So với API key: JWT có hạn dùng, mang theo role (phân quyền user/admin), và lộ token thì chỉ hiệu lực tối đa 60 phút.

### Exercise 4.3: Rate limiting
```text
$ for i in $(seq 1 15); do ... curl -X POST /ask -H "Authorization: Bearer $TOKEN" ...; done
--- Request 1 → 9:   HTTP/1.1 200 OK
--- Request 10
HTTP/1.1 429 Too Many Requests
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":27}}
--- Request 11 → 15: HTTP/1.1 429 Too Many Requests (cùng nội dung)
```
- Request thứ 10 của vòng lặp đã bị 429 vì trước đó đã gọi `/ask` 1 lần ở Exercise 4.2: 1 + 9 = 10 request/phút là hết hạn mức.
- **Thuật toán:** **sliding window log**. Mỗi user có một `deque` lưu timestamp các request; mỗi lần check thì bỏ các timestamp cũ hơn 60 giây, nếu còn ≥ `max_requests` thì trả 429 (`rate_limiter.py` dòng 29–60).
- **Limit:** user **10 req/phút**, admin **100 req/phút** (`rate_limiter.py` dòng 86–87).
- **Bypass cho admin:** `app.py` dòng 141 chọn `rate_limiter_admin` nếu `role == "admin"` (tài khoản `teacher`), role lấy từ JWT nên không giả mạo được nếu không có `JWT_SECRET`.
- Response 429 kèm `retry_after_seconds` (và header `Retry-After`, `X-RateLimit-*`) để client biết khi nào thử lại.
- **Hạn chế:** state nằm trong RAM của process → restart là mất, và khi chạy nhiều instance thì mỗi instance đếm riêng (user được nhân hạn mức theo số instance). Part 6 chuyển state sang Redis.

### Exercise 4.4: Cost guard implementation
**Cách `cost_guard.py` hoạt động:**
- `check_budget(user_id)` chạy **trước** khi gọi LLM: tổng chi phí cả hệ thống ≥ $10/ngày → **503**; chi phí của user ≥ $1/ngày → **402 Payment Required**; dùng ≥ 80% thì ghi log cảnh báo.
- `record_usage(user_id, input_tokens, output_tokens)` chạy **sau** khi gọi LLM: tính chi phí theo giá mỗi 1K token input/output rồi cộng dồn cho user và cho toàn hệ thống.
- Reset theo ngày: mỗi bản ghi gắn với ngày `%Y-%m-%d`, sang ngày mới thì tạo bản ghi mới.

**Rate limit vs cost guard:** rate limit chặn **số lần gọi** trong một khoảng thời gian, cost guard chặn **số tiền** tiêu. Cần cả hai vì một user gọi chậm (không bị rate limit) nhưng mỗi câu rất dài vẫn có thể đốt hết budget, còn cost guard thì không chống được việc spam nhiều request rẻ làm quá tải server.

**Implement với Redis** (budget $10/tháng/user):
```python
import redis
from datetime import datetime

r = redis.Redis()

def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"        # mỗi user, mỗi tháng một key → tự "reset" đầu tháng

    current = float(r.get(key) or 0)              # đã tiêu bao nhiêu trong tháng
    if current + estimated_cost > 10:             # vượt $10 → từ chối (app trả 402)
        return False

    r.incrbyfloat(key, estimated_cost)            # cộng dồn, atomic trong Redis
    r.expire(key, 32 * 24 * 3600)                 # tự xoá sau 32 ngày, không rác Redis
    return True
```
- Lưu trong Redis thay vì RAM nên không mất khi restart và mọi instance dùng chung một con số.
- Hạn chế: `GET` rồi mới `INCRBYFLOAT` là 2 bước, hai request đồng thời có thể cùng lọt qua; muốn chặt chẽ thì `INCRBYFLOAT` trước, nếu vượt thì trừ lại (hoặc dùng Lua script/`MULTI`).

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (bản develop)
```text
INFO:     127.0.0.1:55786 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:55788 - "GET /ready HTTP/1.1" 200 OK
```
- **Liveness — `/health`** (`develop/app.py` dòng 104): trả lời "process còn sống không". Chỉ nên fail khi process hỏng thật (treo, hết bộ nhớ). Platform thấy fail → **restart** container.
- **Readiness — `/ready`** (dòng 147): trả lời "đã sẵn sàng nhận traffic chưa". Trả **503** khi `_is_ready = False` (đang khởi động, đang tắt, hoặc phụ thuộc như Redis/DB chưa kết nối). Load balancer thấy 503 → **tạm ngừng gửi traffic** vào instance đó, nhưng không restart.
- Tách hai cái vì: nếu Redis chết mà `/health` cũng fail thì platform restart liên tục mà không giải quyết được gì; đúng ra chỉ `/ready` fail để ngừng nhận request, `/health` vẫn 200.

### Exercise 5.2: Graceful shutdown
Test: gửi `POST /ask` rồi `kill -TERM <pid>` ngay sau đó.
```text
2026-11-26 14:17:22,025 INFO ✅ Agent is ready!
INFO:     Shutting down                                              ← nhận SIGTERM, ngừng nhận request mới
INFO:     127.0.0.1:37746 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK   ← request đang chạy vẫn hoàn thành
INFO:     Waiting for application shutdown.
2026-11-26 14:18:06,236 INFO 🔄 Graceful shutdown initiated...       ← lifespan: _is_ready=False, chờ in-flight
2026-11-26 14:18:06,236 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3664]
2026-11-26 14:18:06,237 INFO Received signal 15 — uvicorn will handle graceful shutdown
```
- Request gửi ngay trước SIGTERM vẫn trả **200**, không bị cắt ngang.
- Thứ tự: uvicorn nhận SIGTERM → **ngừng nhận kết nối mới** → **chờ request đang chạy xong** → chạy phần shutdown của `lifespan` (đặt `_is_ready = False`, chờ `_in_flight_requests` về 0 tối đa 30s, đóng kết nối) → thoát.
- Dòng `Received signal 15` của `handle_sigterm` in ra **cuối cùng**, sau `Finished server process`: uvicorn tự cài bộ xử lý tín hiệu riêng, xử lý shutdown xong mới gọi lại handler của app. Vì vậy logic dọn dẹp nên đặt trong `lifespan`, không đặt trong `handle_sigterm` (giống quan sát ở Part 1).
- Tại sao quan trọng: mỗi lần deploy/scale down, platform gửi SIGTERM. Không graceful thì user đang chờ câu trả lời sẽ bị lỗi giữa chừng.

### Exercise 5.3: Stateless design
- `production/app.py` dòng 59–89: session và history lưu trong Redis (`session:<id>`, TTL 3600s) qua `save_session` / `load_session`, không lưu trong biến Python.
- **Vì sao state trong RAM hỏng khi scale:** mỗi instance là một process riêng với RAM riêng. Request 1 của user vào instance A (history lưu ở RAM của A), request 2 được Nginx gửi sang instance B → B không thấy history → mất ngữ cảnh. Ngoài ra instance restart/bị kill là mất sạch state.
- Đưa state ra Redis thì instance nào cũng đọc/ghi cùng một chỗ → có thể thêm/bớt/kill instance tuỳ ý.

### Exercise 5.4: Load balancing
Chạy trong `05-scaling-reliability/production/`:
`docker compose -p k5-day14-scaling up -d --build --scale agent=3` → 3 container agent + redis + nginx (cổng 8080).

- Nginx đứng trước, chia request lần lượt (round-robin) cho 3 instance agent qua DNS nội bộ của service `agent`. Kết quả ở 5.5 cho thấy thứ tự `700c00 → 55a841 → 2c87c0 → 700c00 → 55a841`: đúng kiểu xoay vòng.
- Các agent không mở cổng ra ngoài, chỉ đi qua Nginx; mỗi agent giới hạn 0.5 CPU / 256 MB.
- Nếu một instance chết, Nginx chuyển request sang các instance còn lại; vì state nằm trong Redis nên user không mất hội thoại.

### Exercise 5.5: Test stateless
```text
$ python test_stateless.py
Session ID: c6b72ba8-04b2-4a4e-bb4a-d69b37c01b5b

Request 1: [instance-700c00]  Q: What is Docker?
Request 2: [instance-55a841]  Q: Why do we need containers?
Request 3: [instance-2c87c0]  Q: What is Kubernetes?
Request 4: [instance-700c00]  Q: How does load balancing work?
Request 5: [instance-55a841]  Q: What is Redis used for?
------------------------------------------------------------
Total requests: 5
Instances used: {'instance-55a841', 'instance-700c00', 'instance-2c87c0'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  ...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...

✅ Session history preserved across all instances via Redis!
```
**Giải thích kết quả:**
- 5 request trong **cùng một session** được xử lý bởi **cả 3 instance khác nhau** (round-robin của Nginx).
- Dù vậy history vẫn đủ **10 tin nhắn** (5 câu hỏi + 5 câu trả lời) theo đúng thứ tự: mỗi instance đều ghi vào và đọc ra từ cùng một key `session:<id>` trong Redis.
- Nếu history lưu trong RAM, instance-55a841 ở request 2 sẽ không thấy câu hỏi 1 (nằm trong RAM của instance-700c00) → hội thoại bị đứt. Đây là lý do agent phải **stateless**: state ở Redis, instance chỉ xử lý.
- Script không tự tắt instance nào; nhưng vì không instance nào giữ state riêng, kill một instance (`docker stop`) cũng không làm mất session.

## Part 6: Final Project

### Output `python check_production_ready.py` (phần "📋 Checklist Deliverable")
Chạy đầy đủ (có Docker) trong WSL2, Python 3.14.4, `os.name=posix`, trong `06-lab-complete/`:
```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```
Một số số đo trong lần chạy: image **268 MB**; rate limit trả 429 sau 5 request (`RATE_LIMIT_PER_MINUTE=5`) và vẫn 429 sau khi restart agent (state trong Redis); cost guard trả 402 ở request thứ 2 (budget 0.000001 USD); `docker stop` thoát với exit code 0 trong 0.9s.

## AI log
| # | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra thế nào |
|---|--------|---------|------------------------------|
| 1 | CP1: nhờ Claude giải thích log khi chạy bản production và viết câu trả lời Part 1 | Danh sách anti-pattern kèm dòng code, bảng so sánh, giải thích lỗi thứ tự logging và SIGTERM | Tự chạy cả hai bản trong WSL, kiểm tra 200/422/404 bằng curl, gửi SIGTERM bằng `pkill` để xác nhận graceful shutdown |
| 2 | CP2: nhờ Claude viết phần giải thích Exercise 2.3 (Stage 1, Stage 2, vì sao image nhỏ hơn) | Đoạn giải thích multi-stage dựa trên Dockerfile và log build của mình | Tự build 2 image, đo bằng `docker images` (1.67 GB vs 240 MB), đối chiếu các bước `[builder]` / `[runtime]` trong log build |
| 3 | CP5: nhờ Claude viết code các TODO trong `06-lab-complete/` | Claude viết phần lớn code Part 6: `config.py` (đọc env), `auth.py` (X-API-Key → 401), `rate_limiter.py` (sliding window bằng Redis sorted set → 429), `cost_guard.py` (cộng chi phí theo ngày trong Redis → 402), `redis_client.py`, `main.py` (log JSON, `/health`, `/ready`, lifespan shutdown, xử lý lỗi), `Dockerfile` multi-stage, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`; nới phiên bản trong `requirements.txt` để cài được trên Python 3.14 | Tự chạy `python check_production_ready.py` đầy đủ (có Docker, WSL2) đạt **PASS 12/12**; đọc hiểu từng file, đặc biệt vì sao `/health` vẫn 200 còn `/ready` trả 503 khi mất Redis, vì sao state rate limit phải ở Redis, vì sao không tự viết handler SIGTERM |
| 4 | CP0 + công cụ: nhờ Claude Code trỏ remote về bản fork, tạo khung file này, cài Node.js, GitHub CLI, Railway CLI, viết script `.claude/scripts/check_progress.py` và 2 agent kiểm tiến độ / push code | Remote `origin`/`upstream`, công cụ CLI, script liệt kê mục còn thiếu theo SUBMISSION.md | Tự đăng nhập `railway login`, `gh auth login`; tự chạy script và đối chiếu với SUBMISSION.md |
| 5 | CP6: nhờ Claude deploy agent Part 6 lên Railway bằng CLI và viết `DEPLOYMENT.md` + mục Part 3 | Thêm Redis, đặt biến (`AGENT_API_KEY` sinh ngẫu nhiên, lưu ngoài repo), đặt Root Directory `06-lab-complete`, `railway up`; sửa lỗi 500 ở `auth.py` (so sánh key dạng bytes); bảng so sánh `railway.toml`/`render.yaml` và mô tả pipeline Cloud Run | Tự kiểm 4 lệnh CP6 trên URL public (200/200/401/200), thêm key sai → 401, body sai → 422; đọc log Railway để hiểu lỗi `TypeError` non-ASCII |
| 6 | CP7 + CP8: nhờ Claude (và 1 agent con chạy song song) chạy load test, eval, sửa `KNOWLEDGE_BASE`, dựng stack Docker, chạy Locust headless, chụp Grafana/Jaeger/Prometheus và viết `BENCHMARK_REPORT.md` | Số liệu trong `reports/*.json`, `benchmark-results/*.csv`; sửa lỗi `Dockerfile` của stack production (`useradd -d /app` làm thiếu `uvicorn`); báo cáo có ghi chú các điểm nhiễu (slow_0 chạy cùng lúc Docker build, scale_1 thực tế 2 instance) | Mọi số trong báo cáo đối chiếu từ file JSON/CSV và log; eval cuối 23/23, 0 regression; xem lại từng ảnh chụp trước khi commit |
