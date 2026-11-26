# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Trịnh Tuấn Phong — 2A202603781
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11 + WSL2 Ubuntu (kernel 6.6.87.2), 16 vCPU / 6.7 GiB RAM cấp cho WSL, Python 3.12.16. Phần `develop/` chạy trực tiếp bằng Python (không Docker), load generator và agent cùng một máy.

Số liệu mục 2–3 lấy từ `06-lab-complete/benchmark-observability/develop/reports/*.json` (bản copy ở `reports/` gốc repo khi nộp).

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Đúng ngưỡng `--slo-p95-ms` mặc định của `load_test.py`, nên cột SLO trong JSON khớp với bảng này. Khi chưa nghẽn, p95 đo được khoảng 220–240 ms (c = 1–50), nên ngưỡng 500 ms còn dư khoảng 2 lần cho mạng và cloud. Vượt 500 ms là dấu hiệu đã nghẽn (c = 100) hoặc tail latency lan rộng (`MOCK_SLOW_RATE=0.1`). |
| Error rate `/ask` | ≤ 2 % | Mock LLM có sẵn khoảng 1 % lỗi upstream (`MOCK_ERROR_RATE=0.01`), nên SLO phải cao hơn mức nền này. 2 % là gấp đôi mức nền và cũng là ngưỡng `--slo-error-rate` mặc định. Error budget là 2 % số request. |
| Accuracy trên golden dataset | ≥ 80 %, không regression | Ngưỡng `--min-accuracy` mặc định của `run_eval.py`, dùng làm quality gate. Quan trọng hơn ngưỡng là điều kiện "không câu nào baseline đúng mà giờ sai". Lần eval sau khi sửa KB chạy với ngưỡng chặt hơn, `--min-accuracy 1.0`. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Mỗi mức: `--requests 300`, file `reports/load_v2_c{1,10,50,100}.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.41 | 187.6 | 217.6 | 1681.3 | 0.33% | ✅ PASS |
| 10 | 36.97 | 191.3 | 222.0 | 1704.5 | 1.67% | ✅ PASS |
| 50 | 113.4 | 194.3 | 239.9 | 1700.2 | 1.00% | ✅ PASS |
| 100 | 63.78 | 327.4 | 2962.4 | 3167.3 | 2.00% | ❌ FAIL (p95) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. RPS chỉ tăng gần tuyến tính khi chưa có tài nguyên nào bão hoà, sau đó đứng lại rồi tụt.

- Theo Little's law, RPS ≈ concurrency / latency trung bình. Ở c = 1: 1 / 0.2272 s ≈ 4.4 req/s, khớp với 4.41 đo được. Ở c = 10, RPS tăng khoảng 8.4 lần (36.97), còn p50 gần như không đổi (187.6 → 191.3 ms). Agent vẫn trả lời nhanh như cũ, chỉ là phục vụ được nhiều request cùng lúc hơn, vì mock LLM là `asyncio.sleep` nên không chặn event loop.
- Ở c = 50, RPS chỉ là 113.4, thấp hơn mức Little's law dự đoán (50 / 0.2305 s ≈ 217). Nguyên nhân là lần đo quá ngắn: 300 request chia cho 50 worker, mỗi worker chỉ chạy 6 request. Tổng thời gian 2.65 s bị kéo dài bởi worker gặp request chậm (max 1720.9 ms). Tail latency làm cả lần đo kéo dài theo, nên RPS bị thấp đi.
- Ở c = 100, RPS tụt còn 63.78, p50 tăng lên 327.4 ms và p95 lên 2962.4 ms (vi phạm SLO). Tôi quan sát thêm bằng `top` trong lúc chạy tải c = 100 (chỉ để tìm nguyên nhân, không phải số liệu benchmark): process `load_test.py` (một process asyncio) chạy kín một core CPU, còn process agent gần như rảnh. Vậy nút thắt nằm ở **máy tạo tải**, không phải agent. Latency đo được ở c = 100 gồm cả thời gian request chờ trong event loop của client. Muốn đo đúng ở concurrency cao cần nhiều process tạo tải (Locust có nhiều worker, như ở CP8) hoặc chạy client trên máy khác.

### 2.2 Tail latency

Mỗi mức: bật lại v2 với `MOCK_SLOW_RATE` tương ứng, `--requests 300 --concurrency 20`, file `reports/load_v2_slow_{0,0.03,0.1}.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 192.2 | 218.1 | 225.7 |
| 0.03 (mặc định) | 245.7 | 221.8 | 1697.2 |
| 0.1 | 346.0 | 1690.8 | 1711.4 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- Percentile cao nhạy nhất, và percentile nào nhảy phụ thuộc vào tỉ lệ request chậm. Với 3 % request chậm, chỉ p99 nhảy (225.7 → 1697.2 ms, khoảng 7.5 lần), còn p95 gần như đứng yên (218.1 → 221.8 ms), vì 3 % < 5 % nên request chậm chưa lọt vào ngưỡng p95. Với 10 % request chậm (> 5 %), p95 cũng nhảy lên 1690.8 ms.
- Average chỉ tăng từ 192.2 → 245.7 → 346.0 ms. Ở `MOCK_SLOW_RATE=0.1`, avg 346 ms vẫn "đạt" một SLO 500 ms nếu đặt theo average, trong khi khoảng 10 % người dùng phải chờ hơn 1.6 s. Average trộn vài request rất chậm vào số đông request nhanh nên che mất chúng. SLO theo p95/p99 nói thẳng "x % request nhanh hơn ngưỡng", gắn trực tiếp với trải nghiệm người dùng. Đặt SLO theo p95 thì bắt được lần chạy 0.1 (FAIL), đặt theo p99 thì bắt được cả lần chạy mặc định 0.03.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

File: `reports/eval_v1.json`, `reports/eval_v2.json` (baseline v1), `reports/eval_v2_fixed.json` (baseline v2, `--min-accuracy 1.0`).

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.6 | 109.1 | 116.3 |
| Tổng cost (USD) | 0.000411 | 0.000762 | 0.000814 |
| Cost / câu đúng (USD) | 0.00041115 | 0.00003627 | 0.00003537 |
| Latency p95 eval (ms) | 188.0 | 214.6 | 220.0 |
| Quality gate | FAIL (min 80%, 0 regression) | PASS (min 80%, 0 regression) | PASS (min 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | Không entry nào trong `KNOWLEDGE_BASE` có trigger khớp câu hỏi, nên retrieval rỗng và agent trả câu chung chung. Thêm entry trigger `["jwt", "api key"]`, nội dung nói JWT là token có thời điểm hết hạn (exp), server kiểm chữ ký, khác API key cố định. |
| `scaling-03` ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Cùng nguyên nhân. Thêm entry trigger `["hpa", "kubernetes", "autoscaling"]`, nội dung nói HPA scale theo CPU, memory hoặc custom metrics. |

Trigger được chọn để không xuất hiện trong 21 câu còn lại (không dùng từ rộng như `scale`, `token`). Trước khi chạy lại eval, tôi kiểm bằng `retrieve_context()` cho cả 23 câu: 21 câu cũ vẫn lấy đúng tài liệu cũ. Eval cuối: 2 câu được cải thiện, 0 regression, `Quality gate (accuracy ≥ 100%, không regression): ✅ PASS`.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- v2 có retrieval nên prompt dài hơn: số token mỗi câu tăng khoảng 1.9 lần (57.6 → 109.1), tổng cost tăng khoảng 1.85 lần (0.000411 → 0.000762 USD), và p95 tăng 26.6 ms (188.0 → 214.6 ms) do bước tìm tài liệu và prompt dài hơn.
- Đổi lại, accuracy tăng từ 4.3 % lên 91.3 %, nên **cost / câu đúng giảm khoảng 11 lần** (0.00041115 → 0.00003627 USD). Nếu chỉ so "cost / câu" thì v1 trông rẻ hơn, nhưng gần như toàn bộ câu trả lời của v1 là sai, tức tiền bỏ ra không mua được gì. Cost / câu đúng mới cho biết bao nhiêu tiền thì mua được một câu trả lời dùng được.
- Sửa KB làm tokens tăng nhẹ (109.1 → 116.3) và tổng cost tăng thêm 0.000052 USD, nhưng cost / câu đúng còn giảm tiếp (0.00003537). Latency gần như không đổi (p95 220.0 ms) và vẫn trong SLO 500 ms.

### 3.1 Quality gate trong CI (Bài tập 4)

`python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json` (v1 so với baseline v2) trả **exit code 1**: accuracy 4.3 % < 80 % và có 20 câu regression. `run_eval.py` kết thúc bằng `raise SystemExit(0 if gate_ok else 1)`, mà GitHub Actions coi mọi bước có exit code khác 0 là fail. Job đỏ thì, nếu branch `main` bật branch protection "Require status checks to pass", PR không merge được.

Bước GitHub Actions mẫu (chưa đặt vào `.github/workflows/` của repo này):

```yaml
name: eval-gate
on: pull_request
jobs:
  eval:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 06-lab-complete/benchmark-observability/develop
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Start agent v2
        run: |
          AGENT_VERSION=v2 PORT=8002 python app.py &
          for i in $(seq 1 30); do curl -sf http://localhost:8002/health && break; sleep 1; done
      - name: Quality gate (exit 1 → job fail → PR bị chặn merge)
        run: python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2_fixed.json
```

Baseline `reports/eval_v2_fixed.json` được commit cùng repo, nên mỗi PR được so với phiên bản đang chạy tốt. `run_eval.py` có retry 1 lần cho lỗi 5xx, giúp lỗi upstream ngẫu nhiên khoảng 1 % của mock không làm gate fail oan.

---

## 4. Observability stack (production)

Stack: `06-lab-complete/benchmark-observability/production/`, chạy bằng `docker compose -p k5-day14-observability`, 3 instance agent, tải nền Locust headless 30 user / ramp 5 (Exercise 7.4). Một thay đổi so với bản gốc: `production/Dockerfile` thêm `ENV PYTHONUSERBASE=/home/agent/.local`. Thiếu dòng này thì container crash vòng lặp với `ModuleNotFoundError: No module named 'uvicorn'`, vì `useradd -d /app` đặt HOME là `/app` trong khi package nằm ở `/home/agent/.local`. Cách sửa đúng như `CODE_LAB.md:821`.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với 2 alert cùng **firing** (`AgentHighErrorRate` và `AgentHighLatencyP95`, nhóm `agent-slo` FIRING (2)): [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời Exercise 7.4** (30 user, 3 instance):

1. **p95 và avg:** ảnh Grafana cho p95 `/ask` = **292.01 ms** (ô Latency). Trên biểu đồ "Latency /ask — p50 / p95 / p99", đường avg nằm khoảng 240 ms, còn p99 nằm gần 1.8 s. Query Prometheus lúc 22:00:17 cho cùng bức tranh: p95 0.295 s, avg 0.242 s, p99 1.86 s. p95 và avg gần nhau nghĩa là phần lớn request đều nhanh. Khoảng cách lớn nằm giữa avg và p99: khoảng 3 % request bị mock LLM làm chậm thêm 1.5 s (`MOCK_SLOW_RATE=0.03`). Đó là tail latency, và average không cho thấy nó.
2. **Nginx có chia đều không:** có. `sum by (instance) (rate(http_requests_total{route="/ask"}[1m]))` lúc 22:00:17 cho 6.22 / 6.24 / 6.25 req/s cho 3 instance (tổng 18.7 req/s), đúng kiểu round-robin.
3. **Vì sao input tokens/s lớn hơn output tokens/s:** cùng lúc đó input khoảng 1367.5 token/s, output khoảng 725.8 token/s. Prompt gửi vào LLM gồm system prompt, tài liệu retrieve được (RAG context) và câu hỏi, còn output chỉ là câu trả lời. Agent v2 càng nhét nhiều context thì input càng lớn. Vì thế với giá token input và output khác nhau, cost phụ thuộc nhiều vào độ dài context.
4. **`curl http://localhost:8080/metrics`:** trả `HTTP/1.1 404 Not Found` từ `nginx/1.28.3`. `nginx/nginx.conf:20-22` có `location = /metrics` chặn đường này ở cổng public. Chỉ Prometheus được scrape `/metrics`, và nó gọi thẳng từng agent trong mạng nội bộ Docker. Metrics lộ thông tin nội bộ (version, model, cost, lưu lượng) nên không được mở ra internet.

### 4.2 Thí nghiệm "phá hệ thống"

Mỗi thí nghiệm đổi biến môi trường bằng `VAR=... docker compose -p k5-day14-observability up -d --scale agent=3` (D dùng `docker pause`), trong khi tải nền 30 user vẫn chạy. Thời gian tới firing đo bằng script hỏi `GET /api/v1/alerts` của Prometheus mỗi 5 s, tính từ lúc lệnh đổi cấu hình chạy xong.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | **92 s** (pending sau 31 s, rồi `for: 1m`) | Error rate (error rate 21.4 % lúc firing) và "Requests/s theo status code" (đường 503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | **142 s** (pending sau 25 s, rồi `for: 2m`) | "Latency /ask — p50/p95/p99": p95 1.917 s trong khi avg chỉ 0.637 s; LLM p95 1.918 s cho thấy chậm nằm ở LLM |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | **≈ 141 s** (pending sau 21 s theo `activeAt`, rồi `for: 2m`) | LLM cost: $1.76 → $32.0 / giờ (khoảng 18 lần); p95 0.290 → 0.659 s nhưng chưa vượt 1 s nên không có alert latency |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` | **36 s** (pending sau 5 s, rồi `for: 30s`) | Instances: 3 → 2; "Requests/s theo instance": instance bị pause tụt về 0 |
| E | `AGENT_VERSION=v1` | **Không có** | — | Retrieval hit ratio mất dữ liệu (v1 không retrieval); tokens/s giảm (input 1367.5 → 680.2/s); bảng version đổi sang `v1`; p95 thậm chí tốt hơn (0.198 s) |

Ghi chú:
- `LLMCostBurnRateHigh` (ngưỡng $2/giờ) firing ngay ở cấu hình mặc định khi có tải. Cost nền dao động khoảng $1.76–2.43/giờ quanh ngưỡng, nên alert này lúc bật lúc tắt mà không có sự cố. Đó là dấu hiệu ngưỡng đặt quá sát tải bình thường, dễ gây alert fatigue. Tôi giữ nguyên ngưỡng của lab, chỉ ghi lại.
- Trong lúc chạy E, `LLMCostBurnRateHigh` vẫn firing, nhưng đó là phần còn sót của C: cửa sổ `rate(...[5m])` vẫn chứa giai đoạn model large. E không tạo thêm alert nào.
- Ảnh `prometheus-alert-firing.png` chụp ở một lần chạy riêng bật A + B cùng lúc: `AgentHighErrorRate` firing sau 91 s, `AgentHighLatencyP95` firing sau 142 s.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

E là lỗi **chất lượng**, không phải lỗi hạ tầng. Agent v1 vẫn trả 200, nhanh hơn, rẻ hơn, nên mọi metric hạ tầng đều xanh, trong khi accuracy tụt từ 100 % xuống 4.3 % (mục 3). Cách phát hiện:
- **Trước khi deploy:** quality gate trong CI (mục 3.1). `run_eval.py --baseline reports/eval_v2_fixed.json` trả exit 1 với 20 câu regression nên bản này không merge được.
- **Khi đang chạy:**
  - Alert trên metric gián tiếp phản ánh hành vi: retrieval hit ratio giảm đột ngột hoặc mất dữ liệu, tokens/request giảm mạnh, `agent_info` báo version khác version đang mong đợi.
  - Chạy eval định kỳ trên một mẫu traffic hoặc trên golden dataset (online eval, LLM-as-judge).
  - Đo phản hồi người dùng (tỉ lệ thumbs-down, hỏi lại).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được (từ khoảng 3000 trace `/ask` trong 10 phút, qua Jaeger API v3; ảnh `jaeger-slow-trace.png`):

- `trace_id`: `c4018ea7cd805b02b2170bc70be9df0f`
- Tổng thời gian: 1714.7 ms (Jaeger hiển thị Duration 1.7s)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1691.4 ms, 98.6 %). `agent.retrieve_context` chỉ 21.3 ms (1.2 %). Request chậm vì LLM call, không phải vì code của agent hay bước retrieval.
- Dòng log tương ứng (grep theo `trace_id` trong `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-26T14:59:43.535964+00:00", "level": "INFO", "service": "observable-agent", "instance": "4ebe4f0d62e1", "event": "llm_call", "trace_id": "c4018ea7cd805b02b2170bc70be9df0f", "span_id": "c2e00611e3f26b8d", "request_id": "2c48ae6faab1", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1691.2}
{"ts": "2026-11-26T14:59:43.536404+00:00", "level": "INFO", "service": "observable-agent", "instance": "4ebe4f0d62e1", "event": "http_request", "trace_id": "c4018ea7cd805b02b2170bc70be9df0f", "span_id": "c2e00611e3f26b8d", "request_id": "2c48ae6faab1", "method": "POST", "route": "/ask", "status": 200, "ms": 1714.1}
```

Trace lỗi (ảnh `jaeger-error-trace.png`): `trace_id` `448e6f9ef5735fd9fda71c484398b4fc`, 101.4 ms, HTTP 503. Span `chat mock-llm-small` có `error.type = upstream_unavailable` và event `exception` với message `Upstream LLM error: 503 Service Unavailable (mock)`. Log cùng `trace_id`:

```json
{"ts": "2026-11-26T15:01:48.561671+00:00", "level": "INFO", "service": "observable-agent", "instance": "4a96e7cc44a8", "event": "llm_error", "trace_id": "448e6f9ef5735fd9fda71c484398b4fc", "span_id": "5cd168afa6307ed2", "request_id": "36f6ae5c23d2", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T15:01:48.562133+00:00", "level": "INFO", "service": "observable-agent", "instance": "4a96e7cc44a8", "event": "http_request", "trace_id": "448e6f9ef5735fd9fda71c484398b4fc", "span_id": "5cd168afa6307ed2", "request_id": "36f6ae5c23d2", "method": "POST", "route": "/ask", "status": 503, "ms": 100.9}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu là dòng `POST /ask` trong `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv` (RPS làm tròn 2 chữ số; Failures = Failure Count / Request Count).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 60.19 | 190 | 220 | 1700 | 74 / 7186 (1.03%) |
| 3 | 59.89 | 190 | 230 | 1700 | 74 / 7149 (1.04%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Không. Lên 3 instance thì RPS, p50, p95, p99 gần như giữ nguyên (p95 220 → 230 ms nằm trong dao động ngẫu nhiên). Lý do là 1 instance vốn chưa bị quá tải:

- **Thông lượng do mô hình tải quyết định, không do server.** Locust là tải kiểu closed-loop: mỗi user chờ phản hồi xong, nghỉ `between(0.5, 2)` giây (trung bình 1.25 s), rồi mới gửi tiếp. Với 100 user, trần thông lượng xấp xỉ 100 / (1.25 s + khoảng 0.21 s) ≈ 68 req/s, khớp với dòng `Aggregated` trong CSV (66.24 req/s với 1 instance, 65.92 req/s với 3). Thêm instance không làm user gửi nhanh hơn.
- **Latency nằm ở LLM.** p50 190 ms gần đúng bằng latency của mock LLM (120 ms + jitter 0–60 ms + phần theo độ dài prompt). p99 1700 ms là các request dính `MOCK_SLOW_RATE` (+1500 ms). Trace ở mục 4.3 cho thấy span LLM chiếm 98.6 % thời gian request. Thêm instance không làm LLM trả lời nhanh hơn, nên p95/p99 không đổi.
- Failures khoảng 1 % ở cả hai lần là lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0.01`), không phải do thiếu instance.

Scale ngang chỉ có ích khi instance bão hoà: CPU hoặc in-flight cao, request phải xếp hàng, p50 tăng. Muốn thấy khác biệt phải tăng số user hoặc giảm thời gian nghỉ tới khi 1 instance (giới hạn 0.5 CPU) bắt đầu nghẽn. Ở mức tải này, nút thắt là LLM provider.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đọc percentile, không đọc average.** Tail latency do một phụ thuộc (LLM) gây ra chỉ hiện ở p95/p99: avg vẫn "đẹp" trong khi p99 khoảng 1.7 s. Trace cho biết thời gian nằm ở span nào (98.6 % ở LLM), nên biết phải sửa ở đâu thay vì đoán.
  2. **Hiểu công cụ và mô hình tải trước khi kết luận.** `load_test.py` ở c = 100 nghẽn ở chính máy tạo tải (mục 2.1). Locust closed-loop có think time nên scale 1 → 3 instance không đổi gì (mục 5). Số đo phản ánh cả cách đo, không chỉ hệ thống.
  3. **Metric chỉ thấy những gì service đó nhìn thấy, và alert là đánh đổi giữa phát hiện nhanh và báo động giả.** Lỗi chất lượng (E) không làm metric hạ tầng nào đỏ, nên phải có eval/quality gate. `for: 30s`–`2m` làm alert chậm từ 36 s đến khoảng 140 s nhưng tránh báo nhầm khi có spike. Ngưỡng đặt sát tải thường, như alert cost $2/giờ, thì kêu cả khi không có sự cố.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - **Chất lượng:**
    - Điểm online eval / LLM-as-judge trên mẫu traffic.
    - Tỉ lệ phản hồi xấu từ người dùng.
    - Alert khi retrieval hit ratio giảm mạnh, hoặc khi tokens/request lệch xa baseline.
  - **Tầng load balancer và từ bên ngoài:**
    - Metric 5xx/504 và upstream latency của Nginx. Lỗi 504 khi `docker pause` không hiện trong metric của agent.
    - Synthetic probe gọi `/ask` từ bên ngoài.
  - **SLO burn-rate alert nhiều cửa sổ** (vd 1 giờ và 6 giờ), thay cho ngưỡng tức thời: alert theo tốc độ tiêu error budget.
  - **Cost:**
    - Budget theo ngày và cost / câu trả lời đúng.
    - Chỉnh ngưỡng `LLMCostBurnRateHigh` theo tải thật để không báo động giả.
  - **Saturation:** in-flight requests, CPU/RAM từng container, queue time, để biết lúc nào cần scale.
