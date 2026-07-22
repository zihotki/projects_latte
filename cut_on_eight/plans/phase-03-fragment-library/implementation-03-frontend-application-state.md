# Frontend Application State Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 960-line `App.svelte` coordinator with focused reactive feature models and top-level view components while preserving every visible behavior.

**Architecture:** Instance-scoped Svelte 5 `.svelte.ts` classes own workspace, background-processing, fragment-library, and UI-preference state. A small `AppModel` wires those models through narrow ports, and `App.svelte` becomes a declarative composition root with four focused view components.

**Tech Stack:** Svelte 5.56 runes, TypeScript 5.9, Vitest 4, existing Fastify/Zod contracts and API client.

## Global Constraints

- Keep all changes inside `projectslatte/cut_on_eight` and preserve both `AGENTS.md` files exactly.
- Preserve visible behavior, API contracts, persisted data, autosave timing, background processing, and keyboard behavior.
- Do not add dependencies, SvelteKit, SSR, global singleton stores, or reactive-effect orchestration.
- Use `$state.raw` for immutable API snapshots and ordinary `$state` only for reactive scalar/record state.
- Run the repository Svelte autofixer on every changed `.svelte` and `.svelte.ts` file until there are no relevant issues or suggestions.
- `App.svelte` must contain no more than 180 lines when complete.

---

### Task 1: UI Preferences and Application Status

**Files:**
- Create: `apps/web/src/app/ui-preferences.svelte.ts`
- Create: `apps/web/src/app/ui-preferences.test.ts`
- Create: `apps/web/src/app/app-status.ts`
- Create: `apps/web/src/app/app-status.test.ts`

**Interfaces:**
- Consumes: `ActiveView` and `EditorMode` from `components/EditorShell.svelte`; `WorkspaceSnapshot`, `ProjectDocument`, `JobSnapshot`, and `SaveState`.
- Produces: `UiPreferences`, `PreferenceStorage`, `deriveAppStatus(input)`, and `AppStatusSnapshot`.

- [ ] **Step 1: Write failing preference and status tests**

Cover valid and invalid persisted views, unavailable storage, default view selection, collapsed-panel persistence, boundary mode, editor mode, and ready/working/attention precedence.

```ts
import { describe, expect, it } from 'vitest';
import { UiPreferences } from './ui-preferences.svelte.js';

it('uses the saved view and persists explicit changes', () => {
  const values = new Map([['cut-on-eight.active-view', 'fragments']]);
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
  };
  const preferences = new UiPreferences(storage);
  preferences.initialize({ activeProjectId: null } as WorkspaceSnapshot);
  expect(preferences.activeView).toBe('fragments');
  preferences.changeView('editor');
  expect(values.get('cut-on-eight.active-view')).toBe('editor');
});
```

```ts
expect(
  deriveAppStatus({
    backendState: 'ready',
    ffprobeState: 'ready',
    importing: false,
    busy: false,
    jobs: { jobs: [], errors: [] },
    generalError: null,
    saveErrors: {},
  }),
).toEqual({ state: 'ready', label: 'Ready' });
```

- [ ] **Step 2: Run tests and verify the missing modules fail**

Run:

```bash
pnpm --filter @cut-on-eight/web test -- src/app/ui-preferences.test.ts src/app/app-status.test.ts
```

Expected: FAIL because the two production modules do not exist.

- [ ] **Step 3: Implement focused preference and status modules**

Use these public shapes:

```ts
export interface PreferenceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export class UiPreferences {
  activeView = $state<ActiveView>('library');
  segmentPanelCollapsed = $state(false);
  boundaryEditingProjectId = $state<string | null>(null);

  constructor(private readonly storage: PreferenceStorage | null) {}
  initialize(snapshot: Pick<WorkspaceSnapshot, 'activeProjectId'>): void;
  changeView(view: ActiveView): void;
  setSegmentPanelCollapsed(collapsed: boolean): void;
  setBoundaryMode(projectId: string, focused: boolean): void;
  editorMode(activeProject: ProjectDocument | null): EditorMode;
}
```

Storage reads and writes must use `try/catch`; invalid stored views fall back to library or editor according to `activeProjectId`.

```ts
export type BackendState = 'checking' | 'ready' | 'unavailable';
export interface AppStatusSnapshot {
  readonly state: 'ready' | 'working' | 'attention';
  readonly label: 'Ready' | 'Working' | 'Attention';
  readonly jobsLabel: string;
  readonly jobDataWarning: string | null;
}
export function deriveAppStatus(input: AppStatusInput): AppStatusSnapshot;
```

Move the exact precedence and copy from the existing `$derived` values in `App.svelte` into this pure function.

- [ ] **Step 4: Run focused tests and Svelte validation**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/ui-preferences.test.ts src/app/app-status.test.ts
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/app/ui-preferences.svelte.ts --svelte-version 5
pnpm --filter @cut-on-eight/web check
```

Expected: all focused tests pass and Svelte reports zero errors or warnings.

- [ ] **Step 5: Commit Task 1**

```bash
git add apps/web/src/app/ui-preferences.svelte.ts apps/web/src/app/ui-preferences.test.ts apps/web/src/app/app-status.ts apps/web/src/app/app-status.test.ts
git commit -m "refactor: extract frontend preferences and status"
```

---

### Task 2: Workspace Session and Autosave

**Files:**
- Create: `apps/web/src/app/workspace-session.svelte.ts`
- Create: `apps/web/src/app/workspace-session.test.ts`
- Modify: `apps/web/src/App.svelte`

**Interfaces:**
- Consumes: existing workspace API functions, `SaveController`, and `VideoEditorControl`.
- Produces: `WorkspaceSession`, `WorkspaceApi`, and `WorkspacePort`.

- [ ] **Step 1: Write failing workspace-session characterization tests**

Test initialization, immutable project updates, sampled playback merge, save-state reporting, flush-before-switch/import/close, prepare/release hooks, API failure messages, and disposal.

```ts
export interface WorkspacePort {
  hasOpenProject(projectId: string): boolean;
  flushProject(projectId: string): Promise<void>;
  patchSegment(projectId: string, segment: Segment): void;
  removeSegment(projectId: string, fragmentId: string): void;
  restoreSegment(projectId: string, segment: Segment, index: number): void;
}
```

```ts
it('preserves the sampled playback position when editing a segment', () => {
  const session = createSession(initialWorkspace);
  session.samplePlaybackPosition(projectId, 42.5);
  session.updateProject(projectId, (project) => ({
    ...project,
    selectedSegmentId: segmentId,
  }));
  expect(session.documentFor(projectId).playbackPositionSeconds).toBe(42.5);
  expect(session.saveStateFor(projectId)).toBe('unsaved');
});
```

- [ ] **Step 2: Run the focused test and verify failure**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/workspace-session.test.ts
```

Expected: FAIL because `WorkspaceSession` does not exist.

- [ ] **Step 3: Implement `WorkspaceSession` with injected APIs**

```ts
export interface WorkspaceApi {
  loadWorkspace(): Promise<WorkspaceSnapshot>;
  selectImport(): Promise<ImportSelectionResponse>;
  openProject(projectId: string): Promise<WorkspaceSnapshot>;
  activateProject(projectId: string): Promise<WorkspaceSnapshot>;
  saveProject(project: ProjectDocument): Promise<ProjectDocument>;
  closeProject(project: ProjectDocument): Promise<WorkspaceSnapshot>;
  deleteProject(projectId: string): Promise<WorkspaceSnapshot>;
}

export class WorkspaceSession implements WorkspacePort {
  workspace = $state.raw<WorkspaceSnapshot | null>(null);
  loading = $state(true);
  importing = $state(false);
  openingProjectId = $state<string | null>(null);
  busyProjectId = $state<string | null>(null);
  errorMessage = $state<string | null>(null);
  saveStates = $state<Record<string, SaveState>>({});
  saveErrors = $state<Record<string, string>>({});
  retryingProjectId = $state<string | null>(null);

  get activeProject(): ProjectDocument | null;
  get openProjectIds(): ReadonlySet<string>;
  initialize(): Promise<WorkspaceSnapshot>;
  importMp4(): Promise<ImportSelectionResponse['outcome'] | null>;
  reopenProject(projectId: string): Promise<boolean>;
  switchProject(projectId: string): Promise<void>;
  saveAndClose(projectId: string): Promise<void>;
  deleteManagedVideo(projectId: string): Promise<void>;
  updateProject(projectId: string, mutate: ProjectMutation): void;
  samplePlaybackPosition(projectId: string, seconds: number): void;
  registerEditorControl(control: VideoEditorControl): () => void;
  saveActiveProject(): Promise<void>;
  retryAutosave(projectId: string): Promise<void>;
  applyWorkspace(snapshot: WorkspaceSnapshot, preserveEdits?: boolean): void;
  dispose(): void;
}
```

Move the existing controller maps, document merging, save status handling, and project commands without changing ordering. Accept callbacks for `onWorkspaceApplied` and `onImportOutcome` rather than importing UI or background models.

- [ ] **Step 4: Adapt `App.svelte` to delegate workspace behavior**

Instantiate `WorkspaceSession` with the existing API functions. Replace workspace, loading, project, save, import, switch, close, and delete state/function references with the session. Do not extract markup in this task.

```ts
const workspaceSession = new WorkspaceSession(workspaceApi, {
  onWorkspaceApplied: () => requestActiveThumbnails(),
  onImportOutcome: (outcome) => {
    if (outcome !== 'cancelled') changeView('editor');
    void loadToolCapabilities();
  },
});
```

- [ ] **Step 5: Run focused and full frontend checks**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/workspace-session.test.ts src/lib/save-controller.test.ts
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/app/workspace-session.svelte.ts --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/App.svelte --svelte-version 5
pnpm --filter @cut-on-eight/web check
```

Expected: focused tests pass; Svelte check reports zero errors and warnings.

- [ ] **Step 6: Commit Task 2**

```bash
git add apps/web/src/app/workspace-session.svelte.ts apps/web/src/app/workspace-session.test.ts apps/web/src/App.svelte
git commit -m "refactor: extract workspace session state"
```

---

### Task 3: Background Jobs and Thumbnail State

**Files:**
- Create: `apps/web/src/app/background-processing.svelte.ts`
- Create: `apps/web/src/app/background-processing.test.ts`
- Modify: `apps/web/src/App.svelte`

**Interfaces:**
- Consumes: job/capability/thumbnail APIs, `connectJobEvents`, and an active-project getter.
- Produces: `BackgroundProcessing` and `BackgroundApi`.

- [ ] **Step 1: Write failing background-processing tests**

Test capability availability, event merge, corrupt-job warning, retry merge, active-project thumbnail lookup, request-key deduplication, not-ready handling, sprite failure, newer-request precedence, and disposal.

```ts
it('ignores a manifest response superseded by a newer job revision', async () => {
  const first = deferred<ThumbnailManifestV1>();
  const second = deferred<ThumbnailManifestV1>();
  const model = createBackground({
    loadThumbnailManifest: vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise),
  });
  const stale = model.refreshThumbnailManifest(projectId, 'job:1');
  const current = model.refreshThumbnailManifest(projectId, 'job:2');
  first.resolve(oldManifest);
  second.resolve(newManifest);
  await Promise.all([stale, current]);
  expect(model.thumbnailManifestFor(projectId)).toEqual(newManifest);
});
```

- [ ] **Step 2: Run the focused test and verify failure**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/background-processing.test.ts
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the background model**

```ts
export interface BackgroundApi {
  loadCapabilities(): Promise<Capabilities>;
  loadThumbnailManifest(projectId: string): Promise<ThumbnailManifestV1>;
  retryJob(jobId: string): Promise<JobRecord>;
  connectJobEvents(handlers: {
    onSnapshot(snapshot: JobSnapshot): void;
    onWarning(warning: string | null): void;
  }): () => void;
}

export class BackgroundProcessing {
  jobs = $state.raw<JobSnapshot | null>(null);
  ffprobeState = $state<BackendState>('checking');
  connectionWarning = $state<string | null>(null);
  retryingJobId = $state<string | null>(null);
  thumbnailManifests = $state.raw<Record<string, ThumbnailManifestV1>>({});
  thumbnailLoadErrors = $state<Record<string, string>>({});

  start(): void;
  loadToolCapabilities(): Promise<void>;
  inspectionJobFor(projectId: string): JobRecord | null;
  thumbnailJobFor(projectId: string): JobRecord | null;
  thumbnailManifestFor(projectId: string): ThumbnailManifestV1 | null;
  thumbnailStateFor(projectId: string): 'generating' | 'ready' | 'failed';
  requestThumbnails(projectId: string | null): void;
  refreshThumbnailManifest(projectId: string, requestKey: string): Promise<void>;
  retryThumbnails(projectId: string): Promise<void>;
  retryInspection(job: JobRecord): Promise<void>;
  retryJobById(jobId: string): Promise<void>;
  thumbnailPageLoadFailed(projectId: string): void;
  dispose(): void;
}
```

The job-event callback must merge the snapshot and call `requestThumbnails(getActiveProjectId())` directly. Preserve current error strings.

- [ ] **Step 4: Adapt `App.svelte` to delegate background behavior**

Replace job, capability, retry, and thumbnail fields/functions with `BackgroundProcessing`. Wire `WorkspaceSession.onWorkspaceApplied` to `background.requestThumbnails(workspace.activeProjectId)`.

- [ ] **Step 5: Run focused tests and Svelte validation**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/background-processing.test.ts src/lib/job-events.test.ts
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/app/background-processing.svelte.ts --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/App.svelte --svelte-version 5
pnpm --filter @cut-on-eight/web check
```

- [ ] **Step 6: Commit Task 3**

```bash
git add apps/web/src/app/background-processing.svelte.ts apps/web/src/app/background-processing.test.ts apps/web/src/App.svelte
git commit -m "refactor: extract background processing state"
```

---

### Task 4: Fragment Library State

**Files:**
- Create: `apps/web/src/app/fragment-library.svelte.ts`
- Create: `apps/web/src/app/fragment-library.test.ts`
- Modify: `apps/web/src/App.svelte`

**Interfaces:**
- Consumes: fragment/tag APIs, `WorkspacePort`, and a narrow `JobRetryPort`.
- Produces: `FragmentLibrary`, `FragmentApi`, and `JobRetryPort`.

- [ ] **Step 1: Write failing fragment-library tests**

Test catalogue/tag refresh, lower-level error containment, tag deduplication/sorting, flush-before-mutation, open-project patching, deletion/selection clearing, indexed restoration, catalogue refresh, and retry state.

```ts
export interface JobRetryPort {
  readonly retryingJobId: string | null;
  retryJobById(jobId: string): Promise<void>;
}
```

```ts
it('flushes and patches an open project after updating a fragment', async () => {
  const segment = { ...existingSegment, title: 'final' };
  api.updateFragment.mockResolvedValue(segment);
  await library.mutateFragment(projectId, segment.id, { title: 'final' });
  expect(workspace.flushProject).toHaveBeenCalledWith(projectId);
  expect(workspace.patchSegment).toHaveBeenCalledWith(projectId, segment);
  expect(library.catalogue?.fragments[0]?.segment).toEqual(segment);
});
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/fragment-library.test.ts
```

- [ ] **Step 3: Implement `FragmentLibrary`**

```ts
export class FragmentLibrary {
  catalogue = $state.raw<FragmentCatalogue | null>(null);
  tags = $state.raw<TagDefinition[]>([]);
  loading = $state(false);
  error = $state<string | null>(null);

  refresh(): Promise<void>;
  refreshTags(): Promise<void>;
  createTag(name: string): Promise<TagDefinition>;
  mutateFragment(projectId: string, fragmentId: string, mutation: FragmentMutation): Promise<Segment>;
  removeFragment(projectId: string, fragmentId: string): Promise<DeletedFragment>;
  restoreDeletedFragment(deleted: DeletedFragment): Promise<void>;
  retryThumbnail(jobId: string): Promise<void>;
  removeManagedVideo(projectId: string): Promise<void>;
}
```

`removeManagedVideo` coordinates `workspace.deleteManagedVideo(projectId)` followed by catalogue refresh; keep the actual workspace deletion API inside `WorkspaceSession`.

- [ ] **Step 4: Adapt `App.svelte` to delegate catalogue behavior**

Replace fragment catalogue, tag, load/error, and mutation functions. Preserve all current `FragmentsPanel` and `VideoEditor` callback signatures.

- [ ] **Step 5: Run focused tests and Svelte validation**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/fragment-library.test.ts src/lib/fragment-catalogue.test.ts
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/app/fragment-library.svelte.ts --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/App.svelte --svelte-version 5
pnpm --filter @cut-on-eight/web check
```

- [ ] **Step 6: Commit Task 4**

```bash
git add apps/web/src/app/fragment-library.svelte.ts apps/web/src/app/fragment-library.test.ts apps/web/src/App.svelte
git commit -m "refactor: extract fragment library state"
```

---

### Task 5: Application Model and Focused Top-Level Views

**Files:**
- Create: `apps/web/src/app/app-model.svelte.ts`
- Create: `apps/web/src/app/app-model.test.ts`
- Create: `apps/web/src/components/AppStatus.svelte`
- Create: `apps/web/src/components/EditorWorkspaceView.svelte`
- Create: `apps/web/src/components/LibraryView.svelte`
- Create: `apps/web/src/components/FragmentLibraryView.svelte`
- Modify: `apps/web/src/App.svelte`

**Interfaces:**
- Consumes: Tasks 1–4 feature models and existing leaf components.
- Produces: `AppModel` and four view components with focused model props.

- [ ] **Step 1: Write failing application-model lifecycle tests**

Test successful initialization order, initial view choice, fragments-vs-tags loading, backend failure status, view changes that refresh fragments, and idempotent disposal.

```ts
it('loads the catalogue only when fragments is the restored view', async () => {
  preferences.activeView = 'fragments';
  await app.start();
  expect(fragments.refresh).toHaveBeenCalledOnce();
  expect(fragments.refreshTags).not.toHaveBeenCalled();
  expect(background.start).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run test and verify failure**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/app-model.test.ts
```

- [ ] **Step 3: Implement the composition model**

```ts
export class AppModel {
  backendState = $state<BackendState>('checking');
  readonly workspace: WorkspaceSession;
  readonly background: BackgroundProcessing;
  readonly fragments: FragmentLibrary;
  readonly preferences: UiPreferences;

  get status(): AppStatusSnapshot;
  async start(): Promise<void>;
  changeView(view: ActiveView): void;
  dispose(): void;
}

export function createAppModel(): AppModel;
```

`start()` initializes workspace preferences first, then launches capabilities/events and the relevant fragment load. `dispose()` delegates exactly once to workspace and background.

- [ ] **Step 4: Extract top-level view composition**

Each view receives only its required models:

```svelte
<EditorWorkspaceView
  workspace={app.workspace}
  background={app.background}
  fragments={app.fragments}
  preferences={app.preferences}
/>
```

`AppStatus.svelte` receives `app`, renders the existing status `<dl>` and alerts, and never performs API calls. The three view components retain the existing DOM hierarchy and accessible labels so CSS and browser behavior do not change.

- [ ] **Step 5: Reduce `App.svelte` to the composition root**

The final component should follow this shape and stay below 180 lines:

```svelte
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { createAppModel } from './app/app-model.svelte.js';
  import AppStatus from './components/AppStatus.svelte';
  import EditorShell from './components/EditorShell.svelte';
  import EditorWorkspaceView from './components/EditorWorkspaceView.svelte';
  import FragmentLibraryView from './components/FragmentLibraryView.svelte';
  import LibraryView from './components/LibraryView.svelte';

  const app = createAppModel();
  onDestroy(() => app.dispose());
  void app.start();
</script>
```

Use `EditorShell` snippets only to place the focused components; no API calls, controller maps, catalogue mutation, or background-event logic may remain in `App.svelte`.

- [ ] **Step 6: Run model tests and all changed-file Svelte autofixers**

```bash
pnpm --filter @cut-on-eight/web test -- src/app/app-model.test.ts
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/app/app-model.svelte.ts --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/components/AppStatus.svelte --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/components/EditorWorkspaceView.svelte --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/components/LibraryView.svelte --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/components/FragmentLibraryView.svelte --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/App.svelte --svelte-version 5
pnpm --filter @cut-on-eight/web check
test "$(wc -l < apps/web/src/App.svelte)" -le 180
```

- [ ] **Step 7: Commit Task 5**

```bash
git add apps/web/src/app apps/web/src/components/AppStatus.svelte apps/web/src/components/EditorWorkspaceView.svelte apps/web/src/components/LibraryView.svelte apps/web/src/components/FragmentLibraryView.svelte apps/web/src/App.svelte
git commit -m "refactor: organize frontend application state"
```

---

### Task 6: Full Regression and Browser Verification

**Files:**
- Modify: `plans/phase-03-fragment-library/design-03-frontend-application-state.md`
- Modify: `plans/phase-03-fragment-library/implementation-03-frontend-application-state.md`

**Interfaces:**
- Consumes: completed Tasks 1–5.
- Produces: verified behavior-preserving frontend architecture and completed documentation.

- [ ] **Step 1: Run the complete automated gate**

```bash
pnpm test
pnpm check
pnpm build
git diff --check
test "$(wc -l < apps/web/src/App.svelte)" -le 180
git diff --name-only -- AGENTS.md apps/web/AGENTS.md
git status --short ../.pnpm-store
```

Expected: all tests and builds pass, Svelte reports no warnings, formatting is clean, `App.svelte` is at most 180 lines, both `AGENTS.md` files are untouched, and the parent pnpm store has no tracked changes.

- [ ] **Step 2: Perform a browser smoke test**

Run `pnpm dev`, then verify:

1. Restored open videos, active video, playback position, and selected segment match persisted state.
2. Editor, Library, and Fragments tabs render and retain their existing DOM and behavior.
3. Import cancellation, reopen, switch, save/close, and delete confirmation behave as before without modifying an external original.
4. Segment editing autosaves; save failure/retry remains visible.
5. Job status, FFprobe warning, thumbnail generation/retry, and sprite failure retain their UI states.
6. Fragment title/tags/delete/undo and cross-view synchronization remain correct.
7. Segment/source keyboard focus and playback behavior from the previous repair remains intact.

Restore the user's initial selection, playback position, and view after the smoke test.

- [ ] **Step 3: Mark the design and plan complete**

Set both documents to:

```markdown
**Status:** Complete
```

- [ ] **Step 4: Re-run documentation formatting and final diff checks**

```bash
node_modules/.bin/prettier --write plans/phase-03-fragment-library/design-03-frontend-application-state.md plans/phase-03-fragment-library/implementation-03-frontend-application-state.md
git diff --check
git status --short
```

- [ ] **Step 5: Commit verification documentation**

```bash
git add plans/phase-03-fragment-library/design-03-frontend-application-state.md plans/phase-03-fragment-library/implementation-03-frontend-application-state.md
git commit -m "docs: complete frontend application state refactor"
```
