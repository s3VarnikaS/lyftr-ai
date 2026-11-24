# Lyftr AI — LLM Chatbot with Key Failover & Response Caching

A full-stack AI chat application built for the Lyftr full-stack assignment. React + Vite frontend, FastAPI backend, LiteLLM gateway, and SQLite session storage.

## 1. Live URLs

- Frontend: `https://YOUR-PROJECT.vercel.app` (deploy frontend to Vercel)
- Backend: `https://YOUR-SERVICE.onrender.com` (deploy backend to Render)
- Health: `https://YOUR-SERVICE.onrender.com/health`

## 2. Run locally: with Docker and without

### Docker (required path)

1. Copy `.env.example` to `.env` and add two valid Gemini API keys.
2. Run `make up` (or `docker compose up --build -d`).
3. Open http://localhost:3000. Backend runs at http://localhost:8000.
4. Stop with `make down`.

### Without Docker

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export LLM_API_KEYS="key_one,key_two"
export DATABASE_URL="sqlite:///./app.db"
export ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:app --reload --port 8000
```

Frontend (new terminal):

```bash
cd frontend
npm install
# Windows PowerShell: $env:VITE_API_URL="http://localhost:8000"
VITE_API_URL=http://localhost:8000 npm run dev -- --port 3000
```

## 3. Design decisions: key fallback, caching, SQLite session storage

- **Key fallback:** `LLM_API_KEYS` is read in order and assigned stable IDs (`key_1`, `key_2`, ...). Provider errors are caught and the next key is attempted. The client receives a clean JSON 503 only after every key fails.
- **Caching:** LiteLLM's built-in local cache is enabled. A deterministic SQLite response cache uses SHA-256 over the model and the complete message list (system prompt + stored history + new message) to make cache provenance explicit. Cache hits return the exact reply and stored token usage with `key_id: null`.
- **Session history:** User and assistant messages are persisted in SQLite. The client sends only the new message; the server reconstructs the conversation. The system prompt is not persisted or returned by the history endpoint.
- **Tokens and latency:** Token usage is captured from the provider response for each individual request. Latency is measured server-side per request.

## 4. Verification: how to see failover, cache hits and per-message token usage

Health:

```bash
curl https://YOUR-SERVICE.onrender.com/health
```

Send a message (repeat the same first message in a new session to see `LLM_CACHE`):

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/chat \\
  -H 'Content-Type: application/json' \\
  -d '{"session_id":"demo-a","message":"What is the capital of France?"}'
```

Fail over from key 1 to key 2 (use a fresh session/message):

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/chat \\
  -H 'Content-Type: application/json' \\
  -H 'X-Simulate-Failure: key_1=429' \\
  -d '{"session_id":"demo-fallback","message":"Explain cloud computing briefly."}'
```

Expect HTTP 200, `key_id: "key_2"`, and `fallback_attempts: 1`.

Simulate all keys failing:

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/chat \\
  -H 'Content-Type: application/json' \\
  -H 'X-Simulate-Failure: *=429' \\
  -d '{"session_id":"demo-fail","message":"This should not be stored."}'
```

Expect HTTP 503 and `{"detail":"all providers unavailable"}`. Failed requests are not added to history.

Session history:

```bash
curl https://YOUR-SERVICE.onrender.com/sessions/demo-a/messages
```

The UI displays source, model, latency, input tokens, output tokens, and the responding key (when live inference is used) next to each assistant reply.

## 5. Setup Used

- Editor: Visual Studio Code
- AI assistance: ChatGPT
- Frontend: React, Vite, Lucide icons
- Backend: Python, FastAPI, LiteLLM

## 6. Bonus features (if any)

- Dark, responsive chat workspace with starter prompts.
- Optional per-session system prompt.
- Health indicator and copy-response control.
- Persistent response cache in SQLite alongside LiteLLM's local cache.

## Deployment

### Render (backend)

1. Create a new **Web Service** from this repository.
2. Set **Root Directory** to `backend`.
3. Set runtime to Docker and use `backend/Dockerfile`.
4. Add environment variables: `LLM_API_KEYS` (two valid Gemini keys), `LLM_MODEL=gemini/gemini-2.0-flash`, `DATABASE_URL=sqlite:////data/app.db`, `ENABLE_FAILURE_SIMULATION=true`, and `ALLOWED_ORIGINS` containing your Vercel URL.
5. Attach a persistent disk mounted at `/data` (SQLite persistence is required). Deploy and verify `/health`.

### Vercel (frontend)

1. Import this repository into Vercel.
2. Set **Root Directory** to `frontend` and framework preset to Vite.
3. Add `VITE_API_URL` with the deployed Render backend URL (no trailing slash).
4. Deploy. Add the final Vercel origin to Render's `ALLOWED_ORIGINS`, then redeploy the backend.

**Security:** Never commit API keys. Put them only in Render environment variables and your local ignored `.env` file.
