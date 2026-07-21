# Phase 2 Precision Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a content-first precision editor with selection-scoped playback, keyboard/click boundary refinement, a zoomable two-row timeline, and durable compact thumbnail sprites.

**Architecture:** Plain TypeScript modules own geometry, constraints, playback decisions, and thumbnail formats. Svelte components compose those modules while the Fastify backend extends the existing durable queue with FFmpeg thumbnail generation and atomic sprite-set promotion. Phase 2 migrates project documents without changing existing segment timestamps.

**Tech Stack:** TypeScript 5.9, Svelte 5 runes, Vite 8, Fastify 5, Zod 4, Vitest 4, FFprobe, FFmpeg, WebP sprite pages, Canvas 2D.

## Global Constraints

- Keep all changes inside `projectslatte/cut_on_eight`; preserve every `AGENTS.md` file exactly.
- Keep the web app a client-only Svelte 5 SPA; do not add SvelteKit, SSR, Electron, or an installable package.
- Keep filesystem and process access in the backend bound to `127.0.0.1`.
- Keep algorithms in focused plain TypeScript modules and Svelte components in runes mode.
- Selecting a segment changes scope and seeks to its start but never starts playback.
- `Space` or native Play loops the selected range; clicking video or empty timeline returns to full-video scope.
- Permit at most two simultaneous segments; reject a third overlap without mutating persisted state.
- Frame nudging uses reported reliable FPS or `1 / 30` seconds with a visible approximate warning.
- Generate bounded WebP sprite pages and one versioned compact JSON manifest; sampled frame files are staging-only.
- Persist mutable sidecars and job records separately with the existing atomic-write behavior.
- Run focused tests per task; run the complete checks, builds, and browser smoke only in Task 8.

---

## File Map

| Area | Responsibility |
| --- | --- |
| `packages/contracts/src/project.ts` | Versioned project migration, source frame-rate signal, per-project timeline viewport |
| `packages/contracts/src/jobs.ts` | Inspection and thumbnail job variants |
| `packages/contracts/src/thumbnails.ts` | Compact sprite manifest and API response schemas |
| `apps/web/src/lib/segment-constraints.ts` | Range bounds, maximum overlap depth, duration guidance |
| `apps/web/src/lib/two-row-layout.ts` | Deterministic chronological row assignment |
| `apps/web/src/lib/timeline-geometry.ts` | Timestamp/pixel conversion and viewport clamping |
| `apps/web/src/lib/timeline-viewport.ts` | Pointer/playhead anchored zoom and ensure-visible commands |
| `apps/web/src/lib/trim-controller.ts` | Boundary focus and frame/time nudge commands |
| `apps/web/src/lib/playback-controller.ts` | Full-source, selected-loop, and contextual-preview decisions |
| `apps/web/src/lib/thumbnail-renderer.ts` | Visible-cell Canvas sprite drawing |
| `apps/web/src/components/EditorShell.svelte` | Editor/Library navigation, compact status, help, panel preference |
| `apps/web/src/components/PrecisionTimeline.svelte` | Timeline interaction and layered rendering |
| `apps/web/src/components/BoundaryEditor.svelte` | Start/End focus and click controls |
| `apps/server/src/jobs/ffmpeg-runner.ts` | Bounded, shell-free FFmpeg process adapter |
| `apps/server/src/thumbnails/thumbnail-manifest.ts` | Sampling plan, manifest compatibility, sprite coordinates |
| `apps/server/src/thumbnails/thumbnail-worker.ts` | Staging, sprite generation, validation, atomic promotion |
| `apps/server/src/http/thumbnail-routes.ts` | Manifest and sprite byte responses inside the managed root |

---

### Task 1: Precision domain and project migration

**Files:**

- Modify: `packages/contracts/src/project.ts`
- Modify: `packages/contracts/src/index.ts`
- Modify: `packages/contracts/test/project.test.ts`
- Modify: `apps/server/src/imports/import-service.ts`
- Modify: `apps/server/src/jobs/ffprobe-runner.ts`
- Modify: `apps/server/src/services.ts`
- Modify: `apps/server/src/storage/project-repository.ts`
- Modify: `apps/server/test/ffprobe-runner.test.ts`
- Modify: `apps/server/test/storage.test.ts`
- Create: `apps/web/src/lib/segment-constraints.ts`
- Create: `apps/web/src/lib/segment-constraints.test.ts`
- Create: `apps/web/src/lib/two-row-layout.ts`
- Create: `apps/web/src/lib/two-row-layout.test.ts`
- Modify: `apps/web/src/lib/segments.ts`
- Modify: `apps/web/src/lib/segments.test.ts`
- Modify: `apps/web/src/components/VideoEditor.svelte`

**Interfaces:**

- Produces `ProjectDocument` schema version 2 with `source.frameRateNumerator`, `source.frameRateDenominator`, `source.frameRateReliability`, `source.inspectedAt`, `source.inspectorVersion`, and `editor.timelineZoom` / `editor.timelineOffsetSeconds`.
- Produces `migrateProjectDocument(value: unknown): ProjectDocument`; version 1 maps the existing `frameRate` fraction into version 2 and preserves segment timestamps.
- Produces `validateSegmentMutation(segments, candidate, durationSeconds, ignoredId?) => { ok: true; segment } | { ok: false; code: 'invalid_range' | 'outside_source' | 'triple_overlap'; message }`.
- Produces `assignSegmentRows(segments) => { ok: true; rows: Array<{ segment; row: 0 | 1 }> } | { ok: false; code: 'triple_overlap'; message: string }`.
- Produces `frameStepSeconds(source)`, returning the reliable fraction or `1 / 30` with `approximate: true`.
- Produces `createSegment<T extends SegmentState>(state: T, startSeconds: number | null, endSeconds: number, durationSeconds: number, createId?: () => string): { ok: true; state: UpdatedSegmentState<T> } | { ok: false; state: T; code: SegmentConstraintCode; message: string }` so failed rough marking can explain a constraint without changing state.

- [x] **Step 1: Add failing contract and migration cases**

  Cover version-1-to-version-2 migration, unchanged segment timestamps, rational FPS parsing, absent/unreliable FPS fallback, and per-project viewport defaults `{ timelineZoom: 1, timelineOffsetSeconds: 0 }`. Assert that the persisted schema accepts only version 2 after migration.

- [x] **Step 2: Run the contract test and confirm the schema is missing**

  Run: `node_modules/.bin/vitest run packages/contracts/test/project.test.ts`

  Expected: failure on `schemaVersion: 2`, `editor`, or `migrateProjectDocument`.

- [x] **Step 3: Implement the versioned migration boundary**

  Use these public shapes:

  ```ts
  export type FrameRateReliability = 'reliable' | 'approximate';

  export interface FrameStep {
    readonly approximate: boolean;
    readonly seconds: number;
  }

  export function migrateProjectDocument(value: unknown): ProjectDocument;
  export function frameStepSeconds(
    source: ProjectDocument['source'],
  ): FrameStep;
  ```

  Project repositories must parse reads through `migrateProjectDocument` and atomically write migrated version 2 data during the next ordinary save. Inspection compares normalized `avg_frame_rate` and `r_frame_rate`: equal valid fractions are reliable; a missing or differing signal is approximate. Inspection updates all new inspection fields together so client saves cannot replace fresher backend metadata. Legacy `frameRate` migrates conservatively as approximate.

- [x] **Step 4: Add failing constraint and row-allocation cases**

  Cover source bounds, `start < end`, two simultaneous overlaps accepted, three rejected, a segment overlapping its previous and next neighbours at different times accepted, deterministic rows independent of input order, and duration status `short | expected | long` at the 3/8-second boundaries.

- [x] **Step 5: Implement shared segment constraints and use them for creation**

  ```ts
  export type SegmentConstraintCode =
    | 'invalid_range'
    | 'outside_source'
    | 'triple_overlap';

  export type SegmentMutationResult =
    | { readonly ok: true; readonly segment: Segment }
    | {
        readonly ok: false;
        readonly code: SegmentConstraintCode;
        readonly message: string;
      };

  export function validateSegmentMutation(
    segments: readonly Segment[],
    candidate: Segment,
    durationSeconds: number,
    ignoredId?: string,
  ): SegmentMutationResult;
  ```

  Calculate overlap depth from sorted start/end events with end events processed before start events at equal timestamps. `createSegment` returns a discriminated result containing the original state and stable error when validation fails; `VideoEditor` surfaces that error without saving.

- [x] **Step 6: Run the focused domain tests**

  Run: `node_modules/.bin/vitest run packages/contracts/test/project.test.ts apps/web/src/lib/segments.test.ts apps/web/src/lib/segment-constraints.test.ts apps/web/src/lib/two-row-layout.test.ts apps/server/test/ffprobe-runner.test.ts apps/server/test/storage.test.ts`

  Then run: `apps/web/node_modules/.bin/svelte-check --tsconfig apps/web/tsconfig.json --fail-on-warnings`

  Expected: all listed tests and the local Svelte check pass.

- [x] **Step 7: Commit**

  ```bash
  git add packages/contracts apps/server/src/imports/import-service.ts apps/server/src/jobs/ffprobe-runner.ts apps/server/src/services.ts apps/server/src/storage/project-repository.ts apps/server/test/ffprobe-runner.test.ts apps/server/test/storage.test.ts apps/web/src/lib apps/web/src/components/VideoEditor.svelte
  git commit -m "feat: add precision editing domain rules"
  ```

---

### Task 2: Content-first editor shell

**Files:**

- Create: `apps/web/src/components/EditorShell.svelte`
- Create: `apps/web/src/components/ContextHelp.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/components/AppBar.svelte`
- Modify: `apps/web/src/components/LibraryPanel.svelte`
- Modify: `apps/web/src/components/SegmentList.svelte`
- Modify: `apps/web/src/components/VideoEditor.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- Consumes the existing workspace, job, save, import/open/close callbacks from `App.svelte`.
- Produces `EditorMode = 'video' | 'segment' | 'boundary'` for contextual help.
- Browser keys: `cut-on-eight.active-view` (`editor | library`) and `cut-on-eight.segment-panel-collapsed` (`true | false`).

- [x] **Step 1: Implement the standalone navigation shell**

  `EditorShell.svelte` accepts `activeView`, `onViewChange`, compact status content, help mode/content, and editor/library snippets. It renders only Editor, Library, status, and `?` in the top navigation. Import or reopen calls switch to Editor after the workspace update; a direct Library click stays on Library.

- [x] **Step 2: Make the workspace content-first**

  Give video the flexible central area, timeline a fixed compact band, and segments a collapsible lower/side panel. Remove permanent instructional copy and keep actionable empty/error states. Collapsing segments must preserve selection and playback.

- [x] **Step 3: Add central contextual help**

  The closed-by-default popover shows exact key rows for full-video seek/play, selected-segment loop/navigation, or focused-boundary nudging. `Escape` closes the popover before editor selection handling. Focus returns to `?` when closed.

- [x] **Step 4: Persist only view and collapsed preference**

  Parse local-storage values defensively; default to Editor when a project is active and Library otherwise. Never persist whether help/status popovers are open.

- [x] **Step 5: Run Svelte validation**

  Run the repository Svelte autofixer once for each changed `.svelte` file with target Svelte 5, then run `apps/web/node_modules/.bin/svelte-check --tsconfig apps/web/tsconfig.json --fail-on-warnings`.

  Expected: no local Svelte diagnostics. If the autofixer cannot reach its remote service, record that once and rely on `svelte-check` rather than retrying.

- [x] **Step 6: Commit**

  ```bash
  git add apps/web/src/App.svelte apps/web/src/app.css apps/web/src/components
  git commit -m "feat: focus the workspace on editing content"
  ```

---

### Task 3: Playback scopes, seeking, and precise boundary controls

**Files:**

- Create: `apps/web/src/lib/playback-controller.ts`
- Create: `apps/web/src/lib/playback-controller.test.ts`
- Create: `apps/web/src/lib/trim-controller.ts`
- Create: `apps/web/src/lib/trim-controller.test.ts`
- Create: `apps/web/src/components/BoundaryEditor.svelte`
- Modify: `apps/web/src/components/VideoEditor.svelte`
- Modify: `apps/web/src/components/SegmentList.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- Produces `PlaybackScope = { kind: 'source'; start: 0; end } | { kind: 'segment'; segmentId; start; end }`.
- Produces pure commands `selectSegment`, `clearSelection`, `seekBy`, `beginContextPreview`, and `onPlaybackTime` returning seek/play/pause decisions without owning the media element.
- Produces `BoundaryFocus = { segmentId: string; edge: 'start' | 'end' } | null` and `nudgeBoundary(project, focus, deltaSeconds)` returning either an updated project or a stable constraint error.

- [x] **Step 1: Write failing playback-controller tests**

  Cover selection seeking without autoplay, one/ten-second scope-clamped seeks, exact end-to-start loop, selection change while playing pausing, clearing selection, context preview clamped at both source ends, preview completion returning to paused segment scope, and failed seek producing a visible error decision.

- [x] **Step 2: Implement pure playback decisions**

  ```ts
  export type PlaybackCommand =
    | { readonly kind: 'none' }
    | { readonly kind: 'pause-and-seek'; readonly seconds: number }
    | { readonly kind: 'seek-and-play'; readonly seconds: number }
    | { readonly kind: 'pause'; readonly error?: string };
  ```

  `VideoEditor.svelte` remains the media adapter: it applies commands to the `<video>`, samples time with `requestAnimationFrame`, and updates only the playhead element/state needed for current time.

- [x] **Step 3: Write failing trim-controller tests**

  Cover Start and End focus, reliable frame step, approximate `1 / 30`, Shift 0.1-second step, source/range clamp, triple-overlap rejection with no project mutation, Escape focus-then-selection order, and previous/next chronological selection.

- [x] **Step 4: Implement trim commands and BoundaryEditor**

  Show Start/End timestamps and compact `−frame`, `+frame`, `−0.1`, `+0.1` controls for the focused boundary. Arrow behavior is frame-sized while Shift+Arrow is 0.1 seconds. Outside boundary focus Arrow is 1 second and Shift+Arrow is 10 seconds. Disable global shortcuts for text-entry targets.

- [x] **Step 5: Integrate selection-scoped media behavior**

  Segment click pauses, selects, and seeks to start. Space/native Play loops only after user activation. Clicking video or an empty timeline clears segment scope without autoplay. Enter runs one-shot context preview. Up/Down navigate chronological segments, seek, and ensure the selection is visible. Display `Approximate frame stepping` when applicable.

- [x] **Step 6: Run focused tests and Svelte validation**

  Run: `node_modules/.bin/vitest run apps/web/src/lib/playback-controller.test.ts apps/web/src/lib/trim-controller.test.ts apps/web/src/lib/segment-constraints.test.ts`

  Then run the Svelte autofixer once per changed component and `apps/web/node_modules/.bin/svelte-check --tsconfig apps/web/tsconfig.json --fail-on-warnings`.

  Expected: focused tests and local Svelte checks pass.

- [x] **Step 7: Commit**

  ```bash
  git add apps/web/src
  git commit -m "feat: add precision playback and boundary controls"
  ```

---

### Task 4: Zoomable two-row precision timeline

**Files:**

- Create: `apps/web/src/lib/timeline-geometry.ts`
- Create: `apps/web/src/lib/timeline-geometry.test.ts`
- Create: `apps/web/src/lib/timeline-viewport.ts`
- Create: `apps/web/src/lib/timeline-viewport.test.ts`
- Create: `apps/web/src/components/PrecisionTimeline.svelte`
- Delete: `apps/web/src/components/BasicTimeline.svelte`
- Modify: `apps/web/src/components/VideoEditor.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- Produces `TimeScale` with `timeToPixel`, `pixelToTime`, `clampOffset`, and `visibleRange` from `{ durationSeconds, viewportWidth, zoom, offsetSeconds }`.
- Produces `zoomAt(scale, nextZoom, anchorPixel)`, `panByPixels(scale, deltaPixels)`, `fitSource(duration, width)`, and `ensureRangeVisible(scale, start, end)`.

- [ ] **Step 1: Write failing geometry and viewport tests**

  Cover timestamp/pixel round trips, zero/one-hour sources, minimum fit, maximum zoom, pointer anchor invariance, playhead-anchor button zoom, horizontal clamping, fit reset, and ensure-selected-range-visible.

- [ ] **Step 2: Implement the shared coordinate model**

  ```ts
  export interface TimelineViewport {
    readonly durationSeconds: number;
    readonly offsetSeconds: number;
    readonly viewportWidth: number;
    readonly zoom: number;
  }

  export class TimeScale {
    timeToPixel(seconds: number): number;
    pixelToTime(pixel: number): number;
    visibleRange(): { startSeconds: number; endSeconds: number };
  }
  ```

  Use this class for rendering, pointer seeking, hit testing, and tests; do not duplicate ratio formulas in Svelte.

- [ ] **Step 3: Replace BasicTimeline with PrecisionTimeline**

  Render decorative Canvas below semantic DOM controls. Draw segments in deterministic rows 0/1; put selected controls above neighbours. Empty-lane click clears selection and seeks. `Cmd/Ctrl+wheel` anchors zoom at the pointer, `+/-` anchor at playhead, scroll pans, and Fit restores the source.

- [ ] **Step 4: Persist viewport through normal project autosave**

  Debounce viewport persistence separately from high-frequency playhead painting. Project switching restores each document's `editor.timelineZoom` and `editor.timelineOffsetSeconds`. Selection calls `ensureRangeVisible` without changing zoom if the range already fits.

- [ ] **Step 5: Run focused tests and Svelte validation**

  Run: `node_modules/.bin/vitest run apps/web/src/lib/timeline-geometry.test.ts apps/web/src/lib/timeline-viewport.test.ts apps/web/src/lib/two-row-layout.test.ts`

  Then run the Svelte autofixer once and local `svelte-check`.

  Expected: focused tests and local Svelte checks pass.

- [ ] **Step 6: Commit**

  ```bash
  git add apps/web/src
  git commit -m "feat: add zoomable precision timeline"
  ```

---

### Task 5: Compact thumbnail contracts and durable job lifecycle

**Files:**

- Create: `packages/contracts/src/thumbnails.ts`
- Modify: `packages/contracts/src/index.ts`
- Modify: `packages/contracts/src/jobs.ts`
- Create: `packages/contracts/test/thumbnails.test.ts`
- Modify: `apps/server/src/jobs/job-repository.ts`
- Modify: `apps/server/src/jobs/job-queue.ts`
- Modify: `apps/server/src/imports/import-service.ts`
- Modify: `apps/server/test/job-queue.test.ts`
- Modify: `apps/server/test/storage.test.ts`

**Interfaces:**

- Adds job type `'generate-thumbnails'`; each type has at most one current successful/active job per source fingerprint and generator version.
- Produces compact manifest version 1:

  ```ts
  export interface ThumbnailManifestV1 {
    readonly schemaVersion: 1;
    readonly generatorVersion: string;
    readonly sourceFingerprint: string;
    readonly durationSeconds: number;
    readonly thumbnail: readonly [width: number, height: number];
    readonly pages: readonly [fileName: string, width: number, height: number][];
    readonly samples: readonly [
      timeSeconds: number,
      pageIndex: number,
      x: number,
      y: number,
      width: number,
      height: number,
    ][];
  }
  ```

- [ ] **Step 1: Add failing schema and lifecycle tests**

  Validate positional tuple lengths, safe `sprite-NNN.webp` names, ascending bounded sample times, page indexes/rectangles, job recovery, retry, and inspection-completion enqueueing thumbnails exactly once.

- [ ] **Step 2: Implement discriminated job contracts and repository creation**

  Generalize job creation without weakening project/filename/path validation. Existing inspection records remain valid. Thumbnail records use the same atomic per-job file lifecycle and monotonic transitions.

- [ ] **Step 3: Chain thumbnail work after usable inspection**

  After inspection metadata is atomically saved, ensure a queued thumbnail job. Recovery also ensures the job for inspected projects lacking a compatible completed set. Close does not cancel jobs; shutdown waits for the current process boundary and leaves recoverable state.

- [ ] **Step 4: Run focused contract and queue tests**

  Run: `node_modules/.bin/vitest run packages/contracts/test/thumbnails.test.ts apps/server/test/job-queue.test.ts apps/server/test/storage.test.ts`

  Expected: all listed tests pass.

- [ ] **Step 5: Commit**

  ```bash
  git add packages/contracts apps/server/src/jobs apps/server/src/imports/import-service.ts apps/server/test
  git commit -m "feat: queue compact thumbnail generation"
  ```

---

### Task 6: FFmpeg sprite generation and atomic promotion

**Files:**

- Create: `apps/server/src/jobs/ffmpeg-runner.ts`
- Create: `apps/server/test/ffmpeg-runner.test.ts`
- Create: `apps/server/src/thumbnails/thumbnail-manifest.ts`
- Create: `apps/server/src/thumbnails/thumbnail-worker.ts`
- Create: `apps/server/test/thumbnail-worker.test.ts`
- Modify: `apps/server/src/jobs/job-queue.ts`
- Modify: `apps/server/src/services.ts`
- Modify: `apps/server/src/storage/layout.ts`

**Interfaces:**

- Produces `createSamplingPlan(durationSeconds, targetIntervalSeconds = 2, maxSamples = 600)` with first/last samples in bounds.
- Produces `FfmpegRunner.generateSprites(request): Promise<void>` using `spawn(..., { shell: false })`, bounded stderr, timeout, and injected process runner for tests.
- Produces `ThumbnailWorker.generate(project, sourcePath, destinationDirectory): Promise<ThumbnailManifestV1>`.

- [ ] **Step 1: Write failing sampling and fake-runner tests**

  Cover short/one-hour sources, maximum 600 samples, safe sprite capacity/dimensions, shell-free argument construction, timeout/output limits, missing FFmpeg, partial output, corrupt dimensions, and failure preserving the previous valid set.

- [ ] **Step 2: Implement bounded WebP sprite generation**

  Generate only inside a sibling staging directory. FFmpeg writes bounded sprite pages directly or writes ephemeral sampled frames that are packed and deleted before promotion. Never promote individual frames. Use deterministic `sprite-001.webp` names.

- [ ] **Step 3: Validate and atomically promote the complete set**

  Validate manifest tuples and every referenced page before writing `manifest.json` last inside staging. Rename the previous set aside, rename staging to `thumbnails`, sync the project directory, then remove the old set. On failure restore the previous complete set and report a retryable safe error.

- [ ] **Step 4: Integrate the worker with job dispatch**

  Dispatch by `job.type`; inspection and generation failures receive distinct stable codes. A missing/stale/corrupt manifest queues regeneration. Valid compatible output survives reopen/restart without another job.

- [ ] **Step 5: Run focused server tests**

  Run: `node_modules/.bin/vitest run apps/server/test/ffmpeg-runner.test.ts apps/server/test/thumbnail-worker.test.ts apps/server/test/job-queue.test.ts`

  Expected: fake-process tests pass without invoking real FFmpeg.

- [ ] **Step 6: Commit**

  ```bash
  git add apps/server/src apps/server/test
  git commit -m "feat: generate durable thumbnail sprites"
  ```

---

### Task 7: Thumbnail API and visible-cell Canvas renderer

**Files:**

- Create: `apps/server/src/http/thumbnail-routes.ts`
- Modify: `apps/server/src/app.ts`
- Create: `apps/server/test/thumbnail-routes.test.ts`
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/thumbnail-renderer.ts`
- Create: `apps/web/src/lib/thumbnail-renderer.test.ts`
- Modify: `apps/web/src/components/PrecisionTimeline.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- `GET /api/projects/:id/thumbnails/manifest` returns the validated manifest or `404 thumbnail_not_ready`.
- `GET /api/projects/:id/thumbnails/:fileName` returns only a manifest-declared WebP with immutable cache headers.
- `drawVisibleThumbnails(context, manifest, images, scale, canvasSize)` draws intersecting samples only and returns `{ drawn, skipped }` for tests/diagnostics.

- [ ] **Step 1: Write failing route-security tests**

  Cover ready/not-ready manifests, corrupt manifest regeneration signal, unknown/traversal/symlink sprite rejection, range-independent complete WebP response, immutable cache headers, and one project's failure not affecting another.

- [ ] **Step 2: Implement validated manifest and sprite routes**

  Resolve project paths through `StorageLayout`, reject symlink components, parse the manifest before selecting a page, and never accept arbitrary filenames from the filesystem. Register routes under existing Host/Origin/Sec-Fetch protection.

- [ ] **Step 3: Write failing renderer tests**

  Use a fake Canvas context to assert only viewport-intersecting samples draw, source rectangles match positional tuples, unavailable images leave a neutral background, and stale async image loads cannot repaint a different active project.

- [ ] **Step 4: Implement Canvas sprite loading and drawing**

  Load one `Image` per visible sprite page, cache by project/fingerprint/page, and invalidate on manifest change. Draw only visible cells. Timeline remains usable before/without thumbnails and shows compact generating/failed/retry state from the existing job stream.

- [ ] **Step 5: Run focused tests and Svelte validation**

  Run: `node_modules/.bin/vitest run apps/server/test/thumbnail-routes.test.ts apps/web/src/lib/thumbnail-renderer.test.ts`

  Then run the Svelte autofixer once and local `svelte-check`.

  Expected: route, renderer, and local Svelte checks pass.

- [ ] **Step 6: Commit**

  ```bash
  git add apps/server/src apps/server/test apps/web/src
  git commit -m "feat: render compact timeline thumbnails"
  ```

---

### Task 8: Integrated verification and Phase 2 acceptance

**Files:**

- Modify: `README.md`
- Modify: `plans/phase-02-precision-editing/design.md`
- Modify: `plans/phase-02-precision-editing/implementation-01-precision-editing.md`

**Interfaces:**

- Consumes all prior tasks; produces no new runtime contract.

- [ ] **Step 1: Run one optional real-FFmpeg integration smoke**

  Generate a tiny MP4 in `/private/tmp`, import it into an isolated `/private/tmp/cut-on-eight-phase2-data`, wait for inspection and thumbnails, then assert the managed project contains `manifest.json` plus bounded `.webp` pages and no individual sampled frame files. Skip with a clear note only when FFmpeg is unavailable.

- [ ] **Step 2: Run the complete automated suite once**

  Run direct package binaries to avoid the known silent root-wrapper issue:

  ```bash
  node_modules/.bin/vitest run packages/contracts/test
  node_modules/.bin/vitest run apps/server/test
  node_modules/.bin/vitest run apps/web/src
  node_modules/.bin/tsc -p packages/contracts/tsconfig.json --noEmit
  node_modules/.bin/tsc -p apps/server/tsconfig.json --noEmit
  apps/web/node_modules/.bin/svelte-check --tsconfig apps/web/tsconfig.json --fail-on-warnings
  node_modules/.bin/eslint "apps/**/*.ts" "packages/**/*.ts"
  node_modules/.bin/prettier --check .
  ```

  Expected: all tests and static checks pass.

- [ ] **Step 3: Build production artifacts**

  Run:

  ```bash
  node_modules/.bin/tsc -p packages/contracts/tsconfig.json
  node_modules/.bin/tsc -p apps/server/tsconfig.json
  apps/web/node_modules/.bin/vite build --config apps/web/vite.config.ts
  ```

  Expected: contracts, server, and Vite builds finish successfully.

- [ ] **Step 4: Browser smoke the acceptance workflow**

  Through the Vite proxy, verify Editor/Library navigation, compact help/status, panel collapse, project switching, full-video seek, segment select-without-play, exact looping, Escape clearing, Start/End click and keyboard nudges, duration warnings, zoom/pan/fit, two-row overlap, triple-overlap explanation, async thumbnail appearance/retry, and no console errors.

- [ ] **Step 5: Record manual macOS acceptance accurately**

  Mark browser-automated items complete. Keep native picker, trackpad feel, real video playback precision, and native Play loop behavior explicitly pending unless a person performs them; do not claim them from unit tests.

- [ ] **Step 6: Update status and commit**

  Set design status to `Implemented` only when all automated checks and required manual acceptance are complete; otherwise use `Implementation complete; manual macOS acceptance pending` and list the remaining checks.

  ```bash
  git add README.md plans/phase-02-precision-editing
  git commit -m "docs: record Phase 2 verification"
  ```

---

## Plan Self-Review

- **Spec coverage:** Tasks 1-4 cover migration, overlap, layout, compact chrome, help, playback, trim, navigation, guidance, zoom, scrolling, and per-project viewport. Tasks 5-7 cover durable jobs, compact manifest/sprites, safe serving, retry, and visible-cell rendering. Task 8 covers performance-oriented and manual acceptance.
- **Storage policy:** Final derived thumbnail output is bounded WebP sprite pages plus one positional-array JSON manifest. Ephemeral frames stay in staging and are never promoted. Mutable sidecars/jobs remain separate atomic files.
- **Type consistency:** `ProjectDocument` v2, `ThumbnailManifestV1`, `PlaybackScope`, `BoundaryFocus`, `TimeScale`, and stable constraint codes are introduced before their consumers.
- **Placeholder scan:** The plan contains no deferred implementation markers or undefined follow-up steps; product deferrals remain only in the approved design.
- **Verification economy:** Every task runs only its contract seam plus local Svelte checks when necessary. The full suite, builds, real FFmpeg smoke, and browser acceptance run once at integration.
