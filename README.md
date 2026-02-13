# Social Media Analyzer (Social Performance Coach)

YouTube-first social media analytics platform that helps creators understand why some videos outperform others, benchmark against competitors, and generate actionable recommendations.

This repository is a monorepo with:
- `apps/api`: FastAPI backend (YouTube ingestion, analysis, audit pipeline, reports).
- `apps/web`: Next.js frontend (OAuth connect flow, dashboard, competitors, audit workspace, report UI).

## Current MVP Scope

This MVP is currently focused on YouTube.

Implemented:
- Google OAuth connection flow (NextAuth on frontend, encrypted token persistence in backend).
- Channel diagnosis (`packaging`, `consistency`, topic and format-aware analysis).
- Competitor tracking (add/list/remove).
- Competitor recommendations by niche:
  - ranking controls (`subscriber_count`, `avg_views_per_video`, `view_count`)
  - pagination support.
- Strategy blueprint generation with hook intelligence:
  - common hook patterns
  - competitor hook examples
  - format-aware rankings for short-form vs long-form videos.
- Multimodal audit from:
  - YouTube URL
  - local video upload
  - optional retention points.
- Performance likelihood scoring with 3 score sets:
  - competitor metrics
  - platform metrics
  - combined metrics.
- Consolidated report contract and report pages (`/report/latest`, `/report/{audit_id}`).
- Playwright smoke test flow in CI (`connect -> competitors -> audit -> report`).

Out of scope for this MVP:
- Native TikTok and Instagram connectors (disabled).
- Multi-user production hardening.
- Direct retention curve ingest from YouTube Studio API exports.

## High-Level Architecture

Frontend (`apps/web`):
- Next.js App Router + NextAuth (Google OAuth).
- Studio-style pages:
  - `/connect`
  - `/dashboard`
  - `/competitors`
  - `/audit/new`
  - `/report/[id]`

Backend (`apps/api`):
- FastAPI routers:
  - `/auth`
  - `/youtube`
  - `/analysis`
  - `/competitors`
  - `/audit`
  - `/report`
- SQLAlchemy async models/tables:
  - `users`, `connections`, `profiles`
  - `competitors`, `videos`, `video_metrics`
  - `audits`, `uploads`
- Multimodal pipeline:
  - `yt-dlp` (video download for URL mode)
  - `ffmpeg` (frame extraction + duration)
  - audio transcription + LLM analysis (OpenAI optional, deterministic fallback for local/dev).

## Repository Layout

```text
Social_Media_Analyzer/
├── apps/
│   ├── api/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── analysis/
│   │   ├── multimodal/
│   │   ├── models/
│   │   ├── tests/
│   │   └── alembic/
│   └── web/
│       ├── src/app/
│       ├── src/components/
│       ├── src/lib/
│       └── tests/
├── .github/workflows/web-smoke.yml
├── docker-compose.yml
└── .env.example
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm 10+
- PostgreSQL 15+ (or Docker)
- Redis 7+ (or Docker)
- `ffmpeg` installed and available on PATH
- Google Cloud project with:
  - OAuth credentials
  - YouTube Data API key

## Environment Setup

### 1) API env

```bash
cp apps/api/.env.example apps/api/.env
```

Set at least:
- `DATABASE_URL`
- `YOUTUBE_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `ENCRYPTION_KEY`
- `OPENAI_API_KEY` (optional; fallback works without it)

### 2) Web env

```bash
cp apps/web/.env.example apps/web/.env.local
```

Set:
- `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `NEXTAUTH_SECRET` (any strong random value)
- `NEXTAUTH_URL=http://localhost:3000`

### 3) Optional root env (for Docker Compose defaults)

```bash
cp .env.example .env
```

## Running the App Locally

### Option A: Recommended dev flow (local API/web + Docker DB/Redis)

1. Start infra only:

```bash
docker compose up -d postgres redis
```

2. Run API:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host localhost --port 8000 --reload
```

3. Run web:

```bash
cd apps/web
npm install
npm run dev -- --port 3000
```

4. Open:
- Web: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

### Option B: Full Docker Compose

```bash
docker compose up --build
```

Note: If using full compose, verify env files are populated before starting containers.

## Database Bootstrap and Migrations

Two supported paths:

1. Runtime bootstrap (default local dev)
- `AUTO_CREATE_DB_SCHEMA=true`
- API creates missing tables on startup.

2. Alembic migrations (recommended controlled environments)

```bash
cd apps/api
alembic -c alembic.ini upgrade head
```

Initial migration file:
- `apps/api/alembic/versions/20260212_000001_initial_schema.py`

## OAuth Setup Notes (Google)

In Google Cloud Console, configure:
- Authorized JavaScript origins:
  - `http://localhost:3000`
- Authorized redirect URI:
  - `http://localhost:3000/api/auth/callback/google`

Use one hostname consistently (`localhost` recommended).  
Mixing `127.0.0.1` and `localhost` commonly causes connect/sign-in loops.

## Main User Flow

1. Connect account:
- Go to `/connect`
- Click `Connect` for YouTube.

2. Add competitors:
- Go to `/competitors`
- Add a channel URL or handle.
- Optionally use niche suggestions and ranking controls.

3. Generate blueprint:
- In `/competitors`, run `Generate Strategy Blueprint`.

4. Run audit:
- Go to `/audit/new`
- Provide either:
  - YouTube URL, or
  - uploaded video file.
- Optionally add retention points JSON.

5. View report:
- Redirects to `/report/{audit_id}` on completion.
- Latest report always at `/report/latest`.

Legacy route behavior:
- `/audit/[id]` redirects to `/report/[id]`.

## API Surface (MVP)

### Health
- `GET /health`
- `GET /health/ready`
- `GET /health/live`

### Auth
- `GET /auth/me?user_id=...` or `GET /auth/me?email=...`
- `POST /auth/sync/youtube`
- `POST /auth/logout`

### YouTube
- `POST /youtube/resolve`
- `GET /youtube/channel/{channel_id}`
- `GET /youtube/channel/{channel_id}/videos`

Video detail contract uses:
- `view_count`
- `like_count`
- `comment_count`

### Analysis
- `GET /analysis/diagnose/channel/{channel_id}`

### Competitors
- `POST /competitors/`
- `GET /competitors/?user_id=...`
- `DELETE /competitors/{competitor_id}`
- `GET /competitors/{competitor_id}/videos`
- `POST /competitors/recommend`
- `POST /competitors/blueprint`

### Audit
- `POST /audit/upload` (multipart)
- `POST /audit/run_multimodal`
- `GET /audit/?user_id=...`
- `GET /audit/{audit_id}`

### Report
- `GET /report/latest?user_id=...`
- `GET /report/{audit_id}?user_id=...`

## Testing

### Backend tests

```bash
cd apps/api
pytest -q tests analysis/tests
```

### Frontend typecheck and smoke

```bash
cd apps/web
npx tsc --noEmit
npm run smoke
```

Smoke scenario covered:
- connect -> competitors -> audit -> report

## CI

Workflow:
- `.github/workflows/web-smoke.yml`

Job:
- `Playwright Smoke`

Behavior:
- Runs on pull requests that touch `apps/web/**`.
- Executes Playwright smoke in CI mode.
- Uploads Playwright HTML report, traces, screenshots, and videos on failure.

## Troubleshooting

### YouTube connect keeps looping
- Ensure Google OAuth redirect URI is exactly:
  - `http://localhost:3000/api/auth/callback/google`
- Ensure `NEXTAUTH_URL=http://localhost:3000`
- Avoid mixing `127.0.0.1` with `localhost`.

### `YouTube API key not configured`
- Set `YOUTUBE_API_KEY` in `apps/api/.env`.
- Restart API.

### `Could not connect to API` in web
- Confirm API is running on `localhost:8000`.
- Confirm `NEXT_PUBLIC_API_URL` in `apps/web/.env.local`.

### OpenAI key missing
- Expected in local dev.
- Multimodal audit uses deterministic fallback result when OpenAI is unavailable.

### Upload failures
- Max upload size is 300MB.
- Supported formats: `mp4`, `mov`, `m4v`, `webm`, `avi`, `mkv`.

## Security Notes

- OAuth access/refresh tokens are encrypted before persistence (`connections` table).
- Do not commit any `.env` files or credentials.
- Use strong values for `NEXTAUTH_SECRET`, `JWT_SECRET`, and `ENCRYPTION_KEY`.

## Suggested Next Steps

1. Apply the studio UI system to the landing page (`/`) for full visual parity.
2. Add backend API docs/examples for `/competitors/recommend` and `/audit/run_multimodal`.
3. Add API contract tests for performance prediction payloads.
4. Add branch protection rule requiring `Playwright Smoke` before merges.
