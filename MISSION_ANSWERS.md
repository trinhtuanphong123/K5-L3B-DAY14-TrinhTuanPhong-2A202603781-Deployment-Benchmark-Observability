# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Phân tích file `01-localhost-vs-production/develop/app.py` (54 dòng).

| # | Anti-pattern | Vị trí (`file:dòng`) | Vì sao nguy hiểm |
|---|---|---|---|
| 1 | API key và mật khẩu database hardcode trong code | `develop/app.py:17-18` | Push lên GitHub là lộ key: bot của hacker quét tự động GitHub để tìm key bị lộ rồi dùng trái phép, gây tốn tiền và rò rỉ dữ liệu. Xoá file sau đó cũng không đủ vì key vẫn nằm trong lịch sử git |
| 2 | Cấu hình ghi cứng trong code (`DEBUG = True`, `MAX_TOKENS = 500`) | `develop/app.py:21-22` | Khó thay đổi giữa các môi trường (dev/staging/production), mỗi lần đổi phải sửa code và build lại. Dễ để quên `DEBUG` bật ở production |
| 3 | In API key ra log bằng `print` (`Using key: ...`); dùng `print` thay vì logging | `develop/app.py:33-38` (key bị in ở dòng 34) | Log thường được gửi sang hệ thống bên thứ ba hoặc nhiều người đọc được, nên key trong log cũng là lộ key. `print` cũng không có mức độ (level), thời gian hay cấu trúc nên khó tìm lỗi |
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

## Part 3: Cloud Deployment

## Part 4: API Security

## Part 5: Scaling & Reliability

---

## Output của `python check_production_ready.py` (CP5)

---

## AI log

<!-- RULES.md §1: mỗi lần dùng AI cho code Part 6 hoặc cho câu trả lời, ghi: hỏi gì · nhận gì · bạn tự sửa/kiểm tra thế nào. -->

| Ngày | Checkpoint | Hỏi AI gì | AI trả lời/làm gì | Tôi tự kiểm tra / sửa thế nào |
|---|---|---|---|---|
| 2026-11-26 | CP0 | Hỏi Claude cách cài WSL2/Ubuntu, Docker integration và Python 3.12 (vì Python 3.14 không cài được `requirements.txt`) | Claude đề xuất và chạy các lệnh cài Ubuntu, `uv`, Python 3.12 | Tôi tự bật WSL integration trong Docker Desktop, tạo user Ubuntu, chạy lại `docker run hello-world` và `python -c "import os; print(os.name)"` (in `posix`) |
| 2026-11-26 | CP1 | Nhờ Claude chạy bản develop/production của Part 1 và soạn mục 1.2, 1.3, rà soát số dòng ở 1.1 | Claude chạy `curl` và SIGTERM, soạn nội dung 1.2 và 1.3, sửa số dòng ở 1.1 | Tôi tự viết 1.1 ban đầu (có sai số dòng ở mục 3 và 5), Claude sửa lại; tôi đọc lại 1.1, 1.2, 1.3 và đối chiếu với `develop/app.py` và `production/app.py` |
