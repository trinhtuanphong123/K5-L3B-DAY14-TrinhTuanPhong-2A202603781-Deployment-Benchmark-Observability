# Deployment Information

## Public URL

https://k5-day14-agent-jilo.onrender.com

## Platform

Render (Blueprint). Deploy chính agent Part 6 trong `06-lab-complete/`, đọc cấu hình từ `06-lab-complete/render.yaml` (Blueprint Path = `06-lab-complete/render.yaml`, `rootDir: 06-lab-complete`).

| Resource | Loại | Plan / Region |
|---|---|---|
| `k5-day14-agent` | Web Service, runtime Docker (build từ `06-lab-complete/Dockerfile`) | Free · Singapore |
| `k5-day14-redis` | Key Value (Redis-compatible), chỉ cho kết nối nội bộ (`ipAllowList: []`) | Free · Singapore |

Health check của Render: `healthCheckPath: /health`.

## Test Commands

Đặt `BASE=https://k5-day14-agent-jilo.onrender.com` và `AGENT_API_KEY` là key đã đặt trên Render (key không ghi trong repo). Mỗi lệnh chỉ in mã HTTP:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả chạy ngày 2026-11-26: `200`, `200`, `401`, `200`.

### Health Check

```bash
curl https://k5-day14-agent-jilo.onrender.com/health
# {"status":"ok","environment":"production","uptime_seconds":136.6}
```

### API Test (with authentication)

```bash
curl -X POST https://k5-day14-agent-jilo.onrender.com/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deployment?"}'
# {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.","usage":{"input_tokens":6,"output_tokens":32,"cost_usd":2.01e-05}}
```

`python check_production_ready.py --static-only --public-url https://k5-day14-agent-jilo.onrender.com` → `✅ Public URL: GET https://k5-day14-agent-jilo.onrender.com/health → 200`.

Lưu ý: gói Free của Render cho service "ngủ" sau khoảng 15 phút không có request; request đầu tiên sau đó có thể mất tới khoảng 1 phút.

## Environment Variables Set

Đặt trên Render (khai báo trong `render.yaml`, không có giá trị secret nào trong code hay repo):

| Biến | Nguồn |
|---|---|
| `AGENT_API_KEY` | secret, `sync: false` — nhập trên Render Dashboard khi tạo Blueprint |
| `REDIS_URL` | `fromService` → Key Value `k5-day14-redis`, `property: connectionString` |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `PORT` | Render tự cấp; `CMD` trong Dockerfile nghe theo `${PORT:-8000}` |
| `LOG_LEVEL` | không đặt → mặc định `INFO` trong `app/config.py` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
