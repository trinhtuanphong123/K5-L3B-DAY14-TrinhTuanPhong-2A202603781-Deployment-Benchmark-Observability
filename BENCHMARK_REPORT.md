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

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
