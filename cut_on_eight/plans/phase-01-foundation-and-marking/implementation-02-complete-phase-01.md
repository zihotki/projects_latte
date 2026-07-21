# Complete Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the approved Phase 1 workflow: managed MP4 import, restored multi-project workspace, rough keyboard marking, atomic saves and non-blocking close, byte-range playback, and durable FFprobe inspection.

**Architecture:** Keep Fastify as the trusted local boundary and Svelte as a client-only UI. Persist versioned JSON below `~/cut-on-eight_data`, expose task-specific contracts through the shared package, and keep segment rules in plain TypeScript. Use dependency injection around the native picker, filesystem root, clock, and FFprobe runner so focused tests do not touch the real library.

**Tech Stack:** Node.js 24, TypeScript 5.9, Fastify 5, Zod 4, Svelte 5, Vite 8, Vitest 4, native Node filesystem/process APIs, macOS `osascript`, and `ffprobe`.

## Global Constraints

- Keep every product change below `projectslatte/cut_on_eight`.
- Keep the frontend client-only; do not add SvelteKit, SSR, Electron, or an installable package.
- Bind the backend only to `127.0.0.1`.
- Use `~/cut-on-eight_data` by default and `CUT_ON_EIGHT_DATA_ROOT` only for tests and local overrides.
- Copy or clone an external MP4 into managed storage before it becomes editable.
- Never expose an unrestricted filesystem path or shell/process endpoint to the browser.
- Preserve malformed sidecars; never overwrite them automatically.
- Explicit close saves first, removes the project from the workspace, and never waits for background jobs.
- Keep tests focused on contracts and behavior rather than broad UI test scaffolding.
- Preserve the user-edited `AGENTS.md` files.

---

### Task 1: Define Phase 1 contracts and pure segment behavior

**Files:**

- Create: `packages/contracts/src/errors.ts`
- Create: `packages/contracts/src/project.ts`
- Create: `packages/contracts/src/workspace.ts`
- Create: `packages/contracts/src/jobs.ts`
- Create: `packages/contracts/src/api.ts`
- Modify: `packages/contracts/src/index.ts`
- Create: `packages/contracts/test/project.test.ts`
- Create: `apps/web/src/lib/segments.ts`
- Create: `apps/web/src/lib/segments.test.ts`

**Interfaces:**

- Produces `ProjectDocument`, `ProjectSummary`, `WorkspaceSnapshot`, `JobRecord`, `ApiError`, and their Zod schemas.
- Produces `createSegment`, `deleteSelectedSegment`, `deleteMostRecentSegment`, and `sortSegmentsByStart` for the UI.
- Persisted schemas use `schemaVersion: 1` and reject unknown incompatible versions.

- [ ] **Step 1: Add strict persisted schemas**

Define these stable shapes in `packages/contracts/src/project.ts`:

```ts
export const segmentSchema = z.object({
  id: z.string().uuid(),
  startSeconds: z.number().finite().nonnegative(),
  endSeconds: z.number().finite().positive(),
  exportSelected: z.boolean(),
});

export const projectDocumentSchema = z.object({
  schemaVersion: z.literal(1),
  id: z.string().uuid(),
  source: z.object({
    fileName: z.string().min(1),
    durationSeconds: z.number().finite().positive().nullable(),
    width: z.number().int().positive().nullable(),
    height: z.number().int().positive().nullable(),
    frameRate: z.string().nullable(),
    hasAudio: z.boolean().nullable(),
  }),
  settings: z.object({ pauseAfterCreation: z.boolean() }),
  playbackPositionSeconds: z.number().finite().nonnegative(),
  selectedSegmentId: z.string().uuid().nullable(),
  segments: z.array(segmentSchema),
  metadata: z.object({
    title: z.string().nullable(),
    tags: z.array(z.string()),
    notes: z.string().nullable(),
  }),
});
```

Add refinements requiring `endSeconds > startSeconds` and requiring `selectedSegmentId` to reference an existing segment when non-null.

- [ ] **Step 2: Add safe API and workspace schemas**

Define `ProjectSummary` without managed or external filesystem paths. Define:

```ts
type WorkspaceSnapshot = {
  activeProjectId: string | null;
  openProjects: ProjectDocument[];
  library: ProjectSummary[];
};

type ImportSelectionResponse =
  | { outcome: 'cancelled'; workspace: WorkspaceSnapshot }
  | { outcome: 'imported' | 'reopened'; projectId: string; workspace: WorkspaceSnapshot };
```

Use a shared error envelope `{ error: { code, message, retryable, details? } }`. Add job states `queued`, `running`, `completed`, and `failed`, with the single Phase 1 type `inspect-source`.

- [ ] **Step 3: Add contract tests**

Test valid round-trips, invalid segment boundaries, dangling selection IDs, incompatible schema versions, and rejection of filesystem path fields in browser-facing summaries.

Run:

```bash
pnpm --filter @cut-on-eight/contracts test
```

Expected: all contract tests pass.

- [ ] **Step 4: Add pure segment operations**

`createSegment` returns the unchanged input when there is no pending start or when `endSeconds <= startSeconds`. Otherwise it appends a UUID segment, selects it, and keeps storage order as creation order. `sortSegmentsByStart` returns a copy ordered by start, then end, then ID. Deletion functions clear a removed selection and never mutate their input.

- [ ] **Step 5: Test overlap and deletion rules**

Cover five overlapping creations, chronological display sorting, selected deletion, most-recent creation deletion, and invalid `O` behavior.

Run:

```bash
pnpm --filter @cut-on-eight/web test
```

Expected: pure segment tests pass without a browser environment.

- [ ] **Step 6: Commit**

```bash
git add cut_on_eight/packages/contracts cut_on_eight/apps/web/src/lib/segments.ts cut_on_eight/apps/web/src/lib/segments.test.ts
git commit -m "feat: define Phase 1 project contracts"
```

### Task 2: Add atomic managed-storage repositories

**Files:**

- Modify: `apps/server/src/config.ts`
- Create: `apps/server/src/storage/atomic-json.ts`
- Create: `apps/server/src/storage/layout.ts`
- Create: `apps/server/src/storage/library-repository.ts`
- Create: `apps/server/src/storage/project-repository.ts`
- Create: `apps/server/src/storage/workspace-repository.ts`
- Create: `apps/server/test/storage.test.ts`

**Interfaces:**

- Produces `StorageLayout`, `LibraryRepository`, `ProjectRepository`, and `WorkspaceRepository`.
- `StorageLayout` is the only module that converts project IDs into filesystem paths.
- Repositories validate every read and use temporary-file-plus-rename for every write.

- [ ] **Step 1: Add configurable data-root resolution**

Extend `ServerConfig` with `dataRoot`. Default to `join(homedir(), 'cut-on-eight_data')`; accept an absolute `CUT_ON_EIGHT_DATA_ROOT` for isolated tests and reject relative values.

- [ ] **Step 2: Implement atomic JSON writes**

`writeJsonAtomic(target, value)` creates the parent directory, writes UTF-8 JSON through an exclusive temporary file in the same directory, calls `FileHandle.sync()`, closes it, and renames it over the target. Clean up only the temporary file created by the current call when a write fails.

- [ ] **Step 3: Implement the storage layout**

Use:

```text
<root>/_system/workspace.json
<root>/_system/library.json
<root>/<slug>--<short-id>/<source>.mp4
<root>/<slug>--<short-id>/<source>.mp4.danceclips.json
<root>/<slug>--<short-id>/jobs/<job-id>.json
```

Store the full UUID in library data; derive `short-id` only for the folder name. Reject any stored relative path containing `..`, an absolute path, or a path escaping `dataRoot`.

- [ ] **Step 4: Implement repositories**

`library.json` stores version, safe managed relative paths, import fingerprints `{ realPath, size, modifiedMilliseconds }`, and import timestamps. `workspace.json` stores ordered open IDs and one active ID. Project sidecars use `projectDocumentSchema`.

Missing files return empty version-1 documents. Invalid existing JSON returns a typed `corrupt_persisted_data` error and is never rewritten by a read or autosave path.

- [ ] **Step 5: Test persistence and corruption behavior**

Use `mkdtemp` under the test temporary directory. Verify atomic replacement, restoration, path escape rejection, missing-file defaults, and that malformed sidecar bytes remain byte-for-byte unchanged after a failed save attempt.

Run:

```bash
pnpm --filter @cut-on-eight/server test -- storage.test.ts
```

Expected: storage tests pass.

- [ ] **Step 6: Commit**

```bash
git add cut_on_eight/apps/server/src/config.ts cut_on_eight/apps/server/src/storage cut_on_eight/apps/server/test/storage.test.ts
git commit -m "feat: add atomic managed storage"
```

### Task 3: Implement native selection and transactional MP4 import

**Files:**

- Create: `apps/server/src/imports/source-picker.ts`
- Create: `apps/server/src/imports/source-validator.ts`
- Create: `apps/server/src/imports/import-service.ts`
- Create: `apps/server/src/jobs/job-repository.ts`
- Create: `apps/server/test/import-service.test.ts`

**Interfaces:**

- Produces `SourcePicker.selectMp4(): Promise<string | null>` and `ImportService.selectAndImport(): Promise<ImportResult>`.
- Consumes the repositories from Task 2 and produces the minimal durable `JobRepository.createQueuedInspection(projectId, projectDirectory)` operation that Task 7 extends into a worker.

- [ ] **Step 1: Add an injectable macOS picker**

Run `osascript` with a fixed script that asks for one `public.mpeg-4` file and prints its POSIX path. Treat AppleScript cancellation error `-128` as `null`; convert all other failures into `native_picker_failed`. Never accept script text or process arguments from an HTTP request.

- [ ] **Step 2: Validate source files**

Resolve the real path, require a regular `.mp4` file, require a positive size, and verify the first 12 bytes contain an ISO base-media `ftyp` box. Return a fingerprint from real path, size, and modified time.

- [ ] **Step 3: Implement transactional import**

If the fingerprint already exists, reopen and activate the known project. Otherwise:

1. Allocate a UUID and `<slug>--<short-id>.importing` directory.
2. Copy with `copyFile(source, destination, constants.COPYFILE_FICLONE)`; Node falls back when clone-on-write is unsupported.
3. Re-stat and validate the managed copy.
4. Write the initial version-1 sidecar and queued inspection job inside the temporary directory.
5. Rename the temporary directory to its final collision-safe name.
6. Add the library record, then open and activate the project.

On failure, remove only that `.importing` directory and leave existing library/workspace files unchanged. On startup, clean stale directories ending in `.importing`.

- [ ] **Step 4: Test cancellation, duplicate reopen, and rollback**

Inject a fake picker and temporary data root. Verify cancellation changes nothing, a successful import creates the exact layout, a second identical selection reopens without copying, and injected copy/write failures expose no partial library project.

Run:

```bash
pnpm --filter @cut-on-eight/server test -- import-service.test.ts
```

Expected: import lifecycle tests pass.

- [ ] **Step 5: Commit**

```bash
git add cut_on_eight/apps/server/src/imports cut_on_eight/apps/server/src/jobs/job-repository.ts cut_on_eight/apps/server/test/import-service.test.ts
git commit -m "feat: import MP4 files into managed storage"
```

### Task 4: Add workspace, save, close, and byte-range APIs

**Files:**

- Create: `apps/server/src/http/api-error.ts`
- Create: `apps/server/src/http/workspace-routes.ts`
- Create: `apps/server/src/http/project-routes.ts`
- Create: `apps/server/src/http/source-routes.ts`
- Create: `apps/server/src/services.ts`
- Modify: `apps/server/src/app.ts`
- Modify: `apps/server/src/server.ts`
- Create: `apps/server/test/workspace-api.test.ts`
- Create: `apps/server/test/source-range.test.ts`

**Interfaces:**

- `createApp({ config, picker, probeRunner? })` constructs isolated services for tests.
- Produces the approved task-specific endpoints and never returns managed paths.

- [ ] **Step 1: Centralize structured API errors**

Map typed domain errors to stable HTTP statuses and the shared error envelope. Unknown errors return `internal_error` without filesystem paths, command output, or stack traces in the response.

- [ ] **Step 2: Add workspace and import routes**

Implement:

```text
GET  /api/workspace
POST /api/imports/select
POST /api/projects/:id/open
POST /api/projects/:id/activate
PUT  /api/projects/:id
POST /api/projects/:id/close
```

`close` accepts the current validated `ProjectDocument`, saves it first, and updates the workspace only after save succeeds. Jobs are not consulted or awaited.

- [ ] **Step 3: Add safe video streaming**

Implement `GET /api/sources/:projectId/content`. Resolve the source only through the library repository. Support no range with `200` and one `bytes=start-end` range with `206`, `Accept-Ranges`, `Content-Range`, `Content-Length`, and `video/mp4`. Return `416` with `Content-Range: bytes */<size>` for invalid or unsatisfiable ranges.

- [ ] **Step 4: Test API invariants**

Verify restored workspace ordering, activation, closed-project reopen, save-before-close, save failure keeping a project open, absence of filesystem paths in JSON, complete streaming, open-ended ranges, suffix ranges, and `416` behavior.

Run:

```bash
pnpm --filter @cut-on-eight/server test -- workspace-api.test.ts source-range.test.ts
```

Expected: API and range tests pass.

- [ ] **Step 5: Commit**

```bash
git add cut_on_eight/apps/server/src cut_on_eight/apps/server/test/workspace-api.test.ts cut_on_eight/apps/server/test/source-range.test.ts
git commit -m "feat: expose managed workspace APIs"
```

### Task 5: Implement the multi-project Svelte workspace shell

**Files:**

- Create: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/save-controller.ts`
- Create: `apps/web/src/components/AppBar.svelte`
- Create: `apps/web/src/components/ProjectStrip.svelte`
- Create: `apps/web/src/components/LibraryPanel.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- `api.ts` validates every response with shared Zod schemas and throws a typed safe `ApiFailure`.
- `SaveController` exposes `saved | saving | unsaved | failed`, one-second debounce, `flush()`, and `cancel()`.
- `App.svelte` owns the current `WorkspaceSnapshot` and one editable document per open project.

- [ ] **Step 1: Build the validated API client**

Add functions for workspace load, picker import, library reopen, activation, save, close, job retry, and source URL construction. On non-2xx responses, parse the shared error envelope; use `invalid_server_response` if response validation fails.

- [ ] **Step 2: Add the save controller**

Use an injected async save function and clock wrappers. A mutation marks unsaved and restarts a one-second timer. `flush()` cancels the timer and awaits exactly one save. If a mutation occurs during a save, schedule another save rather than losing it. Add focused Vitest tests with fake timers.

- [ ] **Step 3: Replace the hello shell**

On startup, load the workspace. The app bar shows Import MP4, managed-library reopen, backend state, FFprobe state, and global jobs state. The project strip shows filename, active state, save state, job state, and an explicit close button. Switching flushes the current project playback state, activates the next project, and restores its state.

- [ ] **Step 4: Implement close semantics in the UI**

Close calls `flush()` and then the close endpoint with the current document. Remove the tab only after the endpoint succeeds. Show an inline actionable error on save/close failure. Do not wait for an inspection job.

- [ ] **Step 5: Validate Svelte files**

Run the repository Svelte autofixer on each changed component, then:

```bash
pnpm --filter @cut-on-eight/web check
pnpm --filter @cut-on-eight/web test
```

Expected: zero Svelte warnings/errors and passing save-controller tests.

- [ ] **Step 6: Commit**

```bash
git add cut_on_eight/apps/web
git commit -m "feat: add multi-project workspace shell"
```

### Task 6: Add the rough-marking video editor

**Files:**

- Create: `apps/web/src/components/VideoEditor.svelte`
- Create: `apps/web/src/components/BasicTimeline.svelte`
- Create: `apps/web/src/components/SegmentList.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- `VideoEditor` receives the active `ProjectDocument`, emits document mutations, and exposes no server state.
- The native video source is `/api/sources/:projectId/content`.
- Playback sampling remains local to the editor and uses `requestAnimationFrame` while playing.

- [ ] **Step 1: Add native video playback and independent position state**

Restore `playbackPositionSeconds` after metadata loads, persist sampled position through the parent mutation callback, and stop the animation frame loop on pause or component destruction. Switching projects remounts the player keyed by project ID.

- [ ] **Step 2: Add keyboard commands**

Handle shortcuts only when the event target is not an input, textarea, select, or contenteditable element. Implement Space, I, O, Escape, Delete, Backspace, and Cmd/Ctrl+S exactly as approved. Prevent default only when the command is handled.

- [ ] **Step 3: Add timeline and chronological list**

Render a basic duration-scaled lane with a pending in-point overlay and segment overlays. Overlap is allowed. Clicking a segment selects it and seeks to its start. Render the list from `sortSegmentsByStart` without changing creation order in the persisted document.

- [ ] **Step 4: Connect mutations to autosave**

Every segment, selection, setting, and playback-position mutation updates only the active project and schedules its own save controller. `O` continues playback unless `pauseAfterCreation` is enabled.

- [ ] **Step 5: Validate and manually smoke the editor**

Run the Svelte autofixer for all three components and `App.svelte`, then:

```bash
pnpm --filter @cut-on-eight/web check
pnpm --filter @cut-on-eight/web test
```

With a managed fixture, verify five overlapping marks, switching projects, independent positions, explicit save, and close.

- [ ] **Step 6: Commit**

```bash
git add cut_on_eight/apps/web
git commit -m "feat: add rough video segment marking"
```

### Task 7: Add the durable inspection queue and FFprobe

**Files:**

- Modify: `apps/server/src/jobs/job-repository.ts`
- Create: `apps/server/src/jobs/ffprobe-runner.ts`
- Create: `apps/server/src/jobs/job-queue.ts`
- Create: `apps/server/src/http/job-routes.ts`
- Modify: `apps/server/src/services.ts`
- Modify: `apps/server/src/app.ts`
- Create: `apps/server/test/job-queue.test.ts`
- Create: `apps/server/test/ffprobe-runner.test.ts`

**Interfaces:**

- `JobQueue.enqueueInspection(projectId)` durably writes before returning.
- One worker processes jobs serially; close never owns or cancels the worker.
- `ProbeRunner.inspect(sourcePath)` returns duration, dimensions, rational frame-rate text, and audio presence.

- [ ] **Step 1: Persist job records atomically**

Store one version-1 JSON file per job. On startup, validate all known job files and change `running` records back to `queued`. Keep `failed` records for explicit retry. Corrupt job files remain untouched and surface as queue errors without blocking other projects.

- [ ] **Step 2: Implement FFprobe execution**

Spawn only the configured `ffprobe` executable with fixed arguments:

```text
-v error -print_format json -show_format -show_streams <managed-source>
```

Do not use a shell. Bound captured stdout/stderr, reject malformed JSON, and map `ENOENT` to `ffprobe_missing`. Parse video duration, width, height, `avg_frame_rate`, and audio-stream presence.

- [ ] **Step 3: Implement the serial worker**

Transition and persist `queued -> running -> completed|failed`. Increment attempts on start. After successful inspection, update the project sidecar through `ProjectRepository`. Publish in-process job-change events after each durable transition.

- [ ] **Step 4: Add job APIs and SSE**

Implement:

```text
GET  /api/jobs
GET  /api/events
POST /api/jobs/:id/retry
GET  /api/capabilities
```

SSE sends an initial `jobs` snapshot, job updates, a 20-second keepalive comment, and cleans listeners on disconnect. Capabilities report backend and FFprobe availability without blocking editing.

- [ ] **Step 5: Test recovery and non-blocking failure**

Verify running-job recovery, serial processing, successful sidecar metadata update, missing FFprobe producing retryable failure, retry changing failed to queued, and a project close completing while its job remains queued/running.

Run:

```bash
pnpm --filter @cut-on-eight/server test -- job-queue.test.ts ffprobe-runner.test.ts
```

Expected: queue and parser tests pass without requiring a system FFprobe binary.

- [ ] **Step 6: Commit**

```bash
git add cut_on_eight/apps/server
git commit -m "feat: add durable FFprobe inspection jobs"
```

### Task 8: Surface job state and complete restoration

**Files:**

- Create: `apps/web/src/lib/job-events.ts`
- Modify: `apps/web/src/components/AppBar.svelte`
- Modify: `apps/web/src/components/ProjectStrip.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- `connectJobEvents` owns one `EventSource`, validates snapshots, reconnects using browser behavior, and returns a close function.
- UI derives per-project and global states from the latest job snapshot.

- [ ] **Step 1: Connect SSE with snapshot fallback**

Load `/api/jobs` before connecting. Replace local job state only with validated snapshots. On SSE parsing failure keep the last valid state and show a non-destructive connection warning.

- [ ] **Step 2: Show job and tool health**

Show global counts in the app bar and the newest inspection state on each project tab. Failed inspection exposes Retry. Missing FFprobe explains that marking still works.

- [ ] **Step 3: Confirm restoration flow**

Refresh with two projects open and verify open order, active ID, selected segment, playback position, segments, save states, and job status restore without re-importing.

- [ ] **Step 4: Validate Svelte and commit**

Run the Svelte autofixer, web check, and web tests, then:

```bash
git add cut_on_eight/apps/web
git commit -m "feat: show durable background job state"
```

### Task 9: Finalize documentation and Phase 1 verification

**Files:**

- Modify: `README.md`
- Modify: `.gitignore` only if runtime verification exposes an unignored generated path.

**Interfaces:**

- Documents normal local development, optional data-root override, required macOS picker behavior, and FFprobe installation without making FFprobe a playback prerequisite.

- [ ] **Step 1: Update the developer and user quickstart**

Document `pnpm install`, `pnpm dev`, `~/cut-on-eight_data`, Import MP4, keyboard controls, save/close semantics, managed-library reopen, and FFprobe failure behavior. Include a warning that deleting managed storage deletes the catalogue.

- [ ] **Step 2: Run all automated checks**

```bash
pnpm format
pnpm check
pnpm test
pnpm build
git diff --check
```

Expected: all commands exit successfully.

- [ ] **Step 3: Run an isolated-data-root smoke**

Start with a disposable absolute `CUT_ON_EIGHT_DATA_ROOT`, import a fixture through injected integration coverage, verify range playback, mark five overlapping segments, switch between two projects, save, close without waiting for inspection, reopen from the library, restart the backend, and confirm restoration.

- [ ] **Step 4: Perform the macOS manual checks**

Run normal `pnpm dev` and verify the standard picker opens without restarting the app. Import a real MP4, confirm the managed copy exists before editing, confirm browser seeking, and confirm source edits/new frontend files hot-reload. Repeat once with FFprobe unavailable and confirm marking remains usable.

- [ ] **Step 5: Request independent review and fix findings**

Review the complete Phase 1 diff against the approved design and acceptance criteria. Fix all Critical and Important findings and rerun the full verification commands.

- [ ] **Step 6: Commit**

```bash
git add cut_on_eight
git commit -m "docs: complete Cut on Eight Phase 1"
```

- [ ] **Step 7: Confirm scope and history**

```bash
git status --short --branch
git log --oneline -12
```

Expected: no Cut on Eight changes remain uncommitted, no new application/configuration files exist above `cut_on_eight`, and all Phase 1 commits are visible.
