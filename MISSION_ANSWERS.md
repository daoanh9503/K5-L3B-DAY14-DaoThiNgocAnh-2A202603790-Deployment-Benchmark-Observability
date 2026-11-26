# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (≥ 5, kèm dòng code trong `develop/app.py`)
1. 
2. 
3. 
4. 
5. 

### Exercise 1.2: Kết quả gọi bản develop
```text
(dán output curl -X POST "http://localhost:8000/ask?question=Hello")
```

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config  |         |            |                |
| Secrets |         |            |                |
| Health check |    |            |                |
| Logging |         |            |                |
| Shutdown |        |            |                |

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
