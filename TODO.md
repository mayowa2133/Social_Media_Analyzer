# TODO - Social Performance Coach

## Phase A — Project Bootstrap
- [x] Initialize monorepo structure (apps/web, apps/api, packages/*)
- [x] Add docker-compose for Postgres + Redis
- [x] Add .env.example for web/api
- [x] Implement health endpoints (GET /api/health, web landing page)
- [x] Verify docker-compose up works
- [x] Verify web + api run locally

## Phase B — YouTube Ingestion
- [ ] Add Google OAuth on web
- [ ] Store tokens in `connections` table
- [ ] Implement YouTube Data API client (`apps/api/ingestion/youtube.py`)
- [ ] Fetch channel metadata
- [ ] Fetch last N videos + per-video stats
- [ ] Fetch transcripts/captions where available
- [ ] Implement competitor channel ingestion (paste URL → resolve channelId)
- [ ] Build dashboard UI showing videos + competitor comparisons

## Phase C — Metrics Analyzer
- [ ] Build `analysis/metrics.py`
- [ ] Compute posting cadence (days between uploads)
- [ ] Identify outliers (top 10% videos)
- [ ] Topic clusters from titles (TF-IDF or embedding clustering)
- [ ] Packaging signals (title length, keyword presence, thumbnail metadata)
- [ ] Retention heuristics (CTR vs retention analysis)
- [ ] Output structured JSON diagnosis object
- [ ] UI displays "Primary issue" + top 5 recommendations

## Phase D — Multimodal Audit
- [ ] Video processing: extract frames (0.5s for first 10s, then every 2s)
- [ ] Audio feature extraction (silence detection, volume dips)
- [ ] Transcript alignment (user-provided or Whisper)
- [ ] Map retention drop timestamp to transcript/frames/audio
- [ ] LLM multimodal call for timestamp feedback
- [ ] Test on 3 sample videos

## Phase E — Competitor Blueprint Engine
- [ ] Compute median length, hook style patterns per competitor
- [ ] Identify best performing topics
- [ ] Extract typical posting times
- [ ] Compare user vs competitor deltas
- [ ] Generate "do this next" blueprint with quantified targets
- [ ] Build competitor comparison page

## Phase F — Reporting + UX Polish
- [ ] Build final "Audit Report" page
- [ ] Executive summary
- [ ] Scorecards: Packaging / Retention / Topic fit / Consistency
- [ ] Evidence cards with charts
- [ ] Action plan: Next 10 videos, hooks, titles, script edits
- [ ] Save reports to DB and allow reopening

## Observability + Testing
- [ ] Add structured logging
- [ ] Add unit tests for metrics analyzer
- [ ] Add integration test for YouTube ingestion (mock API)
- [ ] Add golden JSON snapshots for LLM outputs

## UI Pages
- [ ] / (landing)
- [ ] /dashboard (connected profiles, recent audits)
- [ ] /connect (OAuth setup)
- [ ] /competitors (add/manage competitors)
- [ ] /audit/new (upload video + select channel)
- [ ] /audit/[id] (report view)
