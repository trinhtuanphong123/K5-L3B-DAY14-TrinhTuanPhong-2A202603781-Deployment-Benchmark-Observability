# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Phân tích file `01-localhost-vs-production/develop/app.py` (54 dòng).

| # | Anti-pattern | Vị trí (`file:dòng`) | Vì sao nguy hiểm |
|---|---|---|---|
| 1 | API key và mật khẩu database hardcode trong code | `develop/app.py:17-18` | Push lên GitHub sẽ bị bot của hacker quét tự động GitHub để tìm key bị lộ rồi dùng trái phép, gây tốn tiền và rò rỉ dữ liệu. Xoá file sau đó cũng không đủ vì key vẫn nằm trong lịch sử git |
| 2 | Cấu hình ghi cứng trong code (`DEBUG = True`, `MAX_TOKENS = 500`) | `develop/app.py:21-22` | Khó thay đổi giữa các môi trường (dev/staging/production), mỗi lần đổi phải sửa code và build lại |
| 3 | In API key ra log bằng `print` (`Using key: ...`); dùng `print` thay vì logging | `develop/app.py:33-38` (key bị in ở dòng 34) | Log thường được gửi sang hệ thống bên thứ ba hoặc nhiều người đọc được, nên key trong log cũng là lộ key. |
| 4 | Không có health check endpoint (`GET /health` → 404) | `develop/app.py:42-43` (chỉ có comment, không có route) | Nếu agent crash hoặc treo, platform không có cách biết để restart; load balancer cũng không biết có nên gửi request vào hay không |
| 5 | Không xử lý shutdown gracefully (không có `lifespan`, không có xử lý SIGTERM) | `develop/app.py:47-54` (chỉ gọi `uvicorn.run`) | Platform tắt container bằng SIGTERM mỗi lần deploy hoặc scale; không dọn dẹp thì request đang chạy có thể bị cắt ngang |
| 6 | Host và port cố định (`host="localhost"`, `port=8000`) | `develop/app.py:51-52` | Trong container, nghe `localhost` thì bên ngoài không gọi vào được. Railway/Render cấp `PORT` qua biến môi trường, cố định 8000 thì app không nhận được traffic |
| 7 | Bật `reload=True` cố định | `develop/app.py:53` | Chế độ tự reload là để dev; ở production tốn tài nguyên và có thể khởi động lại ngoài ý muốn |

### Exercise 1.2: Kết quả chạy bản develop

Chạy trong WSL2 Ubuntu (Python 3.12, `os.name = posix`), thư mục `01-localhost-vs-production/develop`, `python app.py` (cổng 8000):

```bash
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -i -X POST http://localhost:8000/ask -H 'Content-Type: application/json' -d '{"question":"Hello"}'
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
{"detail":"Not Found"}
```

Log của app khi nhận câu hỏi (stdout):

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
```

**Nhận xét:** Bản develop chạy đúng và trả lời được, nhưng chưa sẵn sàng cho production: nó nhận `question` qua query chứ không phải JSON, không có `/health` (platform không biết app còn sống hay không), và log in thẳng API key ra stdout. Nó chạy được trên máy mình chỉ vì không có ai khác dùng và không có platform nào giám sát nó.

### Exercise 1.3: Bảng so sánh develop vs production

Nguồn: `develop/app.py` và `production/app.py`, `production/config.py` (trong `01-localhost-vs-production/`). Các hành vi ghi "Quan sát" là kết quả tôi tự chạy cả hai bản trong WSL2.

| Feature | Develop | Production | Tại sao quan trọng? |
|---|---|---|---|
| Config | Giá trị gán cứng trong code: `DEBUG = True`, `MAX_TOKENS = 500` (`app.py:21-22`) | Gom vào `Settings`, đọc từ biến môi trường qua `os.getenv` có default (`config.py:17-34`), tạo một lần ở `config.py:50` | Cùng một code chạy ở dev/staging/production, chỉ đổi biến môi trường. Gán cứng thì mỗi lần đổi cấu hình phải sửa code và build lại, dễ quên tắt `DEBUG` ở production |
| Secrets | API key và mật khẩu DB nằm trong code (`app.py:17-18`), còn bị `print` ra log (`app.py:34`) | Key đọc từ env (`config.py:27,32`), `.env.example` chỉ là mẫu và `.env` bị `.gitignore`; log chỉ ghi độ dài câu hỏi, không ghi key (`app.py:111-115`) | Push lên GitHub là lộ key, phải revoke (bài này trừ 10 điểm). Log thường được gửi sang hệ thống bên thứ ba nên key trong log cũng là lộ |
| Host / Port | `host="localhost"`, `port=8000`, `reload=True` đều cố định (`app.py:49-53`) | `host`/`port` lấy từ `HOST`/`PORT` với default `0.0.0.0` (`config.py:17-18`, `app.py:194-197`); `reload` chỉ bật khi `DEBUG=true` (`app.py:198`) | Trong container, nghe `localhost` thì bên ngoài không gọi vào được. Railway/Render cấp `PORT` qua env, cố định 8000 thì app không nhận được traffic. `reload` ở production tốn tài nguyên và không an toàn |
| Health check | Không có; quan sát `GET /health` → **404** | `GET /health` → 200 kèm uptime (`app.py:135`); `GET /ready` → 200 khi sẵn sàng, 503 khi chưa (`app.py:152`); khi chạy thật tôi chỉ quan sát được 200 | Platform dùng `/health` để biết khi nào phải restart, load balancer dùng `/ready` để biết có gửi request vào hay không. Không có thì app treo cũng không ai biết |
| Logging | `print` chữ thường, gồm cả dữ liệu nhạy cảm (`app.py:33-38`) | Code dùng `logger.info(json.dumps({...}))` có trường `event` (`app.py:111-122`). **Quan sát:** khi chạy, log vẫn là kiểu `INFO: ...`, không phải JSON, và các dòng `logger.info` của app không hiện, vì `config.py` gọi `logging.warning` lúc import trước khi `basicConfig` ở `app.py:28` kịp chạy (suy luận từ output) | Log JSON có cấu trúc để công cụ (Datadog, Loki…) lọc theo trường được. `print` không có mức độ (level), không có thời gian, khó tìm lỗi. Ghi chú: ý định đúng nhưng thực tế cấu hình chưa có tác dụng, phải kiểm tra output chứ không tin code |
| Shutdown | Không xử lý gì; `uvicorn.run(..., reload=True)` | Có `lifespan` dọn dẹp lúc tắt (`app.py:39-67`) và handler SIGTERM (`app.py:180-189`). **Quan sát:** gửi SIGTERM → process thoát **exit code 0**, log "Application shutdown complete" | Platform tắt container bằng SIGTERM mỗi lần deploy hoặc scale. Không xử lý thì request đang chạy bị cắt ngang. Thoát exit 0 cho platform biết là tắt đúng cách |
| Readiness | Không có | `/ready` trả 503 khi `is_ready` là False (`app.py:152-161`) | Phân biệt "process còn sống" (liveness) với "sẵn sàng nhận việc" (readiness) |
| Xử lý input sai | `question` bắt buộc ở query; thiếu → 422 do FastAPI | Thiếu `question` trong JSON → 422 "question field is required" (`app.py:107-108`). **Quan sát:** gọi `POST /ask?question=Hello` (không có JSON) → **500 Internal Server Error** vì `request.json()` văng `JSONDecodeError` (`app.py:104`) | Lỗi do người dùng gửi sai nên trả mã 4xx rõ ràng, không phải 500. Chỗ này chưa xử lý và sẽ được chấm ở Part 6 ("không lộ stack trace") |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

Phân tích `02-docker/develop/Dockerfile`.

1. Base image:  python:3.11
2. Working directory: /app
3. Tại sao `COPY requirements.txt` trước: vì Docker lưu cache theo từng layer , với việc các thư viện được dùng thì thường ít thay đổi hơn so với code nên làm vậy để tránh pip install lại
4. CMD vs ENTRYPOINT khác nhau thế nào:CMD là lệnh mặc định, docker run image <lệnh khác> ghi đè được; ENTRYPOINT là chương trình cố định, muốn đổi phải dùng cờ --entrypoint

### Exercise 2.2: Build và chạy container develop

Chạy trong WSL2 Ubuntu, từ gốc repo (Dockerfile `COPY` theo đường dẫn tính từ gốc). Bản develop nhận `question` qua query chứ không nhận JSON (README.md mục 3):

```bash
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d --name cp2-dev -p 8000:8000 my-agent:develop

$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":4.9,"container":true}

$ docker logs cp2-dev
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.17.0.1:41952 - "POST /ask?question=What%20is%20Docker HTTP/1.1" 200 OK
INFO:     172.17.0.1:41966 - "GET /health HTTP/1.1" 200 OK

$ docker exec cp2-dev sh -c "whoami; pwd; ls"
root
/app
__pycache__
app.py
requirements.txt
utils
```

**Quan sát:** container chạy được và trả lời giống chạy trực tiếp trên máy, nhưng tiến trình trong container chạy bằng **root** (`whoami` ra `root`). Đây là điểm chưa an toàn mà Dockerfile production đã sửa bằng `USER appuser`. Thư mục `/app` chứa đúng các file mà Dockerfile đã `COPY` (`app.py`, `requirements.txt`, `utils/`). `docker exec` và `docker logs` là hai cách để debug container đang chạy.

### Exercise 2.3: Multi-stage build

Phân tích `02-docker/production/Dockerfile`.

- **Stage 1 (builder, dòng 16-29):** dùng `python:3.11-slim`, cài `gcc` và `libpq-dev`, rồi `pip install --user -r requirements.txt` để cài dependency vào `/root/.local`. Stage này chỉ để build, không dùng để deploy.
- **Stage 2 (runtime, dòng 36-72):** bắt đầu lại từ `python:3.11-slim`, tạo user `appuser` (non-root), chỉ `COPY --from=builder /root/.local` (khoảng 40.8 MB) cùng `main.py` và `utils/mock_llm.py`, chuyển sang `USER appuser`, thêm `HEALTHCHECK` và `CMD uvicorn ... --workers 2`.
- **Vì sao image nhỏ hơn:** (1) image cuối lấy base `-slim` thay vì bản `python:3.11` đầy đủ như bản develop; (2) các công cụ build (`gcc`, `libpq-dev`, cache của apt) nằm ở stage 1 và không được copy sang stage 2; (3) chỉ copy thư mục package đã cài và vài file code, không copy cả thư mục dự án.

Kích thước đo bằng `docker images` (cột **DISK USAGE**; cột CONTENT SIZE ghi thêm để đối chiếu):

| Image | DISK USAGE | CONTENT SIZE |
|---|---|---|
| `my-agent:develop` (single-stage, `python:3.11`) | 1.67 GB | 426 MB |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | 240 MB | 57.4 MB |

Chênh lệch: **85.6%** theo DISK USAGE ((1670 − 240) / 1670 × 100); theo CONTENT SIZE là 86.5% ((426 − 57.4) / 426 × 100). Số liệu lấy từ lệnh `docker images` tôi tự chạy, không chép từ README.

### Exercise 2.4: Docker Compose stack

Sơ đồ các service (`02-docker/production/docker-compose.yml`):

```text
        Client (curl)
            │  http://localhost:80
            ▼
     ┌────────────┐   proxy_pass agent:8000   ┌──────────────────────┐
     │   nginx    │ ────────────────────────▶ │  agent (uvicorn,     │
     │ :80 / :443 │                           │  2 workers, :8000)   │
     └────────────┘                           │  không mở cổng ra    │
                                              │  máy host            │
                                              └──────────────────────┘
   ───────────── network nội bộ "internal" (bridge) ─────────────
        ┌────────┐      ┌─────────┐
        │ redis  │      │ qdrant  │   khởi động và healthy, nhưng
        │ :6379  │      │ :6333   │   agent KHÔNG gọi tới (main.py
        └────────┘      └─────────┘   không dùng Redis/Qdrant)
```

- **Services được start:** 4 service là `agent`, `nginx`, `redis`, `qdrant`, cùng nằm trong network `internal`. Chỉ `nginx` publish cổng ra ngoài (80 và 443).
- **Giao tiếp:** Nginx chuyển request tới `agent:8000` bằng tên service (DNS nội bộ của Docker, khai báo trong `nginx/nginx.conf`); Nginx còn giới hạn 10 request/giây mỗi IP và thêm vài header bảo mật. Compose truyền `REDIS_URL` và `QDRANT_URL` vào agent, và `depends_on` bắt agent chờ Redis/Qdrant `healthy`, nhưng `main.py` không dùng hai biến đó nên log agent không có dòng nào nhắc Redis hay Qdrant.

Kết quả test qua Nginx (cổng 80), chạy bằng `docker compose -p k5-day14-docker up -d --build` trong `02-docker/production/` (đã `touch .env.local` trước):

```bash
$ curl -i http://localhost/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.4,"version":"2.0.0","timestamp":"2026-11-26T09:22:36.575327"}

$ curl -i -X POST http://localhost/ask -H 'Content-Type: application/json' \
    -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

$ curl -i -X POST http://localhost/ask -H 'Content-Type: application/json' -d '{}'
HTTP/1.1 422 Unprocessable Entity
{"detail":"question required"}

$ curl http://localhost:8000/health        # gọi thẳng agent, không qua Nginx
(không kết nối được: agent không publish cổng 8000 ra host)
```

Lưu ý: lúc test, redis và qdrant đã `healthy` còn agent mới ở trạng thái `health: starting` (uptime 0.4 giây); tôi chưa quan sát agent tới `healthy`. Log agent hiện mỗi dòng hai lần vì `--workers 2` chạy hai tiến trình. Xong thì dọn bằng `docker compose -p k5-day14-docker down -v`.

## Part 3: Cloud Deployment

## Part 4: API Security

## Part 5: Scaling & Reliability

---

## Output của `python check_production_ready.py` (CP5)

---



