# Video Processing and Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show active video work in a compact panel and remove redundant preview and workspace-read work.

**Architecture:** PostgreSQL remains the source of processing state. A read-only API maps video and thumbnail rows to a small public contract; the web app polls it while visible. Fragment cards use the existing per-video thumbnail bundle. Workspace snapshots load related rows in batches.

**Tech Stack:** TypeScript, Fastify, Kysely, PostgreSQL, Svelte 5, Vitest.

**Spec:** `cut_on_eight/docs/superpowers/specs/2026-09-23-video-processing-and-optimization-design.md`

**Rollout decision:** New fragment preview jobs stop in this change. Existing
preview readers and workers stay for old data and queued jobs; their removal
is a follow-up after real-media review.

## Global Constraints

- Keep all changes inside `cut_on_eight`.
- Keep search behavior and UI unchanged.
- Do not add multi-user state, raw job payloads, progress percentages, or queue controls.
- Use the existing video thumbnail bundle and current catalog tables.
- Keep the editor clear when the processing panel is closed.

## Review Focus

- A video with no thumbnail-state row shows a waiting state, not false success (Task 3).
- A deleted video does not remain in the processing response (Task 3).
- Raw worker errors and storage paths never reach the browser (Task 3).
- A fragment shorter than five frame intervals still shows useful available samples (Task 1).
- A failed refresh leaves prior items visible and marks them stale (Task 4).

---

### Task 1: Reuse video thumbnails for fragment cards

**Files:** Add `apps/web/src/domain/video-fragment-previews.ts`; modify `apps/web/src/lib/api.ts`, `apps/web/src/app/search-model.svelte.ts`, `apps/web/src/components/SearchView.svelte`, and `apps/server/src/fragments/fragment-service.ts`. Keep the old worker and reader for existing data during this rollout. Test selection, fragment loading, search loading, and no new preview enqueue.

**Interfaces:** Consume `VideoThumbnailManifestDto` and `/api/videos/:id/thumbnails` with samples shaped as `[seconds, pageIndex, x, y, width, height]`. Produce `framesForFragment(manifest, startSeconds, endSeconds, count): FragmentPreview[]`; use the current `FragmentPreviewStrip` display data shape.

- [ ] **Step 1: Add selection tests.** Cover a normal range, a short range, a range near video end, and no manifest. For a normal range, five selected frame times must be inside `[startSeconds, endSeconds]`; for a short range, reuse the nearest available samples without duplicate frame keys.
- [ ] **Step 2: Run the focused test and confirm failure.** Use `pnpm -C cut_on_eight/apps/web exec vitest run src/domain/video-fragment-previews.test.ts`.
- [ ] **Step 3: Add a pure frame selector.** Filter samples in the range, choose up to five evenly distributed indices, and map page data to the existing crop shape. When no sample is in the range, choose the nearest sample to the range midpoint. Return `[]` for a missing manifest.
- [ ] **Step 4: Wire fragment cards to the video manifest.** Load each video's bundle once, pass its selected samples to each card, and retain the placeholder when unavailable. Do not trigger a new job per fragment.
- [ ] **Step 5: Stop new per-fragment generation.** Remove the enqueue calls. Retain the old worker and asset reader during this rollout, then remove them with a separate compatibility migration after real-media review.
- [ ] **Step 6: Verify and commit.** Run focused web/server tests and `git diff --check`; commit only Task 1 files.

### Task 2: Batch workspace reads

**Files:** Modify `apps/server/src/workspace/workspace-service.ts`, `apps/server/src/fragments/fragment-repository.ts`, `apps/server/src/videos/video-repository.ts`. Test with `apps/server/test/video-workspace-api.test.ts` or a focused database integration test.

**Interfaces:** Add `tagsByVideoIds(ids): Promise<Map<string, TagRecord[]>>`, `tagsByFragmentIds(ids): Promise<Map<string, TagRecord[]>>`, and `previewsByFragmentIds(ids): Promise<Map<string, PreviewRecord>>` if preview records remain during Task 1. Keep `WorkspaceService.snapshot(): Promise<WorkspaceDto>` unchanged.

- [ ] **Step 1: Add a database test with two videos and several fragments.** Assert identical workspace JSON before and after batching. Instrument Kysely query count and assert the number of tag/preview queries does not grow per fragment.
- [ ] **Step 2: Run the integration suite with the repository test database.** Use `./scripts/integration.sh` from the repository root.
- [ ] **Step 3: Add set-based repository reads.** Use `where('video_id', 'in', ids)` and `where('fragment_id', 'in', ids)` with an empty-ID early return. Group rows by ID in maps; retain deterministic tag order.
- [ ] **Step 4: Replace per-item awaits in `WorkspaceService.snapshot()`.** Fetch all needed IDs, then construct DTOs from maps. Keep the public result and ordering unchanged.
- [ ] **Step 5: Verify and commit.** Run focused integration tests and `git diff --check`; commit only Task 2 files.

### Task 3: Add the processing read API

**Files:** Create `packages/api-contracts/src/processing.ts`, `apps/server/src/processing/processing-service.ts`, `apps/server/src/api/processing-routes.ts`, and tests. Modify contract exports and `apps/server/src/app.ts`.

**Interfaces:** Export `processingSnapshotSchema` and `ProcessingSnapshotDto` from API contracts. Add `ProcessingService.snapshot(): Promise<ProcessingSnapshotDto>`. Register `GET /api/processing` only for the current PostgreSQL runtime.

- [ ] **Step 1: Define the public contract and tests.** Model `task` as `import | inspect | thumbnails`, `state` as `queued | running | failed`, IDs/titles/timestamps, safe failure code, `activeCount`, `failedCount`, `items`, and `observedAt`.
- [ ] **Step 2: Add mapping/integration tests.** Seed receiving, queued, processing, ready-without-thumbnail-row, generating, ready, failed, and deleted videos. Assert count, order, bounded results, and no raw error or path fields.
- [ ] **Step 3: Run focused tests and confirm failure.** Use `pnpm -C cut_on_eight/apps/server exec vitest run test/processing-service.test.ts`; run `./scripts/integration.sh` for the route.
- [ ] **Step 4: Implement the read model.** Select video and left-joined thumbnail rows with Kysely; compute counts before applying the display bound. Map video state first, then thumbnail state for ready videos. Use only known failure codes in the DTO.
- [ ] **Step 5: Register the route and verify.** Parse the response through `processingSnapshotSchema`, run contract and API tests, and commit Task 3 files.

### Task 4: Add compact processing panel

**Files:** Create `apps/web/src/app/processing-model.svelte.ts` and `apps/web/src/components/ProcessingPanel.svelte`; modify `apps/web/src/lib/api.ts`, `apps/web/src/app/app-model.svelte.ts`, `apps/web/src/components/AppBar.svelte`, `apps/web/src/components/EditorShell.svelte`, and `apps/web/src/App.svelte`. Add model/component tests.

**Interfaces:** Add `loadProcessing(): Promise<ProcessingSnapshotDto>` in API client. `ProcessingModel` owns `snapshot`, `stale`, `expanded`, `start()`, `dispose()`, and `toggle()`. The panel receives the model and an `onOpenVideo(id)` callback.

- [ ] **Step 1: Test model refresh.** Fake the API and timers. Assert active count, a refresh while visible, no refresh while hidden, stale data after failure, and timer cleanup on dispose.
- [ ] **Step 2: Test UI behavior.** Assert a compact count when closed; when open, list video title, task, state, and safe failure label. Clicking a row opens its video and only then changes the active view.
- [ ] **Step 3: Run focused tests and confirm failure.** Use `pnpm -C cut_on_eight/apps/web exec vitest run src/app/processing-model.test.ts`.
- [ ] **Step 4: Implement model and panel.** Poll at a modest interval while `document.visibilityState === 'visible'`; keep the last snapshot on error and show a small stale marker. Use a button with `aria-expanded` and a side panel that does not obscure editor controls when closed.
- [ ] **Step 5: Wire navigation and verify.** Use `WorkspaceSession.reopenProject(id)` on click. Run the Svelte autofixer for changed Svelte files, focused web tests, and `git diff --check`; commit Task 4 files.

### Task 5: Whole-feature verification

**Files:** Update `docs/cleanup-report.md` to mark delivered work and leave event-payload shrink as a follow-up.

- [ ] **Step 1: Run `./scripts/check.sh` and `./scripts/test.sh` from repository root.** Fix failures caused by this work.
- [ ] **Step 2: Run `./scripts/integration.sh` when Docker is available.** Record skipped checks if Docker is unavailable.
- [ ] **Step 3: Review the full diff for search behavior, storage paths, and unrelated files.** Do not stage the root `.DS_Store`.
- [ ] **Step 4: Commit the report update and give the user a concise handoff with verification results.**
