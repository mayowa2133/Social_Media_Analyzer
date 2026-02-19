# IG/TikTok Parity Execution Checklist

Last updated: 2026-02-19
Owner: Codex + Mayowa
Mode: Hybrid safe (official/provider data + user imports/capture, no external media download by default)

## Goal
Reach functional parity for IG/TikTok competitor discovery and media download workflows so non-YouTube users can complete full product loops.

## Phase Tracker

- [x] `Phase 0` Create execution checklist in-repo and map to concrete files.
- [x] `Phase 1` Discovery engine foundation (provider-based discovery service + deterministic merge/dedupe).
- [x] `Phase 2` Discovery expansion for IG/TikTok quality and confidence signals.
- [x] `Phase 3` Media download pipeline parity for IG/TikTok (queued jobs + status + audit integration).
- [ ] `Phase 4` UI integration and fallback UX hardening.
- [ ] `Phase 5` Test + smoke coverage expansion for parity workflows.

## File-Mapped Execution Plan

### Phase 1: Discovery Engine Foundation (completed)
- [x] Extract `/competitors/discover` logic into dedicated service module.
  - Target files:
    - `apps/api/services/competitor_discovery.py` (new)
    - `apps/api/routers/competitor.py`
- [x] Implement provider interfaces:
  - `official_api`
  - `research_corpus`
  - `manual_url_seed`
  - Target file: `apps/api/services/competitor_discovery.py`
- [x] Add deterministic merge + dedupe with shared identity tokens.
  - Target files:
    - `apps/api/services/competitor_discovery.py`
    - `apps/api/services/identity.py` (if helper changes needed)
- [x] Keep endpoint response backward-compatible (`DiscoverCompetitorsResponse` unchanged).
  - Target file: `apps/api/routers/competitor.py`
- [x] Add/adjust tests for deterministic ranking and dedupe.
  - Target files:
    - `apps/api/tests/test_parity_hardening.py`
    - `apps/api/tests/test_competitor_discovery.py` (optional new)

### Phase 2: Discovery Expansion (completed)
- [x] Add confidence tier and evidence fields to discovery response (additive).
  - Target files:
    - `apps/api/routers/competitor.py`
    - `apps/api/services/competitor_discovery.py`
    - `apps/web/src/lib/api.ts`
    - `apps/web/src/app/competitors/page.tsx` (or route file path in repo)
- [x] Expand IG/TikTok candidate sourcing beyond local-only fallbacks where provider data exists.
  - Target files:
    - `apps/api/services/competitor_discovery.py`
    - `apps/api/services/connectors/*`
- [x] Add deterministic pagination stability checks.
  - Target files:
    - `apps/api/tests/test_parity_hardening.py`
    - `apps/api/tests/test_competitor_discovery.py`

### Phase 2 Detailed Execution (completed)
- [x] 2.1 Add additive response metadata:
  - `confidence_tier: low|medium|high`
  - `evidence: string[]`
- [x] 2.2 Add additional discovery provider for IG/TikTok:
  - shared competitor graph source (cross-user public handle corpus with dedupe)
  - maintain user-scoped tracking flagging (`already_tracked`)
- [x] 2.3 Improve ranking confidence:
  - source fusion bonus when candidate appears in multiple sources
  - deterministic confidence tier assignment from source_count + metric coverage
- [x] 2.4 Frontend parity surfacing:
  - show confidence badge
  - show first 1-2 evidence bullets
  - keep existing discover import workflow intact
- [x] 2.5 Tests and verification:
  - API tests for confidence/evidence presence and pagination stability
  - run full API suite + smoke + typecheck

### Phase 3: Media Download Pipeline Parity (planned)
- [x] Add media download job endpoints (`POST /media/download`, `GET /media/download/{job_id}`).
  - Target files:
    - `apps/api/routers/media.py` (new)
    - `apps/api/main.py`
- [x] Add durable job + asset models.
  - Target files:
    - `apps/api/models/media_download_job.py` (new)
    - `apps/api/models/media_asset.py` (new)
    - `apps/api/models/__init__.py`
- [x] Add queued processing service with retries/timeouts.
  - Target files:
    - `apps/api/services/media_download.py` (new)
    - `apps/api/services/audit_queue.py`
- [x] Integrate downloaded assets into audit flow.
  - Target files:
    - `apps/api/routers/audit.py`
    - `apps/api/services/audit.py`

### Phase 3 Detailed Execution (completed)
- [x] 3.1 Data model layer:
  - add `MediaDownloadJob` and `MediaAsset` SQLAlchemy models
  - wire into `models/__init__.py` + user/upload relationships
- [x] 3.2 Queue/runtime layer:
  - add `MEDIA_QUEUE_NAME` and enqueue helper in `services/audit_queue.py`
  - update `worker.py` to consume audit + media queues
  - add stale media job recovery at startup in `main.py`
- [x] 3.3 Media processing service:
  - implement `services/media_download.py` with async pipeline:
    - queued -> downloading -> processing -> completed/failed
    - create `Upload` + `MediaAsset`, attach IDs to job
    - durable status/error tracking
- [x] 3.4 API surface:
  - implement `POST /media/download`
  - implement `GET /media/download/{job_id}`
  - enforce feature flag `ALLOW_EXTERNAL_MEDIA_DOWNLOAD`
  - user scoping and deterministic error messages
- [x] 3.5 Validation:
  - add integration tests for:
    - successful queued download completion (mocked downloader)
    - queue unavailable/failure path
    - user scoping on job retrieval
  - run full API + typecheck + smoke + build

### Phase 4: UX Integration (planned)
- [ ] Competitors page: provider source filters, confidence chips, import actions.
  - Target files:
    - `apps/web/src/app/competitors/page.tsx`
    - `apps/web/src/lib/api.ts`
- [ ] Audit page: download job submit/poll/select asset workflow.
  - Target files:
    - `apps/web/src/app/audit/new/page.tsx`
    - `apps/web/src/lib/api.ts`

### Phase 5: Test/CI Expansion (planned)
- [ ] API tests for discovery provider merge/dedupe and pagination stability.
  - Target files:
    - `apps/api/tests/test_parity_hardening.py`
    - `apps/api/tests/test_competitor_discovery.py`
- [ ] API tests for media download job lifecycle.
  - Target files:
    - `apps/api/tests/test_media_download.py` (new)
- [ ] Playwright parity smoke:
  - `connect/manual -> discover -> import -> download -> audit -> report`
  - Target files:
    - `apps/web/tests/smoke.spec.ts`

## Progress Notes

- 2026-02-19: Checklist created and Phase 1 kickoff started.
- 2026-02-19: Phase 1 completed.
  - Added provider-based discovery service in `apps/api/services/competitor_discovery.py`.
  - Wired router endpoint to service in `apps/api/routers/competitor.py`.
  - Added parity test coverage in `apps/api/tests/test_parity_hardening.py`.
  - Verified with `43 passed` on API suite (`pytest -q tests analysis/tests`).
- 2026-02-19: Phase 2 completed.
  - Added discovery confidence and evidence fields (`confidence_tier`, `evidence`, `source_count`, `source_labels`).
  - Added IG/TikTok discovery enrichment via `community_graph` provider in `apps/api/services/competitor_discovery.py`.
  - Added UI surfacing + filtering for discovery confidence/source in `apps/web/src/app/competitors/page.tsx`.
  - Added deterministic pagination and enrichment tests in `apps/api/tests/test_parity_hardening.py`.
  - Verified with:
    - `pytest -q tests/test_parity_hardening.py` -> `6 passed`
    - `pytest -q tests analysis/tests` -> `45 passed`
    - `npx tsc --noEmit` -> pass
    - `npx playwright test tests/smoke.spec.ts --reporter=list` -> `5 passed`
    - `npm run build` -> pass
- 2026-02-19: Phase 3 completed.
  - Added durable media models:
    - `apps/api/models/media_download_job.py`
    - `apps/api/models/media_asset.py`
  - Added media queue/runtime support:
    - `apps/api/services/audit_queue.py` (`MEDIA_QUEUE_NAME`, enqueue helper, stale-job recovery)
    - `apps/api/worker.py` (worker now consumes audit + media queues)
    - `apps/api/main.py` (startup media stale recovery)
  - Added media pipeline service:
    - `apps/api/services/media_download.py`
  - Added API endpoints:
    - `POST /media/download`
    - `GET /media/download/{job_id}`
    - in `apps/api/routers/media.py` and mounted in `apps/api/main.py`
  - Added web API client bindings:
    - `createMediaDownloadJob`, `getMediaDownloadJobStatus` in `apps/web/src/lib/api.ts`
  - Added integration tests:
    - `apps/api/tests/test_media_download.py`
  - Verified with:
    - `pytest -q tests/test_media_download.py` -> `3 passed`
    - `pytest -q tests/test_audit_router_upload.py tests/test_parity_hardening.py` -> `8 passed`
    - `pytest -q tests analysis/tests` -> `48 passed`
    - `npx playwright test tests/smoke.spec.ts --reporter=list` -> `5 passed`
    - `npm run build` -> pass
    - `npx tsc --noEmit` -> pass
