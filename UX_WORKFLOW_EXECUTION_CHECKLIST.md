# UX Workflow Hardening Checklist

## Goal
Reduce user confusion in the core loop by making next actions explicit, platform defaults intelligent, and prerequisite gaps visible.

## Progress
- [x] Phase 1: Shared app shell + global stepper foundation.
- [x] Phase 2: Core workflow simplification and advanced-tool collapsing.
- [x] Phase 3: Connect/Competitors hierarchy and platform-aware empty states.
- [x] Phase 4: Workflow assistant + platform-aware defaults across Research/Audit/Report.
- [x] Phase 5: E2E UX polish pass and copy tuning.
- [x] Phase 6: Cross-page continuity and draft-to-audit acceleration.

## Phase 3 Validation (completed)
- API: `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests/test_ux_flow_state.py tests/test_parity_hardening.py` -> `9 passed`
- Web typecheck: `cd apps/web && npx tsc --noEmit` -> pass
- Web smoke: `cd apps/web && npm run smoke` -> `6 passed`
- Web build: `cd apps/web && npm run build` -> pass

## Phase 4 Plan (locked)
1. Add reusable `WorkflowAssistant` component backed by `/ux/flow_state`:
   - next best action CTA
   - completion + preferred platform context
   - direct links for missing prerequisites
2. Wire assistant into:
   - `/research`
   - `/audit/new`
   - `/report/[id]`
3. Apply flow-state platform defaults:
   - research script/import/search defaults align to preferred platform when no explicit source context exists
   - audit platform default aligns to preferred platform when no explicit source context exists
4. Validate sequentially:
   - `npx tsc --noEmit`
   - `npm run smoke`
   - `npm run build`
   - `PYTHONPATH=. venv/bin/pytest -q tests analysis/tests`

## Phase 4 Implementation (completed)
- Added reusable workflow guidance component:
  - `apps/web/src/components/workflow-assistant.tsx`
  - shows next action, completion, preferred platform, and missing prerequisite links.
- Wired assistant into:
  - `apps/web/src/app/research/page.tsx`
  - `apps/web/src/app/audit/new/page.tsx`
  - `apps/web/src/app/report/[id]/page.tsx`
- Added platform-aware defaults using flow state:
  - Research defaults `scriptPlatform`, `importPlatform`, and `searchPlatform` to preferred platform once when no explicit seed context is present.
  - Audit defaults `selectedPlatform` to preferred platform once when no explicit URL/source/upload context is present.

## Phase 4 Validation (completed)
- Web typecheck: `cd apps/web && npx tsc --noEmit` -> pass
- Web smoke: `cd apps/web && npm run smoke` -> `6 passed`
- Web build: `cd apps/web && npm run build` -> pass
- API regression: `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `73 passed`

## Phase 5 Plan (locked)
1. Research Script Optimizer copy + quick-start improvements:
   - add one-click topic presets per platform
   - disable variant generation when topic is empty with explicit guidance text
2. Audit run reliability UX:
   - add explicit run-readiness state block
   - disable run button until source is ready and show clear reason
3. Report outcomes UX:
   - improve platform mismatch controls with one-click "use report platform"
   - make submit button state explicit when mismatch blocks save
4. Validate sequentially:
   - `cd apps/web && npx tsc --noEmit`
   - `cd apps/web && npm run smoke`
   - `cd apps/web && npm run build`
   - `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests`

## Phase 5 Implementation (completed)
- Research script-optimizer UX polish in `apps/web/src/app/research/page.tsx`:
  - added platform-specific one-click topic presets
  - added quick-start instructional copy
  - disabled variant generation until topic is provided with explicit hint
- Audit run UX polish in `apps/web/src/app/audit/new/page.tsx`:
  - added run-readiness status card (source/platform/metrics guidance)
  - disabled run button until source is ready with explicit reason copy
- Report outcomes UX polish in `apps/web/src/app/report/[id]/page.tsx`:
  - improved platform mismatch handling with one-click "Use report platform"
  - explicit submit-button state when mismatch blocks save

## Phase 5 Validation (completed)
- Web typecheck: `cd apps/web && npx tsc --noEmit` -> pass
- Web smoke: `cd apps/web && npm run smoke` -> `6 passed`
- Web build: `cd apps/web && npm run build` -> pass
- API regression: `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `73 passed`

## Phase 6 Plan (locked)
1. Research continuity acceleration:
   - add one-click `Apply Top AI Edits` from line-level suggestions
   - add `Reset to Selected Variant` to undo local edit experiments
   - add direct handoff link to `/audit/new` with platform/source context params
2. Audit deep-link continuity:
   - support query param prefills (`platform`, `source_mode`, `source_context`)
   - surface entry-context hint in the workspace so users know why values are prefilled
3. Report continuity fallback:
   - ensure "Generate Improved A/B/C" is available even when `best_edited_variant` is absent
   - include report platform in script-studio deep links for correct defaults
4. Validation:
   - `cd apps/web && npx tsc --noEmit`
   - `cd apps/web && npm run smoke`
   - `cd apps/web && npm run build`
   - `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests`

## Phase 6 Implementation (completed)
- Research Script Studio continuity (`apps/web/src/app/research/page.tsx`):
  - added `Apply Top AI Edits` action from `line_level_edits`
  - added `Reset to Selected Variant` action for quick rollback
  - added direct `Run Audit From Script Studio` handoff link with platform/source context query params
  - added `platform` query prefill support for script/import/search defaults
- Audit continuity (`apps/web/src/app/audit/new/page.tsx`):
  - added deep-link param support for `platform`, `source_mode`, and `source_context`
  - added entry-context hint text when launched from another workspace
- Report continuity fallback (`apps/web/src/app/report/[id]/page.tsx`):
  - made script-studio refine links include report platform
  - added fallback “Refine in Script Studio” section when `best_edited_variant` is absent
- Smoke coverage update (`apps/web/tests/smoke.spec.ts`):
  - validates new edit actions (`Apply Top AI Edits`, `Reset to Selected Variant`) in research flow
  - regression fixed by re-running re-score before saving after reset

## Phase 6 Validation (completed)
- Web typecheck: `cd apps/web && npx tsc --noEmit` -> pass
- Web smoke: `cd apps/web && npm run smoke` -> `6 passed`
- Web build: `cd apps/web && npm run build` -> pass
- API regression: `cd apps/api && PYTHONPATH=. venv/bin/pytest -q tests analysis/tests` -> `73 passed`
