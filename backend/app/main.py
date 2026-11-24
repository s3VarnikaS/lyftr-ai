import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

import litellm
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from litellm import Cache

APP_NAME = "Lyftr AI"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
DEFAULT_SYSTEM_PROMPT = "You are Lyftr AI, a helpful, accurate, and friendly assistant."
KEYS = [key.strip() for key in os.getenv("LLM_API_KEYS", "").split(",") if key.strip()]
ENABLE_FAILURE_SIMULATION = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if x.strip()]

# LiteLLM's built-in cache is enabled. A small SQLite response cache alongside it
# makes cache provenance deterministic and survives process restarts.
try:
    litellm.cache = Cache(type="local")
    CACHE_ENABLED = True
except Exception:
    litellm.cache = None
    CACHE_ENABLED = False

app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*", "Content-Type", "X-Simulate-Failure"],
)


def db_path() -> str:
    url = DATABASE_URL
    if url.startswith("sqlite:////"):
        path = "/" + url[len("sqlite:////"):]
    elif url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
    else:
        path = "/data/app.db"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def connect():
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS response_cache (
            cache_key TEXT PRIMARY KEY,
            reply TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""")


@app.on_event("startup")
def startup():
    init_db()


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)
    system_prompt: Optional[str] = None


def fetch_history(session_id: str):
    with connect() as conn:
        rows = conn.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def cache_key(model: str, messages: list) -> str:
    payload = json.dumps({"model": model, "messages": messages}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_simulation(value: Optional[str]):
    failures = {}
    if not value:
        return failures
    for pair in value.split(","):
        if "=" not in pair:
            continue
        key_id, status = pair.strip().split("=", 1)
        try:
            status_int = int(status)
        except ValueError:
            continue
        if status_int in (429, 500, 502, 503):
            failures[key_id.strip()] = status_int
    return failures


def save_message(session_id: str, role: str, content: str, metadata=None):
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata) if metadata is not None else None, datetime.now(timezone.utc).isoformat()),
        )


@app.get("/health")
def health():
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok", "keys_configured": len(KEYS), "cache_enabled": CACHE_ENABLED}


@app.post("/chat")
async def chat(payload: ChatRequest, x_simulate_failure: Optional[str] = Header(default=None, alias="X-Simulate-Failure")):
    message = payload.message.strip()
    session_id = payload.session_id.strip()
    if not session_id or not message:
        raise HTTPException(status_code=422, detail="session_id and message are required")
    if len(message) > 4000:
        raise HTTPException(status_code=422, detail="message must be 4000 characters or fewer")
    if len(session_id) > 128:
        raise HTTPException(status_code=422, detail="session_id must be 128 characters or fewer")
    if len(KEYS) < 2:
        raise HTTPException(status_code=503, detail="two or more LLM_API_KEYS must be configured")

    started = time.perf_counter()
    system_prompt = (payload.system_prompt or DEFAULT_SYSTEM_PROMPT).strip() or DEFAULT_SYSTEM_PROMPT
    history = fetch_history(session_id)
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": message}]
    model = DEFAULT_MODEL
    key = cache_key(model, messages)
    simulated = parse_simulation(x_simulate_failure) if ENABLE_FAILURE_SIMULATION else {}

    # Simulated failures intentionally bypass cache so the failover hook always exercises providers.
    if not simulated:
        with connect() as conn:
            cached = conn.execute("SELECT * FROM response_cache WHERE cache_key=?", (key,)).fetchone()
        if cached:
            latency = max(1, int((time.perf_counter() - started) * 1000))
            metadata = {
                "resolution_source": "LLM_CACHE", "model": cached["model"], "latency_ms": latency,
                "input_tokens": cached["input_tokens"], "output_tokens": cached["output_tokens"],
                "key_id": None, "fallback_attempts": 0,
            }
            save_message(session_id, "user", message)
            save_message(session_id, "assistant", cached["reply"], metadata)
            return {"session_id": session_id, "reply": cached["reply"], "metadata": metadata}

    failures = simulated
    last_error = None
    for index, api_key in enumerate(KEYS):
        key_id = f"key_{index + 1}"
        if "*" in failures or key_id in failures:
            last_error = failures.get(key_id, failures.get("*"))
            continue
        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                api_key=api_key,
                caching=True,
                temperature=0.7,
            )
            reply = response.choices[0].message.content
            if isinstance(reply, list):
                reply = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in reply)
            reply = str(reply or "").strip()
            if not reply:
                raise RuntimeError("provider returned an empty response")
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            latency = max(1, int((time.perf_counter() - started) * 1000))
            metadata = {
                "resolution_source": "LIVE_INFERENCE", "model": model, "latency_ms": latency,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "key_id": key_id, "fallback_attempts": index,
            }
            with connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO response_cache(cache_key, reply, model, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, reply, model, input_tokens, output_tokens, datetime.now(timezone.utc).isoformat()),
                )
            save_message(session_id, "user", message)
            save_message(session_id, "assistant", reply, metadata)
            return {"session_id": session_id, "reply": reply, "metadata": metadata}
        except Exception as exc:
            last_error = exc
            # Continue for rate limits, quota errors, provider errors and 5xx responses.
            continue
    raise HTTPException(status_code=503, detail="all providers unavailable")


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str):
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM messages WHERE session_id=? LIMIT 1", (session_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="session not found")
        rows = conn.execute("SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    messages = []
    for row in rows:
        item = {"role": row["role"], "content": row["content"]}
        if row["metadata"]:
            item["metadata"] = json.loads(row["metadata"])
        messages.append(item)
    return {"session_id": session_id, "messages": messages}
