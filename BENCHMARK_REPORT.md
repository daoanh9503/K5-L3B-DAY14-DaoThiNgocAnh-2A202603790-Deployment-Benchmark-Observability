# Benchmark & Observability Report — Day 14

> Mọi con số lấy từ report JSON trong `reports/` và CSV trong `benchmark-results/`, không ước lượng.

**Họ tên:** Đào Thị Ngọc Anh
**Ngày chạy:** 2026-11-26
**Môi trường:** Laptop Windows 11 Pro, AMD Ryzen 5 5500U (6 nhân / 12 luồng), RAM 15 GB. Part 7 Bước 1 chạy bằng Python 3.13 (venv Windows). Bước 2 chạy trên Docker Desktop (WSL2 backend).

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM mất khoảng 120–180 ms + retrieval 20 ms. 500 ms chừa đủ chỗ cho jitter mà người dùng vẫn thấy "tức thì". Đây cũng là mặc định `--slo-p95-ms` của `load_test.py` |
| Error rate `/ask` | < 2 % | Upstream LLM tự lỗi khoảng 1% (`MOCK_ERROR_RATE=0.01`). 2% cho phép biến động ngẫu nhiên nhưng bắt được khi lỗi tăng gấp đôi |
| Accuracy trên golden dataset | ≥ 85 % | Ngưỡng của quality gate trong CI (Exercise 7.3): thấp hơn thì chặn merge. Bản phát hành cuối đạt 100% |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

`--requests 300`, file `reports/load_v2_c{1,10,50,100}.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.85 | 212.6 | 242.3 | 1708.3 | 1.33 % | ✅ PASS |
| 10 | 34.48 | 216.1 | 493.4 | 1709.0 | 1.33 % | ✅ PASS |
| 50 | 34.22 | 748.2 | 4343.1 | 6114.4 | 0.33 % | ❌ FAIL (p95) |
| 100 | 30.45 | 1958.9 | 6379.6 | 7578.0 | 2.00 % | ❌ FAIL (p95, error) |

**Nhận xét:** RPS tăng gần tuyến tính từ 1 lên 10 (3.85 → 34.48, gấp khoảng 9 lần) vì mock LLM là `asyncio.sleep`: chờ không tốn CPU nên 10 request chạy song song được. Từ 10 lên 50 và 100, RPS **đứng ở khoảng 30–34** còn p50/p95 tăng vọt: server đã bão hoà (một process uvicorn, middleware đo metrics, log JSON từng request, cùng chạy trên laptop với load generator). Request thêm vào chỉ xếp hàng, nên latency tăng theo định luật Little (latency ≈ concurrency / throughput: 100 / 30 ≈ 3.3 s, khớp avg 2.7 s). Điểm làm việc tốt nhất là khoảng **10 concurrent**, qua ngưỡng này phải scale ngang.

### 2.2 Tail latency

`--requests 300 --concurrency 20`, file `reports/load_v2_slow_{0,0.03,0.1}.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 611.1 | 1527.5 | 3484.7 |
| 0.03 (mặc định) | 281.1 | 564.4 | 1723.0 |
| 0.1 | 546.5 | 1777.4 | 2213.3 |

> ⚠️ Lần chạy `MOCK_SLOW_RATE=0` bị nhiễu: nó chạy **đúng lúc Docker đang build stack Part 7 Bước 2** trên cùng máy, nên CPU bị chiếm và RPS chỉ còn 32 (so với 68.6 của lần 0.03). Số trong bảng là số thật trong file, nhưng không phản ánh riêng tác động của `MOCK_SLOW_RATE`. So sánh dưới đây dùng hai lần chạy không bị nhiễu (0.03 và 0.1).

**Nhận xét:** Tăng tỉ lệ request chậm từ 3% lên 10% làm **avg chỉ tăng khoảng 1.9 lần** (281 → 547 ms), nhưng **p95 tăng 3.1 lần** (564 → 1777 ms) vì khi hơn 5% request bị chậm thêm 1.5 s thì chính p95 rơi vào nhóm chậm. p99 vốn đã nằm trong nhóm chậm từ mức 3%. Percentile (p95/p99) nhạy nhất với request chậm. Average trộn 90% request nhanh với 10% request rất chậm thành một con số "trông vẫn ổn", che mất việc cứ 10 người dùng thì có 1 người chờ gần 2 giây. Vì vậy SLO đặt theo p95/p99, không đặt theo average.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3 % (1/23) | 91.3 % (21/23) | **100 % (23/23)** |
| Avg tokens / câu | 56.7 | 109.1 | 113.7 |
| Tổng cost (USD) | 0.000398 | 0.000762 | 0.000790 |
| Cost / câu đúng (USD) | 0.00039795 | 0.00003627 | 0.00003436 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%, 0 regression) | PASS (≥ 100%, 0 regression) |

File: `reports/eval_v1.json`, `reports/eval_v2.json` (baseline v1), `reports/eval_v2_fixed.json` (baseline v2, `--min-accuracy 1.0`).

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 ("JWT khác gì API key…") | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu kích hoạt bởi từ khoá `jwt` vào `KNOWLEDGE_BASE`: JWT là token có chữ ký số, chứa thời điểm hết hạn; API key cố định, không tự hết hạn |
| scaling-03 ("Kubernetes HPA scale dựa trên…") | `cpu`, `memory`, `custom metrics` | Thêm tài liệu kích hoạt bởi `hpa` / `kubernetes`: HPA scale pod theo CPU, memory hoặc custom metrics |

Chỉ sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và chép sang `production/utils/mock_llm.py` cho stack Docker), không sửa `golden_dataset.jsonl`. Trước khi thêm, đã grep golden dataset: chỉ đúng 2 câu này chứa `jwt` / `kubernetes` / `hpa`, nên tài liệu mới không "cướp" retrieval của câu khác. Eval cuối xác nhận 0 regression.

**Quality gate trong CI:** `run_eval.py` trả **exit code 1** khi accuracy < `--min-accuracy` hoặc có câu regression so với `--baseline`. Job CI chỉ cần chạy agent rồi gọi:
```bash
python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85 --baseline reports/eval_main.json
```
Bước đó fail thì job fail, và nếu đặt job làm *required status check* cho nhánh `main` thì PR không merge được.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 thêm bước retrieval nên prompt dài gần gấp đôi (56.7 → 109.1 token/câu), tổng cost gấp khoảng 1.9 lần và mỗi request chậm thêm khoảng 20 ms retrieval cộng 0.2 ms/token. Nhưng accuracy tăng từ 4% lên 91%, nên **cost / câu đúng giảm khoảng 11 lần** (0.000398 → 0.0000363 USD). So hai phiên bản phải dùng cost / câu đúng, vì v1 rẻ hơn mỗi câu nhưng gần như mọi câu trả lời đều vô dụng. Sửa KB tăng thêm 4.6 token/câu (+3.7% cost) nhưng cost / câu đúng còn giảm tiếp.

---

### 3.1 Exercise 7.1: Metrics của agent

Output `GET /metrics` (develop v2, sau 1 request):
```text
http_requests_total{method="POST",route="/ask",status="200"} 1.0                 ← Counter (chỉ tăng)
agent_in_flight_requests 0.0                                                    ← Gauge (lên xuống)
http_request_duration_seconds_bucket{le="0.3",method="POST",route="/ask"} 1.0   ← Histogram (bucket)
agent_question_length_chars_count 1.0                                           ← metric mới thêm
agent_question_length_chars_sum 5.0
```
- **Nếu label `route` dùng URL thật** (`request.url.path`): mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`…) tạo **một time series mới** cho mỗi tổ hợp method × status, và cả chục series bucket của histogram. Cardinality tăng không giới hạn, Prometheus phình RAM và chậm query, thậm chí OOM. Kẻ tấn công còn có thể cố ý làm sập hệ thống giám sát. Dùng route template, gom mọi URL không khớp vào `unmatched`, thì số series cố định.
- **Metric mới:** `agent_question_length_chars` là Histogram với bucket `20, 50, 100, 200, 500, 1000, 2000`, gọi `observe(len(question))` trong `/ask` (`develop/app.py`). Không dùng label `length=...` vì độ dài có vô số giá trị.

---

## 4. Observability stack (production)

### 4.0 Exercise 7.4: Đọc dashboard khi có tải (Locust 100 users)

1. **p95 và avg:** dashboard lúc 23:41 cho p95 = **1.46 s**. Locust `scale_1_stats.csv` cho Average **433.7 ms**, p50 220 ms, p95 1700 ms. p95 lớn gấp khoảng 4 lần avg, nghĩa là phân bố latency có **đuôi dài**: phần lớn request nhanh (p50 220 ms), một nhóm nhỏ rất chậm (tail latency của LLM cộng thời gian xếp hàng khi quá tải). Average che mất nhóm này, nên SLO phải theo p95.
2. **Nginx có chia đều không:** `increase(http_requests_total{route="/ask"}[2m])` lúc 23:42:35 là **3385** (instance `172.18.0.5`) và **2637** (instance `172.18.0.8`), tỉ lệ khoảng 56/44. Không đều hoàn toàn vì instance thứ hai vừa khởi động khi Locust bắt đầu (`docker compose run` bật lại replica thứ 2), nên nhận traffic muộn hơn khoảng 5 s. Ngoài ra round-robin của Nginx chia theo *request* chứ không theo *tải*, nên request chậm làm một instance bận lâu hơn.
3. **Input tokens/s > output tokens/s:** cùng thời điểm, input là **3840 token/s**, output là **2003.5 token/s**. Prompt gồm system prompt, tài liệu retrieval (v2 RAG) và câu hỏi. Câu trả lời của mock chỉ là đoạn tài liệu. Với LLM thật cũng vậy: context RAG thường dài hơn câu trả lời. Giá output đắt gấp 4 lần input nhưng input chiếm số lượng lớn, nên phải theo dõi cả hai.
4. **`curl http://localhost:8080/metrics`** trả về **404 Not Found** (đã kiểm tra). `nginx.conf` có `location = /metrics { return 404; }`: metrics chỉ dành cho Prometheus scrape trực tiếp từng agent trong mạng nội bộ Docker. Nếu public ra ngoài sẽ lộ route, lưu lượng, chi phí và version. Hơn nữa, qua load balancer mỗi lần scrape trúng một instance khác nhau nên số liệu nhảy lung tung.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải — `screenshots/grafana-dashboard.png` (45.4 req/s, error 0.82%, p95 1.46 s đỏ vì vượt SLO 1 s, 15 in-flight, 2 instance)
- [x] Một trace chậm trong Jaeger — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger — `screenshots/jaeger-error-trace.png` (`llm_error` 503)
- [x] Trang Alerts của Prometheus với alert đang **firing** — `screenshots/prometheus-alert-firing.png`: **FIRING (2)** = `AgentHighErrorRate` + `AgentInstanceDown` (thí nghiệm A + D chạy cùng lúc)

### 4.2 Thí nghiệm "phá hệ thống"

Mỗi thí nghiệm: đổi biến môi trường rồi `docker compose -p k5-day14-observability up -d --no-deps agent` (tạo lại 2 instance agent), chạy tải nền bằng Locust headless 30 users. Thời gian đo bằng cách poll `GET /api/v1/alerts` của Prometheus (mốc "firing" là lần poll đầu tiên thấy state = firing, poll mỗi 3–5 s).

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| Tải | Locust 100 users (mục 5, bắt đầu 23:40:40) | `LLMCostBurnRateHigh` (firing); `AgentHighLatencyP95` chỉ **pending** (p95 = 1.46 s) vì tải dừng trước khi đủ `for: 2m` | khoảng 3.5 phút (cost) | Latency p95 (đỏ), LLM cost |
| A | `MOCK_ERROR_RATE=0.2` (23:53:38) | `AgentHighErrorRate` | **khoảng 82 s** (firing 23:55:00): rate 1m cần dữ liệu cộng `for: 1m` | Error rate, Requests/s theo status (503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` (23:56:15) | `AgentHighLatencyP95` (p95 = 1.92 s) | **khoảng 144 s** (pending 23:56:37, firing 23:58:39 = `for: 2m`) | Latency p50/p95/p99 (p99, p95 vọt, p50 gần như không đổi) |
| C | `LLM_MODEL=mock-llm-large` (23:58:50) | `LLMCostBurnRateHigh`: 8.78 USD/h, gấp khoảng 4.4 lần ngưỡng 2 USD/h | **khoảng 75 s** (firing 00:00:05). Alert đã *pending* từ 23:58:02 do tải của B, model large đẩy burn rate vượt ngưỡng nên firing ngay khi đủ `for: 2m` | LLM cost (1h), tokens/s. Latency cũng tăng (hệ số latency ×2.5) |
| D | `docker pause` agent-2 (23:53:51) | `AgentInstanceDown` | **khoảng 25 s** (firing 23:54:16). Lưu ý: alert đã *pending* từ 23:53:42 vì lúc tạo lại container ở thí nghiệm A instance cũng tạm `up=0` | Instances up (2 → 1); Nginx dồn traffic sang instance còn lại |
| E | `AGENT_VERSION=v1` | không | — | không panel hạ tầng nào; chỉ eval thấy |

**Nhận xét:** Thời gian tới lúc firing ≈ thời gian để `rate()` / `histogram_quantile()` trên cửa sổ 1m "thấy" sự cố cộng với `for:` của rule. `for:` ngắn (30 s cho InstanceDown) thì báo nhanh nhưng dễ báo nhầm khi deploy hoặc restart. Thí nghiệm A minh hoạ đúng điều này: tạo lại container cũng làm InstanceDown vào pending. `for:` dài (2m cho latency/cost) giảm báo nhầm nhưng phát hiện chậm hơn khoảng 2 phút.
| E | `AGENT_VERSION=v1` | không | — | không panel hạ tầng nào; chỉ eval thấy |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

v1 vẫn trả HTTP 200 nhanh và rẻ, nên mọi Golden Signal (latency, traffic, errors, saturation) đều "xanh". Đây là lỗi **chất lượng**, không phải lỗi hạ tầng. Cách bắt:
1. **Quality gate trước deploy**: eval golden dataset trong CI (mục 3), v1 chỉ đạt 4.3% nên bị chặn trước khi lên production.
2. **Eval liên tục sau deploy**: chạy golden dataset định kỳ (synthetic probe) vào môi trường thật, đẩy accuracy thành metric (`agent_eval_accuracy`) và alert khi giảm.
3. **Metric gián tiếp**: v1 không retrieval, nên tỉ lệ câu có `retrieved=true` và input tokens/câu giảm đột ngột (khoảng 109 → 57). Alert trên các chỉ số này, cùng `agent_info{version}` để thấy version đổi.
4. **Tín hiệu từ người dùng**: thumbs-down, tỉ lệ hỏi lại.

### 4.3 Debug bằng trace

- `trace_id`: `6506d94d86376aae7622215c89db8f24`
- Tổng thời gian: 3401.8 ms (span gốc `POST /ask`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1884.6 ms, khoảng 55%). `agent.retrieve_context` chỉ 109.0 ms. Phần còn lại (khoảng 1.4 s giữa `POST /ask` và `agent.run` 1994.3 ms) là thời gian **chờ trong hàng đợi** của instance khi đang tải 100 users. Request này vừa trúng tail latency của LLM (`MOCK_SLOW_RATE`) vừa bị xếp hàng.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T16:41:06.978572+00:00", "level": "INFO", "service": "observable-agent", "instance": "11f202a6ab04", "event": "llm_call", "trace_id": "6506d94d86376aae7622215c89db8f24", "span_id": "1400b9d8bff6dcf0", "request_id": "224a5113a054", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1664.3}
{"ts": "2026-11-26T16:41:07.277795+00:00", "level": "INFO", "service": "observable-agent", "instance": "11f202a6ab04", "event": "http_request", "trace_id": "6506d94d86376aae7622215c89db8f24", "span_id": "1400b9d8bff6dcf0", "request_id": "224a5113a054", "method": "POST", "route": "/ask", "status": 200, "ms": 3386.1}
```

Trace lỗi: `2df2bc99b135407b574792c370b995ec`. Log: `"event": "llm_error", "error": "Upstream LLM error: 503 Service Unavailable (mock)"`, `"status": 503, "ms": 97.8`. Lỗi trả về nhanh (97.8 ms), đúng như mock: lỗi upstream đến sớm hơn response thành công.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

File: `benchmark-results/scale_1_stats.csv`, `benchmark-results/scale_3_stats.csv` (dòng Aggregated).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 (thực tế 2, xem ghi chú) | 57.14 | 220 | 1700 | 2200 | 73 / 6797 (1.07%) |
| 3 | 61.46 | 210 | 1000 | 1800 | 77 / 7284 (1.06%) |

> ⚠️ `docker-compose.yml` đặt `deploy.replicas: 2`, và `docker compose run locust` tự bật lại dependency theo cấu hình này, nên lần "scale_1" thực tế chạy với **2** instance (Grafana panel "Instances up" = 2 trong ảnh dashboard). So sánh đúng là **2 → 3 instance**.

**Giải thích kết quả:** Từ 2 lên 3 instance, **p95 giảm từ 1700 ms xuống 1000 ms (−41%)** và p99 từ 2200 ms xuống 1800 ms, vì 100 users chia ra 3 event loop nên mỗi instance ít request phải xếp hàng hơn. Đúng như trace ở mục 4.3: khoảng 40% thời gian của request chậm là chờ hàng đợi. RPS chỉ tăng nhẹ (57 → 61) vì Locust mô phỏng user có `wait_time`, nên RPS bị giới hạn bởi số user chứ không bởi server. p50 gần như không đổi (220 → 210 ms) vì nó do latency của LLM quyết định. Nút thắt còn lại: (1) **tail latency của LLM upstream** (`MOCK_SLOW_RATE`, cộng 1.5 s), không giảm được bằng scale; (2) error rate khoảng 1% do upstream (`MOCK_ERROR_RATE`), scale không sửa được, phải retry hoặc fallback model; (3) mọi container chạy chung một laptop nên CPU của máy cũng là giới hạn.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Average nói dối, percentile thì không.** Tăng request chậm từ 3% lên 10%, avg chỉ tăng 1.9 lần nhưng p95 tăng 3.1 lần. SLO phải đặt theo p95/p99.
  2. **Throughput có trần.** Qua khoảng 10 concurrent, RPS không tăng nữa (khoảng 34) mà chỉ latency tăng (p95 từ 0.5 s lên 6.4 s). Load test cho biết chính xác khi nào phải scale ngang.
  3. **Đo chất lượng phải tách khỏi đo hạ tầng.** v1 "khoẻ" theo mọi metric nhưng chỉ đúng 4%. Cần eval với quality gate và so sánh bằng *cost / câu đúng*, không phải cost / câu.
- Nếu đưa lên production thật sẽ thêm:
  - Metric `agent_eval_accuracy` từ eval định kỳ, kèm alert khi giảm quá 5 điểm.
  - Alert **burn rate** của error budget (cửa sổ 1h/6h) thay cho ngưỡng tĩnh.
  - Alert cost/giờ vượt budget.
  - Tỉ lệ `retrieved=false`.
  - Saturation: event-loop lag và in-flight requests theo từng instance.
