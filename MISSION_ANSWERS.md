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
1. Base image: 
2. Working directory: 
3. Vì sao `COPY requirements.txt` trước `COPY . .`: 
4. CMD vs ENTRYPOINT: 

### Exercise 2.2: Kết quả gọi container
```text
```

### Exercise 2.3: Image size comparison (đo bằng `docker images`)
- Develop: [X] MB
- Production: [Y] MB
- Difference: [Z]%

### Exercise 2.4: Docker Compose stack
- Sơ đồ service:
- Kết quả test qua Nginx:

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6
- Nền tảng: 
- URL: 
- Screenshot: `screenshots/`

### So sánh `railway.toml` và `render.yaml`

### Exercise 3.3: Pipeline Cloud Run (3–5 dòng, đọc `cloudbuild.yaml` + `service.yaml`)

## Part 4: API Security

### Exercise 4.1-4.3: Test results (`curl -i`, đã che token)
```text
401:
200:
429:
```

### Exercise 4.4: Cost guard implementation

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
- Liveness vs readiness:
- Graceful shutdown:
- Stateless + Redis:
- Kết quả `python test_stateless.py`:

## Part 6: Final Project

### Output `python check_production_ready.py` (phần "📋 Checklist Deliverable")
```text
```

## AI log
| # | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra thế nào |
|---|--------|---------|------------------------------|
| 1 | Nhờ Claude Code đọc repo và hướng dẫn các bước làm lab; làm CP0 | Lộ trình CP0–CP8; trỏ remote về bản fork, tạo khung file này | Tự kiểm `git remote -v`, đối chiếu với CHECKPOINTS.md |
| 2 | CP1: nhờ Claude giải thích log khi chạy bản production và viết câu trả lời Part 1 | Danh sách anti-pattern kèm dòng code, bảng so sánh, giải thích lỗi thứ tự logging và SIGTERM | Tự chạy cả hai bản trong WSL, kiểm tra 200/422/404 bằng curl, gửi SIGTERM bằng `pkill` để xác nhận graceful shutdown |
