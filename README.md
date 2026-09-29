# Dilip — Autonomous Incident Triage Agent

An AI agent that triages IT incidents with LangGraph + Gemini + Supabase pgvector + HITL approval.

## Quick Start

```powershell
# 1. Create venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install
pip install -r requirements.txt

# 3. Run SQL migration in Supabase SQL Editor
#    (paste contents of db/migrations/001_incident_docs.sql)

# 4. Seed runbooks
python .\seed_rag.py
python .\seed_rag.py   # run twice to confirm idempotency

# 5. Run tests
pytest -q

# 6. Start app
python app.py
# UI  → http://localhost:7860
# API → http://localhost:7860/docs
```

## Stack
| Layer | Technology |
|-------|-----------|
| LLM | Gemini 1.5 Flash |
| Embeddings | Gemini text-embedding-004 (768 dims) |
| Vector DB | Supabase Postgres + pgvector |
| Agent | LangGraph + PostgresSaver (HITL interrupt) |
| API | FastAPI |
| UI | Gradio Blocks |
| Hosting | Render (free tier) |

## API
| Method | Path | Description |
|--------|------|-------------|
| GET | /healthz | Health check (no external calls) |
| POST | /chat | Start triage → COMPLETED \| AWAITING_APPROVAL |
| POST | /approve | Resume → RESOLVED \| REJECTED_AND_RESUMED \| 400 |

## Render Deploy
Push to GitHub → Render **New → Blueprint** (render.yaml) → add `GEMINI_API_KEY` and `DATABASE_URL` env vars → Deploy.

> Free tier note: spins down after 15 min idle; state survives in Postgres.
