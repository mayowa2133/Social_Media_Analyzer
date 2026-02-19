# Social Performance Coach API

FastAPI backend for Social Media Analyzer.

## What It Supports

- Auth/session sync:
  - `POST /auth/sync/youtube`
  - `POST /auth/sync/social`
  - `GET /auth/me`
- Competitor intelligence:
  - YouTube + Instagram + TikTok competitor tracking
  - research-driven competitor import (`/competitors/import_from_research`)
  - platform-aware blueprint/series/script endpoints
- Audit + reports:
  - upload/url audit entrypoints
  - durable RQ worker processing
  - consolidated + shareable reports
- Research + optimizer + outcomes loop:
  - research import/search/export
  - AI-first script variants + rescore + draft snapshots
  - predicted-vs-actual outcomes + calibration summaries

## Local Setup

1. Install deps:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure env:

```bash
cp .env.example .env
```

Set required values:
- `DATABASE_URL`
- `YOUTUBE_API_KEY`
- `JWT_SECRET` (>=24 chars)
- `ENCRYPTION_KEY` (>=32 chars)

3. Start API:

```bash
uvicorn main:app --host localhost --port 8000 --reload
```

4. Start worker (separate terminal):

```bash
python worker.py
```

## Database Bootstrap

Two supported paths:

1. Runtime bootstrap (local dev default):
- `AUTO_CREATE_DB_SCHEMA=true`
- App runs `Base.metadata.create_all()` at startup.

2. Alembic migrations:

```bash
cd apps/api
alembic -c alembic.ini upgrade head
```

## Tests

```bash
cd apps/api
PYTHONPATH=. pytest -q tests analysis/tests
```

## Notes

- Security startup guard fails boot when `JWT_SECRET`/`ENCRYPTION_KEY` are insecure defaults.
- OpenAI is optional; deterministic fallbacks are built into scoring/optimizer flows.
