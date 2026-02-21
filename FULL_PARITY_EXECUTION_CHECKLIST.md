# Full Parity Execution Checklist (Sortfeed + ViralFindr Functional Coverage)

Last updated: 2026-02-21
Owner: Codex + Mayowa
Mode: Web-only parity with maximum automation

## Goal
Deliver functional parity for discovery/feed workflows while retaining SPC AI scoring/reporting advantages.

## Phase Tracker

- [x] Phase 1: Discovery + canonical feed ranking foundation.
- [x] Phase 2: Favorites/collections bulk ops + export completion.
- [x] Phase 3: Bulk download + transcript jobs from feed items.
- [x] Phase 4: Follow sources + scheduled auto-ingest.
- [x] Phase 5: Repost package workflow.
- [x] Phase 6: Cross-loop integration (discover -> script/audit/report).
- [x] Phase 7: Hardening + rollout telemetry.

## Phase 1 Plan (locked)

1. Add feed discovery/search backend service backed by canonical research items.
2. Add additive API routes:
   - `POST /feed/discover`
   - `POST /feed/search`
3. Support deterministic ranking keys:
   - `trending_score`, `engagement_rate`, `views_per_hour`, base metric keys.
4. Support mode-aware filtering:
   - `profile`, `hashtag`, `keyword`, `audio`.
5. Add timeframe filtering + deterministic pagination.
6. Add integration tests for:
   - ranking behavior
   - mode/timeframe filtering
   - pagination stability.

## Phase 1 Implementation (completed)

### Files added
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/tests/test_feed_discovery.py`

### Files updated
- `apps/api/main.py` (mounted `/feed` router)
- `apps/api/routers/__init__.py` (router import)

### Runtime behavior shipped
- `POST /feed/discover`
  - returns: `run_id`, `ingestion_method`, `source_health`, paginated `items`.
- `POST /feed/search`
  - returns paginated feed results with derived ranking metrics.
- Item payload includes:
  - `engagement_rate`
  - `views_per_hour`
  - `trending_score`.

### Errors found/fixed during development
- Fixed timezone-naive vs timezone-aware datetime arithmetic in ranking/timeframe logic in `apps/api/services/feed_discovery.py`.

## Phase 2 Plan (locked)

1. Add feed favorite toggle endpoint that persists in canonical `research_items.media_meta_json`.
2. Add bulk collection assignment endpoint for feed items.
3. Add feed export endpoint with signed download URLs.
4. Add download endpoint that validates signed token purpose + export ownership.
5. Add integration tests covering all new endpoints including token mismatch behavior.

## Phase 2 Implementation (completed)

### Files updated
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/tests/test_feed_discovery.py`
- `apps/web/src/lib/api.ts`

### Runtime behavior shipped
- `POST /feed/favorites/toggle`
  - request: `{ item_id, favorite, user_id? }`
  - response: `{ item_id, favorite }`
- `POST /feed/collections/assign`
  - request: `{ item_ids[], collection_id, user_id? }`
  - response: `{ collection_id, assigned_count, missing_count, missing_item_ids[] }`
- `POST /feed/export`
  - supports direct `item_ids[]` or search-parameter export.
  - returns signed download URL and completed export metadata.
- `GET /feed/export/{export_id}/download?token=...`
  - validates signed token (`purpose=feed_export`, matching `export_id`) before serving file.

### Errors found/fixed during development
- Web checks can fail when `next build`, `tsc --noEmit`, and smoke run in parallel due `.next/types` and build artifact races; sequential execution is stable and now used in verification.

## Validation Evidence

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py tests/test_research_optimizer_outcomes.py` -> `10 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `58 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass
- `cd apps/web && npx playwright test tests/smoke.spec.ts --reporter=list` -> `6 passed`

Note: `tsc --noEmit` can fail transiently if run in parallel with `next build` due `.next/types` generation timing. Sequential runs pass.

### Phase 2 validation additions

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py` -> `6 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `61 passed`
- `cd apps/web && npm run smoke` -> `6 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass

## Phase 3 Plan (locked)

1. Add feed bulk media download endpoint to queue per-item jobs from feed items.
2. Add feed bulk media job status endpoint for polling from feed workspace.
3. Add feed transcript job model + worker entrypoint.
4. Add feed bulk transcript endpoint and transcript status polling endpoint.
5. Persist download/transcript linkage metadata on `research_items.media_meta_json`.
6. Add integration tests covering queueing, status polling, and transcript completion fallback.

## Phase 3 Implementation (completed)

### Files added
- `apps/api/models/feed_transcript_job.py`
- `apps/api/services/feed_transcript.py`

### Files updated
- `apps/api/models/__init__.py`
- `apps/api/services/audit_queue.py`
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/main.py`
- `apps/api/tests/test_feed_discovery.py`
- `apps/web/src/lib/api.ts`

### Runtime behavior shipped
- `POST /feed/download/bulk`
  - queues media download jobs for feed items with valid source URLs.
  - response includes per-item queue/skip/failure outcomes.
- `POST /feed/download/status`
  - bulk polling endpoint for media download jobs.
- `POST /feed/transcripts/bulk`
  - queues transcript extraction jobs per feed item.
- `POST /feed/transcripts/status`
  - bulk polling endpoint for transcript jobs with transcript preview/source.
- Worker support:
  - added `enqueue_feed_transcript_job(...)` and stalled transcript recovery.

### Errors found/fixed during development
- Added deterministic caption/title fallback in transcript processor so transcript jobs do not fail when no downloaded media/audio pipeline is available.

### Phase 3 validation additions

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py` -> `8 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `63 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass
- `cd apps/web && npm run smoke` -> `6 passed`

## Phase 4 Plan (locked)

1. Add feed follow persistence model for saved source queries with cadence and next run.
2. Add follow CRUD endpoints (`upsert`, `list`, `delete`) in feed router.
3. Add ingest run model to track each manual/scheduled run.
4. Add manual ingest endpoints:
   - `POST /feed/follows/ingest`
   - `GET /feed/follows/runs`
5. Add scheduled auto-ingest loop that executes due follows periodically.
6. Add integration tests for follow lifecycle + due-only ingest + run history.

## Phase 4 Implementation (completed)

### Files added
- `apps/api/models/feed_source_follow.py`
- `apps/api/models/feed_auto_ingest_run.py`

### Files updated
- `apps/api/models/__init__.py`
- `apps/api/config.py`
- `apps/api/.env.example`
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/main.py`
- `apps/api/tests/test_feed_discovery.py`
- `apps/web/src/lib/api.ts`

### Runtime behavior shipped
- `POST /feed/follows/upsert`
  - upserts follow by `(platform, mode, query)` for the authenticated user.
- `GET /feed/follows`
  - lists saved follows with optional platform + active filtering.
- `DELETE /feed/follows/{follow_id}`
  - deletes a saved follow.
- `POST /feed/follows/ingest`
  - runs follow ingestion on-demand, with optional `run_due_only`.
- `GET /feed/follows/runs`
  - returns run history for a user (optional `follow_id` filter).
- Periodic scheduler:
  - `FEED_AUTO_INGEST_ENABLED` + `FEED_AUTO_INGEST_INTERVAL_MINUTES` added.
  - startup loop now executes due follow ingests automatically.

### Errors found/fixed during development
- Reconfirmed/handled build-typecheck race: `build`, `tsc`, and smoke in parallel produce transient `.next` type failures. Sequential validation remains stable and is used as the required check pattern.

### Phase 4 validation additions

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py` -> `10 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `65 passed`
- `cd apps/web && npm run smoke` -> `6 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass

## Phase 5 Plan (locked)

1. Add repost package persistence model keyed by source feed item.
2. Add deterministic repost package generator (hooks, platform captions, CTA, edit directives, checklist).
3. Add repost package APIs:
   - `POST /feed/repost/package`
   - `GET /feed/repost/packages`
   - `GET /feed/repost/packages/{package_id}`
   - `POST /feed/repost/packages/{package_id}/status`
4. Add frontend API contract methods for repost package workflow.
5. Add integration tests for create/list/get/status and validation failures.

## Phase 5 Implementation (completed)

### Files added
- `apps/api/models/feed_repost_package.py`

### Files updated
- `apps/api/models/__init__.py`
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/tests/test_feed_discovery.py`
- `apps/web/src/lib/api.ts`

### Runtime behavior shipped
- `POST /feed/repost/package`
  - generates and saves a repost package from a feed source item.
  - package includes hook variants, platform-specific captions/hashtags/CTA, edit directives, and execution checklist.
- `GET /feed/repost/packages`
  - lists saved repost packages (optional `source_item_id` filter).
- `GET /feed/repost/packages/{package_id}`
  - retrieves one repost package.
- `POST /feed/repost/packages/{package_id}/status`
  - updates package status (`draft|scheduled|published|archived`).

### Errors found/fixed during development
- Reconfirmed the local CI race where `next build` and `tsc` overlap can produce transient `.next/types` missing-file errors. Validation remains stable when checks are run one at a time.

### Phase 5 validation additions

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py` -> `12 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `67 passed`
- `cd apps/web && npm run smoke` -> `6 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass

## Phase 6 Plan (locked)

1. Add feed loop endpoint to generate optimizer variants directly from a source feed item.
2. Add feed loop endpoint to run audits directly from completed feed downloads for that source item.
3. Add feed loop summary endpoint that reports latest repost package, latest draft snapshot, and latest audit/report state.
4. Add frontend API contract methods for these loop endpoints.
5. Add integration tests for loop variant generation, loop audit launch, and summary stage progression.

## Phase 6 Implementation (completed)

### Files updated
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/tests/test_feed_discovery.py`
- `apps/web/src/lib/api.ts`

### Runtime behavior shipped
- `POST /feed/loop/variant_generate`
  - infers topic/audience/objective from source item when omitted.
  - runs optimizer variant generation with source context and returns credit charge metadata.
- `POST /feed/loop/audit`
  - resolves source item -> completed feed download -> upload and enqueues audit.
  - stores linkage in audit input (`source_item_id`, download/upload linkage, optional snapshot/package references).
- `GET /feed/loop/summary`
  - returns source item context + latest repost package + latest draft snapshot + latest audit and stage completion map.

### Errors found/fixed during development
- Fixed test hygiene issue in the new loop-audit integration test (removed unnecessary query stubs and used explicit model queries), keeping test logic deterministic.

### Phase 6 validation additions

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py` -> `15 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `70 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass
- `cd apps/web && npm run smoke` -> `6 passed`

## Phase 7 Plan (locked)

1. Add persistent feed telemetry event model for discovery-to-report funnel events.
2. Instrument feed discovery/workflow endpoints with structured event logging and contextual evidence.
3. Add telemetry summary endpoint with funnel conversion rates and error counts.
4. Add telemetry events listing endpoint with deterministic filtering/pagination controls.
5. Add frontend API contract methods for telemetry summary/events.
6. Add integration tests validating funnel counters and event persistence from loop flows.

## Phase 7 Implementation (completed)

### Files added
- `apps/api/models/feed_telemetry_event.py`

### Files updated
- `apps/api/models/__init__.py`
- `apps/api/services/feed_discovery.py`
- `apps/api/routers/feed.py`
- `apps/api/tests/test_feed_discovery.py`
- `apps/web/src/lib/api.ts`

### Runtime behavior shipped
- `GET /feed/telemetry/summary`
  - returns event volume by type/status, error counts, and funnel conversion metrics:
    - `discovered_count`
    - `packaged_count`
    - `scripted_count`
    - `audited_count`
    - `reported_count`
    - conversion percentages across each funnel stage.
- `GET /feed/telemetry/events`
  - returns recent telemetry events with optional `event_name` and `status` filters.
- Feed workflows now emit structured telemetry events for:
  - discover/search
  - favorites/collections/export
  - download/transcript start and status polling
  - follows upsert/delete/ingest
  - repost package lifecycle
  - loop variant/audit/summary actions.

### Errors found/fixed during development
- Fixed telemetry durability bug where some events were flushed but not committed in read-style post-processing paths; added explicit commits so events persist reliably for summary and list queries.
- Reconfirmed the local web artifact race for parallel `next build` + `tsc`; required checks remain sequential for stable CI/local execution.

### Phase 7 validation additions

- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_feed_discovery.py` -> `16 passed`
- `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `71 passed`
- `cd apps/web && npm run build` -> pass
- `cd apps/web && npx tsc --noEmit` -> pass
- `cd apps/web && npm run smoke` -> `6 passed`
