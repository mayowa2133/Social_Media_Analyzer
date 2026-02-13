# MASTER PROMPT FOR CURSOR — Build "Social Performance Coach"
You are Cursor acting as a senior full-stack engineer + AI engineer. Build a production-ready web app that audits a creator's social performance across YouTube, TikTok, and Instagram, explains *why* engagement is low, and compares against competitors with actionable recommendations.

## 0) Hard Requirements
1) Create a file `PLAN.md` in the repo root and put this entire plan into it.
2) Create a file `PROGRESS.md` in the repo root. This is a running changelog + checklist completion log.
3) Create a file `TODO.md` in the repo root with a task list that mirrors the phases below.
4) As you complete each step, update `PROGRESS.md` and check items in `TODO.md`.
5) Build in small, testable increments. Every phase should end with "definition of done" checks.

## 1) Product Definition (What we're building)
### Core user workflow (MVP)
- User connects YouTube (OAuth) OR pastes a YouTube channel URL.
- User selects 3–10 competitor channel URLs/usernames.
- App fetches recent videos + key metrics, identifies top performers, and extracts patterns.
- User uploads (optional) 1–3 short-form video files for qualitative audit (frame/audio/transcript).
- App returns a structured "Why engagement is low" report:
  - Packaging (titles/thumb/first 3 sec hook)
  - Retention (drop-off points + what happened there)
  - Topic fit / audience mismatch
  - Posting consistency + format fit
  - Competitor blueprint (what's working and why)
- App outputs:
  - A "Next 10 videos" action plan
  - Hook rewrite suggestions
  - Title/thumbnail suggestions (YouTube)
  - Script improvements at drop-off timestamps
  - A/B test ideas

### Non-goals (for MVP)
- No "illegal scraping" baked in. Competitor data must come from:
  - YouTube official API (allowed, easy)
  - TikTok/Instagram: start with **manual upload** of exported analytics + optional third-party connectors behind feature flags (not default).

## 2) Architecture Overview
### Tech stack
- Frontend: Next.js (App Router), TypeScript, Tailwind, shadcn/ui
- Backend: FastAPI (Python) OR Next.js API routes (choose one; prefer FastAPI for AI/video tooling)
- DB: Postgres (Supabase) + Prisma (if Next backend) or SQLAlchemy (if FastAPI)
- Queue: Redis + RQ/Celery OR lightweight background jobs (for video analysis)
- Storage: S3-compatible (Supabase storage or AWS S3)
- AI: OpenAI multimodal model for frame/audio analysis + text model for synthesis
- Video processing: ffmpeg + optional OpenCV
- Transcripts:
  - YouTube captions API where possible
  - If no captions: optional Whisper (server-side) behind a toggle for cost

### Services (modules)
1) `ingestion/` — platform data collectors
2) `analysis/` — metrics analysis, retention heuristics, competitor benchmarking
3) `multimodal/` — frame extraction, audio features, transcript alignment
4) `llm/` — prompts, structured outputs, tool-calling
5) `reporting/` — builds final JSON report + UI rendering

## 3) Repo Structure (Create this first)
Create:
- `apps/web` (Next.js)
- `apps/api` (FastAPI)
- `packages/shared` (shared types, Zod schemas)
- `packages/prompts` (prompt templates + versioning)
- `infra/` (docker-compose, env templates)

Example:
/
  PLAN.md
  TODO.md
  PROGRESS.md
  .env.example
  docker-compose.yml
  apps/
    web/
    api/
  packages/
    shared/
    prompts/
  infra/

## 4) Data Model (DB schema)
Tables:
- users (id, email, created_at)
- connections (id, user_id, platform, access_token_encrypted, refresh_token_encrypted, expires_at)
- profiles (id, user_id, platform, handle, external_id, created_at)
- competitors (id, user_id, platform, handle, external_id)
- videos (id, profile_id, platform, external_id, url, title, published_at, duration_s, thumbnail_url)
- video_metrics (video_id, views, likes, comments, shares, watch_time, avg_view_duration, ctr, retention_points_json, fetched_at)
- audits (id, user_id, status, created_at, input_json, output_json)
- uploads (id, user_id, file_url, file_type, created_at)

Security:
- encrypt tokens at rest
- never log tokens
- least privilege scopes

## 5) Phase Plan (Step-by-step implementation)
### Phase A — Project bootstrap (Day 1)
Tasks:
1) Initialize monorepo structure.
2) Add docker-compose for Postgres + Redis.
3) Add .env.example for web/api.
4) Implement health endpoints:
   - GET /api/health
   - web landing page loads

Definition of done:
- `docker-compose up` works
- web + api run locally
- PLAN/TODO/PROGRESS files exist and are filled

### Phase B — YouTube ingestion (MVP backbone)
Implement YouTube integration first because it's legal + stable:
1) Add Google OAuth on web
2) Store tokens in `connections`
3) Implement YouTube Data API client in `apps/api/ingestion/youtube.py`
4) Fetch:
   - channel metadata
   - last N videos
   - per-video stats (views, likes, comments)
   - transcripts/captions where available

Competitor ingestion:
- user pastes channel URLs
- resolve channelId
- fetch last N videos and stats

Definition of done:
- User connects YouTube
- Competitor channels added
- DB contains videos + metrics
- UI shows a dashboard list of videos and competitor comparisons

### Phase C — Metrics analyzer ("why" from numbers)
Build `analysis/metrics.py`:
Compute:
- Posting cadence (days between uploads)
- Outliers (top 10% videos)
- Topic clusters from titles (simple TF-IDF or embedding clustering)
- Packaging signals:
  - title length
  - keyword presence
  - thumbnail presence (just metadata for now)
- Retention heuristics (YouTube):
  - if avg_view_duration low relative to duration => hook/pacing issue
  - if CTR low but retention good => packaging issue
  - if CTR good but retention low => content mismatch/hook bait

Output a structured JSON "diagnosis" object:
{
  "summary": "...",
  "primary_issue": "PACKAGING|RETENTION|TOPIC_FIT|CONSISTENCY",
  "evidence": [...],
  "recommendations": [...]
}

Definition of done:
- Analyzer produces consistent JSON for a channel + competitors
- UI displays "Primary issue" + top 5 recommendations

### Phase D — Multimodal audit (video file + retention timestamp mapping)
Goal: explain *what happened at second X*.
Inputs:
- uploaded mp4
- optional retention graph points (manual upload or JSON paste for MVP)

Steps:
1) Video processing:
   - extract frames every 0.5s for first 10s, then every 2s afterwards
   - extract audio waveform features (silence detection, volume dips)
2) Transcript:
   - if provided by user, use it
   - else run Whisper (optional toggle)
3) Alignment:
   - map retention drop timestamp to:
     - transcript segment around that time
     - frames around that time
     - audio features around that time
4) LLM multimodal call:
   - feed key frames + transcript snippet + "drop timestamp"
   - ask for reasons + concrete edits

Definition of done:
- Upload a video, supply "drop at 0:03"
- App returns: "At 0:03 you… → fix: …"
- Works reliably on 3 test videos

### Phase E — Competitor blueprint engine (what winners do)
Implement competitor benchmarker:
- For each competitor:
  - compute median length, hook style patterns from titles
  - best performing topics
  - typical posting times (where available)
- Compare user vs competitor deltas
- Generate "do this next" blueprint:
  - "Make 5 videos in format X"
  - "Use hook styles A/B"
  - "Aim for 12–18s average"

Definition of done:
- Competitor comparison page shows:
  - format differences
  - top topic clusters
  - suggested blueprint with quantified targets

### Phase F — Reporting + UX polish
Deliver final "Audit Report" page:
- Executive summary
- Scorecards: Packaging / Retention / Topic fit / Consistency
- Evidence cards with charts
- Action plan:
  - Next 10 videos
  - Hooks to test
  - Titles to test (YouTube)
  - Script edits at timestamps

Definition of done:
- A single "Run Audit" button produces a polished report
- Reports saved in DB and can be reopened

## 6) UI Pages
- / (landing)
- /dashboard (connected profiles, recent audits)
- /connect (OAuth setup)
- /competitors (add/manage competitors)
- /audit/new (upload video + select channel + optional retention input)
- /audit/[id] (report view)

## 7) Observability + Testing
- Add structured logging
- Add unit tests for metrics analyzer
- Add integration test for YouTube ingestion (mock API)
- Add "golden JSON" snapshots for LLM outputs (schema-validated)

## 8) Prompting + Output Schemas (must be strict)
Use Zod schemas in `packages/shared` for:
- Diagnosis schema
- Competitor blueprint schema
- Video timestamp feedback schema
Validate all LLM outputs. If invalid → retry with repair prompt.

## 9) Compliance & Safety Constraints
- No default scraping for IG/TikTok competitors in MVP.
- Add feature flags:
  - ENABLE_TIKTOK_CONNECTORS=false
  - ENABLE_INSTAGRAM_CONNECTORS=false
- Offer manual uploads for those platforms (CSV exports, screenshots later)

## 10) Execution Instructions
Start by creating PLAN.md/TODO.md/PROGRESS.md and scaffolding the repo.
Then implement Phase A → Phase B → Phase C, etc.
After each phase, update PROGRESS.md:
- date/time
- what changed
- what's next
And check off TODO.md items.

Now proceed to implement the project.
