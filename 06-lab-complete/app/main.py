"""
Production AI Agent — Part 6 Final Project

Endpoints:
  GET  /health  — liveness: luôn 200 khi process còn chạy, không chạm Redis
  GET  /ready   — readiness: 200 khi Redis ping được, 503 khi không
  POST /ask     — hỏi agent (auth / rate limit / cost guard nối vào ở các task sau)

Log: mỗi dòng log của app là một JSON object (JsonFormatter gắn vào root logger).
Lỗi: input sai → 422 {"error": "invalid_input"}, lỗi bất ngờ → 500 {"error": "internal_error"};
stack trace chỉ nằm trong log, không trả cho client.
Graceful shutdown: uvicorn xử lý SIGTERM, lifespan ghi log shutdown và đóng Redis.
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            data.update(fields)
        if record.exc_info:
            data["exc_type"] = record.exc_info[0].__name__
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)


setup_logging()
logger = logging.getLogger("agent")
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup",
        extra={
            "fields": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    if settings.agent_api_key == "":
        logger.warning(
            "AGENT_API_KEY is empty - every /ask request will be rejected with 401",
            extra={"fields": {"event": "config_warning"}},
        )
    yield
    logger.info("shutdown", extra={"fields": {"event": "shutdown"}})
    try:
        r.close()
    except Exception:
        pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        ms = round((time.perf_counter() - start) * 1000, 1)
        logger.error(
            "request",
            extra={
                "fields": {
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "ms": ms,
                }
            },
        )
        raise
    ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "request",
        extra={
            "fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": ms,
            }
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "invalid_input",
            "detail": [
                {"loc": [str(x) for x in e.get("loc", ())], "msg": e.get("msg", "")}
                for e in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_error",
        exc_info=exc,
        extra={"fields": {"event": "unhandled_error", "path": request.url.path}},
    )
    return JSONResponse(status_code=500, content={"error": "internal_error"})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready() -> dict:
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)) -> dict:
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    input_tokens = len(body.question.split()) * 2
    output_tokens = len(answer.split()) * 2
    cost = record_cost(input_tokens, output_tokens)
    return {
        "question": body.question,
        "answer": answer,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 8),
        },
    }
