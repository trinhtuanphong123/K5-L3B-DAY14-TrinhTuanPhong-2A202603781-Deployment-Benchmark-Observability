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

### Exercise 3.1 / 3.2: Deploy (nền tảng chính: Render)

Theo CHECKPOINTS.md CP6, tôi deploy chính agent Part 6 (`06-lab-complete/`), không deploy app mẫu trong `03-cloud-deployment/`. Tạo bằng Render Blueprint từ repo GitHub, Blueprint Path = `06-lab-complete/render.yaml`; Blueprint tạo web service Docker `k5-day14-agent` và Key Value `k5-day14-redis`, `AGENT_API_KEY` nhập trên Dashboard (`sync: false`). Chi tiết ở [DEPLOYMENT.md](DEPLOYMENT.md).

- URL: https://k5-day14-agent-jilo.onrender.com
- Screenshot: [dashboard](screenshots/dashboard.png) · [running](screenshots/running.png) · [test](screenshots/test.png)

4 lệnh tự kiểm của CP6 (`BASE` = URL trên, key lấy từ biến môi trường, không in ra):

```text
GET  /health                    → 200
GET  /ready                     → 200   (Redis trên Render kết nối được)
POST /ask (không X-API-Key)     → 401
POST /ask (X-API-Key đúng)      → 200
```

### So sánh `railway.toml` và `render.yaml` (nền tảng còn lại)

Hai file trong `06-lab-complete/` cùng deploy một Dockerfile và cùng kiểm `/health`, nhưng phạm vi khác nhau:

| Khía cạnh | `railway.toml` | `render.yaml` (Blueprint) |
|---|---|---|
| Định dạng, phạm vi | TOML, chỉ cấu hình build/deploy của **một** service | YAML, khai báo **toàn bộ hạ tầng**: web service + Key Value, kèm cách nối biến giữa chúng |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`; thư mục gốc chọn khi `railway up` trong `06-lab-complete/` | `runtime: docker`, `rootDir: 06-lab-complete`; `dockerfilePath`, `dockerContext` tính tương đối với `rootDir` |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Render tự quản lý, không cần khai báo |
| Redis | không nằm trong file: phải thêm Redis bằng plugin rồi đặt biến `REDIS_URL = ${{Redis.REDIS_URL}}` | khai báo service `type: keyvalue` và nối bằng `fromService … property: connectionString` |
| Secret | đặt bằng `railway variables` hoặc Dashboard | `sync: false` → Render hỏi giá trị khi tạo Blueprint, file không chứa giá trị |
| Plan, region | không có trong file (chọn trên Railway) | `plan: free`, `region: singapore` ngay trong file |

Vì sao khác: `railway.toml` là "config-as-code" cho cách build và chạy một service, còn các resource khác (Redis, biến) tạo bằng CLI hoặc giao diện; `render.yaml` là Infrastructure-as-Code, một file tạo lại được cả stack. Vì vậy với Render, mất cả project vẫn dựng lại được chỉ từ repo, còn với Railway phải nhớ thêm các bước thêm Redis và đặt biến.

### Exercise 3.3: Cloud Run CI/CD (đọc `03-cloud-deployment/production-cloud-run/`)

- `cloudbuild.yaml` chạy 4 bước nối nhau bằng `waitFor`: **test** (`pytest tests/` trong `python:3.11-slim`) → **build** image Docker gắn tag `$COMMIT_SHA` và `latest`, dùng `--cache-from` image cũ để tận dụng layer cache → **push** lên Container Registry `gcr.io/$PROJECT_ID/ai-agent` → **deploy** bằng `gcloud run deploy` với image đúng `$COMMIT_SHA`, region `asia-southeast1`, 1–10 instance, 512Mi, secret lấy từ Secret Manager (`--set-secrets`).
- Test fail thì các bước sau không chạy, nên code lỗi không lên production; deploy theo `$COMMIT_SHA` nên biết chính xác commit nào đang chạy và rollback được.
- `service.yaml` mô tả cùng service theo kiểu khai báo (Knative): `minScale: 1` để tránh cold start, `maxScale: 10`, `containerConcurrency: 80`, giới hạn CPU/RAM, secret qua `secretKeyRef`, `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready` (đúng tách liveness/readiness ở Part 5).
- Điểm tôi để ý khi đọc: thư mục `production-cloud-run/` chỉ có hai file này, không có `requirements.txt` hay `tests/`, nên bước test sẽ fail nếu chạy nguyên trong thư mục đó; và `cloudbuild.yaml` chỉ đặt secret `OPENAI_API_KEY`, còn `AGENT_API_KEY` chỉ có trong `service.yaml`.

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/app.py`)

Chạy trong WSL2, bật bằng `AGENT_API_KEY=secret-key-123 python app.py`, rồi gọi bốn trường hợp:

```bash
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: sai-key" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -i http://localhost:8000/health        # không cần key
HTTP/1.1 200 OK
{"status":"ok"}
```

**Câu hỏi (TỰ TRẢ LỜI, dẫn `file:dòng`):**

1. API key được kiểm tra ở đâu?
   - Trong hàm dependency `verify_api_key` (`04-api-gateway/develop/app.py:39-54`). Hàm lấy header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)` (dòng 36) và so sánh với biến `API_KEY` (dòng 35, đọc từ môi trường `AGENT_API_KEY`). Endpoint `/ask` được bảo vệ bằng cách khai báo dependency này; `/health` không khai báo nên công khai (đã thấy trả 200 không cần key).
2. Điều gì xảy ra nếu sai key?
   - Thiếu header: `401 Unauthorized` "Missing API key" (dòng 44-48). Có header nhưng giá trị khác `API_KEY`: `403 Forbidden` "Invalid API key." (dòng 49-53). Cả hai tôi đã chạy thật ở trên. Lưu ý: bản Part 6 yêu cầu sai key cũng trả 401, nên không chép nguyên logic này.
3. Làm sao rotate key?
   - Đổi giá trị biến môi trường `AGENT_API_KEY` rồi khởi động lại process; không cần sửa code vì key đọc ở dòng 35. Nếu không đặt biến, code dùng giá trị mặc định `demo-key-change-in-production` (dòng 35), nên production bắt buộc phải đặt biến. Hạn chế: chỉ có một key chung cho mọi client, nên rotate là mọi client phải đổi cùng lúc; muốn rotate êm cần chấp nhận nhiều key cùng lúc (cái này code hiện tại chưa làm). Key cũng bị in ra log lúc khởi động (log develop có dòng `API Key: secret-key-123`), nên không dùng bản develop ở production.

### Exercise 4.2: JWT authentication (`04-api-gateway/production/`)

Chạy `python app.py` trong `04-api-gateway/production/`. Token đã che bằng `<token>`:

```bash
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"sai"}'
HTTP/1.1 401 Unauthorized
{"detail":"Invalid credentials"}

$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
{"access_token":"<token>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer <token>..."}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer abc.def.ghi" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid token."}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

Token dài 168 ký tự, gồm 3 phần cách nhau bởi 2 dấu chấm (header.payload.signature).

**JWT flow (TỰ VIẾT, theo thứ tự các bước, dẫn `file:dòng`):**

1. **Login:** client gửi `POST /auth/token` với username/password (`production/app.py:105-118`). `authenticate_user` (`auth.py:70-75`) tra `DEMO_USERS`; sai thì `401 Invalid credentials`.
2. **Server ký token:** `create_token` (`auth.py:35-43`) tạo payload gồm `sub` (username), `role`, `iat`, `exp` (60 phút, dòng 24) rồi ký bằng `jwt.encode(..., SECRET_KEY, algorithm="HS256")`. Server không lưu token ở đâu cả (stateless).
3. **Client giữ token** và gửi kèm mỗi request trong header `Authorization: Bearer <token>`.
4. **Mỗi request vào `/ask`:** dependency `verify_token` (`auth.py:46-67`) chạy trước: không có header → `401` kèm `WWW-Authenticate: Bearer`; `jwt.decode` kiểm chữ ký và `exp`; hết hạn → `401 Token expired`; chữ ký sai/token hỏng → `403 Invalid token`; hợp lệ → trả `{username, role}`.
5. **Dùng thông tin trong token:** `ask_agent` (`app.py:125-153`) lấy `role` từ token để chọn rate limiter (dòng 141), rồi kiểm cost, gọi LLM mock, ghi usage. Vì `role` nằm trong token đã ký, server không cần truy vấn DB mỗi request.

Điểm yếu cần biết: `SECRET_KEY` có giá trị mặc định ghi cứng `super-secret-change-in-production-please` (`auth.py:22`); nếu quên đặt `JWT_SECRET` thì ai đọc repo cũng tự ký được token admin. Mật khẩu demo lưu dạng chữ thường trong code (`auth.py:27-30`), chỉ chấp nhận được cho bài lab.

### Exercise 4.3: Rate limiting (`production/rate_limiter.py`)

Vòng lặp 12 lần `POST /ask` bằng token của `student` (user, giới hạn 10 request/phút). Request `(e)` ở mục 4.2 đã tính là lần gọi thứ 1 trong cửa sổ 60 giây, nên lần thứ 10 của vòng lặp bị chặn:

```text
Request  1: HTTP 200
...
Request  9: HTTP 200
Request 10: HTTP 429
Request 11: HTTP 429
Request 12: HTTP 429
```

```bash
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <token>" ... (lần bị chặn)
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795686379
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}

$ curl http://localhost:8000/me/usage -H "Authorization: Bearer <token>"
{"user_id":"student","date":"2026-11-26","requests":10,"input_tokens":40,"output_tokens":296,"cost_usd":0.000184,"budget_usd":1.0,"budget_remaining_usd":0.999816,"budget_used_pct":0.0}
```

Với `teacher` (role admin, giới hạn 100/phút), 12 request liên tiếp đều trả `200` (không bị 429). `/admin/stats` bằng token teacher trả `200`, bằng token student trả `403 {"detail":"Admin only"}`.

**Câu hỏi (TỰ TRẢ LỜI, dẫn `file:dòng`):**

1. Algorithm nào được dùng? (Fixed window, sliding window log hay token bucket? Dựa vào cấu trúc dữ liệu trong code.)
   - **Sliding window log.** Mỗi user có một `deque` lưu timestamp từng request (`rate_limiter.py:27`); mỗi lần `check` bỏ các timestamp cũ hơn `now - window_seconds` (dòng 39-40), rồi đếm số còn lại, nếu `>= max_requests` thì chặn (dòng 45). Docstring đầu file ghi "Sliding Window Counter" (dòng 7) nhưng code lưu từng timestamp chứ không đếm theo bucket, nên đúng tên là sliding window log.
2. Limit là bao nhiêu requests/window? Cửa sổ dài bao lâu?
   - User: 10 request / 60 giây (`rate_limiter.py:86`). Admin: 100 request / 60 giây (dòng 87). Khi vượt: `429` với `Retry-After` và `X-RateLimit-*` (dòng 48-61); đã thấy `retry-after: 59` khi chạy.
3. Làm sao bypass limit cho admin?
   - Không bỏ qua hoàn toàn mà dùng limiter khác: `ask_agent` chọn `rate_limiter_admin` nếu `role == "admin"`, ngược lại `rate_limiter_user` (`app.py:141`). Role lấy từ JWT đã ký nên client không tự nâng quyền được. Kiểm chứng: `teacher` gọi 12 lần đều `200`, `student` bị `429` từ lần thứ 10 của vòng lặp. Lưu ý trạng thái đếm nằm trong bộ nhớ từng process (`defaultdict` dòng 27), nên khi chạy nhiều instance mỗi instance đếm riêng, cần Redis (Part 5).

### Exercise 4.4: Cost guard (`production/cost_guard.py`)

**Cách làm cost guard (TỰ VIẾT, 4–6 câu):** mỗi user có ngân sách bao nhiêu mỗi ngày, kiểm tra ở bước nào của `/ask`, ghi chi phí ở đâu, khi vượt thì trả mã gì, và hạn chế của việc lưu trong bộ nhớ so với Redis.

- Mỗi user có ngân sách `$1`/ngày và toàn hệ thống `$10`/ngày (`cost_guard.py:42-43`, singleton dòng 128). Trong `/ask` (`app.py:145`), `check_budget` chạy **trước** khi gọi LLM: nếu tổng chi phí toàn cục `>= $10` thì trả `503` (dòng 68-73), nếu chi phí của user `>= $1` thì trả `402 Payment Required` (dòng 76-85), còn từ 80% thì chỉ ghi log cảnh báo (dòng 88-91). Sau khi gọi LLM, `record_usage` (`app.py:153`, `cost_guard.py:93-110`) cộng token vào bản ghi của user và vào `_global_cost`; chi phí tính từ số token nhân giá mỗi 1K token (`cost_guard.py:20-21,34-36`). Bản ghi theo ngày: sang ngày mới `_get_record` tạo bản ghi mới (dòng 53-58), nên budget tự reset.
- Hạn chế: dữ liệu nằm trong bộ nhớ (`self._records`, dòng 49), nên mất khi restart và mỗi instance đếm riêng; production phải chuyển sang Redis/DB như docstring dòng 9 nói. Hai chỗ lệch tôi thấy khi đọc code: (1) `resets_at: "midnight UTC"` nhưng `time.strftime` dùng giờ local của máy, không phải UTC; (2) `/ask` trả `budget_remaining_usd: usage.total_cost_usd` (`app.py:160`) — đây là số tiền **đã dùng**, không phải còn lại (khi chạy thấy `1.9e-05` ngay sau request đầu), còn `/me/usage` mới trả đúng `budget_remaining_usd`. Tôi không sửa vì bài chỉ yêu cầu đọc và giải thích.

Ghi chú tôi quan sát được khi chạy: `student` dùng 10 request mới hết khoảng `$0.000184` trên ngân sách `$1`/ngày, nên không thể kích hoạt lỗi `402` trong demo này; chỉ đọc code để thấy nhánh đó.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (`05-scaling-reliability/develop/app.py`)

Chạy trong WSL2 bằng `python app.py` (cổng 8000):

```bash
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":3.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T09:52:24.220855+00:00","checks":{"memory":{"status":"ok","used_percent":15.5}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

Code đã có sẵn hai endpoint, không phải tự viết khung TODO trong CODE_LAB:

- **`/health` (liveness, dòng 104-144):** chỉ trả lời "process còn sống không", kèm uptime, version, kiểm memory bằng `psutil`. Nếu endpoint này lỗi hoặc timeout thì platform **restart** container.
- **`/ready` (readiness, dòng 147-169):** trả `503` khi `_is_ready` là `False` (đang khởi động hoặc đang shutdown), ngược lại `200`. Nếu fail thì load balancer **ngừng gửi traffic** vào instance này nhưng không restart nó.
- **Khác nhau ở đâu:** liveness trả lời "có cần giết và chạy lại không", readiness trả lời "có nên gửi request vào lúc này không". Một instance đang tắt dần phải `ready = false` nhưng vẫn còn sống; nếu cho liveness fail lúc đó thì platform sẽ giết nó giữa chừng, làm hỏng chính cơ chế graceful shutdown.
- Ghi chú: `in_flight_requests: 1` trong kết quả `/ready` chính là request `/ready` tự đếm bản thân (middleware dòng 72-81 tăng biến đếm cho mọi request).

### Exercise 5.2: Graceful shutdown (`develop/app.py`)

Thử đúng như CODE_LAB gợi ý: gửi `POST /ask` (mock LLM mất khoảng 3 giây), sau 1 giây gửi `SIGTERM` cho process:

```text
16:52:25.251  gửi SIGTERM
curl: HTTP/1.1 200 OK  {"answer":"Tôi là AI agent được deploy lên cloud. ..."}

INFO:     Shutting down
INFO:     127.0.0.1:52636 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
INFO  🔄 Graceful shutdown initiated...
INFO  ✅ Shutdown complete
INFO:     Finished server process [2630]
INFO  Received signal 15 — uvicorn will handle graceful shutdown
```

**Kết quả:** request đang xử lý lúc nhận SIGTERM **vẫn hoàn thành với 200** rồi server mới tắt, cổng 8000 đóng sau đó. Cơ chế gồm ba phần:

1. `uvicorn.run(..., timeout_graceful_shutdown=30)` (dòng 192-198): uvicorn nhận SIGTERM thì ngừng nhận kết nối mới, chờ request đang chạy tối đa 30 giây.
2. `lifespan` (dòng 42-66): khi tắt đặt `_is_ready = False` (dòng 55) để `/ready` trả 503, rồi vòng lặp chờ `_in_flight_requests` về 0, tối đa 30 giây (dòng 59-64).
3. Handler `handle_sigterm` (dòng 175-187) chỉ **ghi log**; việc tắt thật do uvicorn làm. Trong log, dòng "Received signal 15" của handler xuất hiện sau cùng, nghĩa là uvicorn xử lý trước rồi mới chuyển tiếp tín hiệu cho handler cũ.

Vì sao quan trọng: platform (Docker, Railway, Render, Kubernetes) tắt container bằng SIGTERM, nếu sau một khoảng ngắn process chưa thoát sẽ gửi SIGKILL (không bắt được). Không xử lý SIGTERM thì request của người dùng bị cắt giữa chừng mỗi lần deploy. Process Python cũng phải nhận được tín hiệu: Dockerfile bản production dùng `CMD ["python","-m","uvicorn",...]` (exec form) nên Python là PID 1 và nhận SIGTERM trực tiếp; log đã thấy `Shutting down` khi `docker stop`.

### Exercise 5.3: Stateless design (`05-scaling-reliability/production/app.py`)

- **Anti-pattern:** giữ `conversation_history = {}` trong RAM của process. Khi chạy nhiều instance, request 1 vào instance A lưu history ở RAM của A, request 2 của cùng user vào instance B thì B **không có** history đó. Instance restart cũng làm mất toàn bộ state.
- **Cách bản production làm:** state nằm ở Redis, instance chỉ giữ code. `save_session` dùng `_redis.setex(f"session:{id}", ttl, ...)` (dòng 59-65, TTL 3600 giây), `load_session` đọc `_redis.get` (dòng 68-73), `append_to_history` thêm message và cắt còn tối đa 20 (dòng 76-90). Bất kỳ instance nào cũng đọc/ghi được cùng session. Mỗi response có `served_by` (dòng 155) để thấy instance nào xử lý.
- **Điểm yếu nên biết:** (1) khi không kết nối được Redis, code **âm thầm** chuyển sang dict trong RAM (dòng 43-45), lúc đó chạy nhiều instance sẽ hỏng session mà không báo lỗi, chỉ có trường `storage` trong response lộ ra; (2) `append_to_history` đọc rồi ghi lại cả session (không nguyên tử), hai request đồng thời của cùng session có thể ghi đè nhau (suy luận từ code, tôi chưa thử); (3) trường `turn` (dòng 154) tính sau khi đã thêm câu hỏi nên **lệch 1**: sau 5 câu, request kế tiếp báo `turn 7` thay vì 6.

### Exercise 5.4: Load balancing (Nginx + 3 agent)

Chạy trong `05-scaling-reliability/production/` (đã `touch .env.local`, file này được gitignore):

```bash
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
$ docker compose -p k5-day14-scaling ps
NAME                       SERVICE   STATUS                    PORTS
k5-day14-scaling-agent-1   agent     Up 8 seconds (healthy)    8000/tcp
k5-day14-scaling-agent-2   agent     Up 8 seconds (healthy)    8000/tcp
k5-day14-scaling-agent-3   agent     Up 7 seconds (healthy)    8000/tcp
k5-day14-scaling-nginx-1   nginx     Up 7 seconds              0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   redis     Up 19 seconds (healthy)   6379/tcp
```

10 request `POST http://localhost:8080/chat` (mỗi request một session mới), header `X-Served-By` là IP của agent mà Nginx chọn:

```text
X-Served-By: 172.21.0.3:8000  served_by= instance-375032  storage= redis
X-Served-By: 172.21.0.4:8000  served_by= instance-d5b6c1  storage= redis
X-Served-By: 172.21.0.5:8000  served_by= instance-307357  storage= redis
X-Served-By: 172.21.0.3:8000  ... (lặp lại theo vòng 3 instance)
```

- **Cách phân tải:** upstream `agent_cluster` trỏ `server agent:8000` (`nginx.conf`); Docker DNS trả về IP của 3 container, Nginx chia đều theo vòng (round-robin), đúng như thấy: ba địa chỉ lặp lại theo thứ tự. Chỉ Nginx mở cổng ra ngoài (8080), agent không mở cổng ra host.
- **Chịu lỗi:** `proxy_next_upstream error timeout http_503` với `proxy_next_upstream_tries 3` nghĩa là nếu một instance lỗi, timeout hoặc trả 503 (ví dụ đang shutdown) thì Nginx thử instance khác.
- Lưu ý: cổng Nginx là **8080** và endpoint là `/chat`, khác với CODE_LAB ghi cổng 80 và `/ask`.

### Exercise 5.5: Test stateless

```bash
$ python test_stateless.py
Session ID: 283f62b2-0d91-4476-a203-a99c817e22e0
Request 1: [instance-d5b6c1]
Request 2: [instance-307357]
Request 3: [instance-375032]
Request 4: [instance-d5b6c1]
Request 5: [instance-307357]
Instances used: {'instance-d5b6c1', 'instance-307357', 'instance-375032'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:** 5 câu hỏi cùng một `session_id` được 3 instance khác nhau xử lý, vậy mà history đọc lại có đủ **10 message** (5 câu hỏi + 5 trả lời) theo đúng thứ tự. Điều đó chứng minh state không nằm trong RAM của instance nào mà nằm ở Redis dùng chung.

README ghi script này không tự tắt instance nào, nên tôi tự làm thêm phần "kill instance" của CODE_LAB: dừng `k5-day14-scaling-agent-1` bằng `docker stop`, rồi gọi tiếp 3 request với cùng session:

```text
dừng: k5-day14-scaling-agent-1
turn 7 served_by instance-d5b6c1
turn 8 served_by instance-307357
turn 9 served_by instance-d5b6c1
history count = 16      (10 + 3 × 2)
```

Cả 3 request vẫn thành công do hai instance còn lại phục vụ; history tăng đúng lên 16 message, không mất cuộc hội thoại. Xong dọn bằng `docker compose -p k5-day14-scaling down`; cổng 8080 đã đóng sau đó.

Hạn chế của phép thử: tôi không quan sát được Nginx có phải retry sang instance khác hay không (không có log lỗi nào được ghi lại), nên không khẳng định cơ chế `proxy_next_upstream` đã chạy trong lần thử này.

---

## Output của `python check_production_ready.py` (CP5)

Chạy trong WSL2 Ubuntu (`os.name == posix`), thư mục `06-lab-complete/`, Docker Desktop bật, Python 3.12 (`pip install -r requirements.txt`), lệnh `python check_production_ready.py` (chế độ đầy đủ, không `--skip-docker`), ngày 2026-11-26:

```text
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
```

Số đo trong lần chạy này: image `63 MB`; `docker stop` thoát với exit code 0 sau 0.8 giây; rate limit trả 429 sau 5 request thành công (`RATE_LIMIT_PER_MINUTE=5`), restart agent vẫn 429; budget `0.000001` USD trả 402.

---



