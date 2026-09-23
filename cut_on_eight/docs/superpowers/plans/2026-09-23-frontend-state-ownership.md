# Frontend State Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each shared frontend value traceable to one owner, a named operation, and a read-only projection without changing visible behavior.

**Architecture:** Keep Svelte 5 rune-backed feature models. Separate the server workspace snapshot from open-video working copies, replace the editor's generic mutation callback with feature-scoped named operations, and keep cross-feature flows in `AppModel`. Use plain TypeScript for projections and editor transitions; do not build a store framework.

**Tech Stack:** TypeScript, Svelte 5, Vitest, existing Fastify API contracts.

**Spec:** `cut_on_eight/docs/superpowers/specs/2026-09-23-frontend-state-ownership-design.md`

## Global Constraints

- Preserve the client-only Svelte 5 SPA, backend API contract, autosave, explicit close, keyboard behavior, playback, and visible UI.
- Add no SignalTree, general store, global command bus, tracing, DevTools, or new runtime dependency.
- Keep component-only focus and fast playback sampling local; shared writes use named feature operations.
- Work only under `cut_on_eight`; keep `AGENTS.md` short and put the state guide elsewhere.
- For changed `.svelte` and `.svelte.ts` files, follow `apps/web/AGENTS.md`, including the repo-local Svelte skills and autofixer.

## Review Focus

1. A workspace poll arrives while a video has unsaved edits: Task 1 must retain the draft and accept new source facts and revision.
2. A save resolves after the user edits again: Task 1 must retain the newer edit and schedule another save.
3. A save fails: Task 1 must keep the draft and the retry control must still work.
4. A search result points to a fragment no longer in its video: Task 3 must open the video and leave fragment selection empty.
5. A late fragment/search response arrives after a newer request or disposal: Task 4 must not replace current state.

---

### Task 1: Separate the server workspace from editor working copies

**Files:**
- Create: `cut_on_eight/apps/web/src/app/workspace-projections.ts`
- Create: `cut_on_eight/apps/web/src/app/workspace-projections.test.ts`
- Modify: `cut_on_eight/apps/web/src/app/workspace-session.svelte.ts`
- Modify: `cut_on_eight/apps/web/src/app/workspace-session.test.ts`

**Interfaces:**
- Produces: `projectWorkspace(server: WorkspaceSnapshot | null, drafts: Readonly<Record<string, ProjectDocument>>): WorkspaceSnapshot | null` and `mergeUnsavedEditor(local, authoritative): ProjectDocument`.
- Preserves: `WorkspaceSession.workspace`, `activeProject`, `documentFor`, `applyWorkspace`, `saveStateFor`, and existing `WorkspacePort` until Task 2 changes the generic edit entry point.

- [ ] **Step 1: Add focused tests for projection and save races.** In `workspace-projections.test.ts`, use one server project and one draft with an edited title; assert `projectWorkspace` shows the draft but leaves the server input unchanged. In `workspace-session.test.ts`, add these cases:

```ts
session.applyWorkspace(snapshot(), false);
session.updateProject(projectId, (p) => ({
  ...p,
  metadata: { ...p.metadata, title: 'local edit' },
}));
session.applyWorkspace({
  ...snapshot(),
  openProjects: [{ ...project(), revision: 2, sourceHref: '/source' }],
});
expect(session.activeProject).toMatchObject({
  revision: 2,
  sourceHref: '/source',
  metadata: { title: 'local edit' },
});
```

Use a deferred `saveProject` promise to assert that an edit made during the first save remains `unsaved` and is sent by the next save. Reject one save, assert the draft and `failed` state remain, then call `retryAutosave` and assert `saved`.

- [ ] **Step 2: Run the focused tests and confirm the new cases fail.** Run `pnpm -C cut_on_eight/apps/web exec vitest run src/app/workspace-projections.test.ts src/app/workspace-session.test.ts`.

- [ ] **Step 3: Implement the state boundary.** Move the existing `mergeUnsavedEditor` logic to `workspace-projections.ts`. Keep a rune-backed authoritative snapshot and a draft record inside `WorkspaceSession`; expose a projected `workspace` getter so components keep the same read shape:

```ts
private serverWorkspace = $state.raw<WorkspaceSnapshot | null>(null);
private drafts = $state.raw<Record<string, ProjectDocument>>({});
private projectedWorkspace = $derived(
  projectWorkspace(this.serverWorkspace, this.drafts),
);
get workspace(): WorkspaceSnapshot | null {
  return this.projectedWorkspace;
}
```

`updateProject` writes only the working copy. `applyWorkspace` replaces the server snapshot, merges each unsaved draft with its matching new server project, and removes drafts for closed videos. A successful save updates the authoritative project revision; it clears a draft only when no newer edit exists. A failed save leaves the draft intact. Keep `SaveController`'s debounce, in-flight ordering, retry, and cancel behavior.

- [ ] **Step 4: Run the focused tests and web check.** Run the same Vitest command and `pnpm -C cut_on_eight/apps/web check`; expect all pass. Run the required Svelte autofixer on `workspace-session.svelte.ts`.

- [ ] **Step 5: Commit the working boundary.** Stage only Task 1 files and commit `refactor(cut-on-eight): separate workspace snapshots and drafts`.

### Task 2: Replace generic editor writes with named operations

**Files:**
- Create: `cut_on_eight/apps/web/src/domain/editor-operations.ts`
- Create: `cut_on_eight/apps/web/src/domain/editor-operations.test.ts`
- Modify: `cut_on_eight/apps/web/src/app/workspace-session.svelte.ts`
- Modify: `cut_on_eight/apps/web/src/components/EditorWorkspaceView.svelte`
- Modify: `cut_on_eight/apps/web/src/components/VideoEditor.svelte`
- Modify: `cut_on_eight/apps/web/src/app/workspace-session.test.ts`

**Interfaces:**
- Produces: `EditorOperation` (feature-local discriminated union) and `applyEditorOperation(project: ProjectDocument, operation: EditorOperation): ProjectDocument`.
- Produces: `WorkspaceSession.applyEditorOperation(projectId: string, operation: EditorOperation): void` and `selectFragment(projectId: string, fragmentId: string | null): void`.
- Consumes: Task 1 working-copy projection; no global dispatcher or new dependency.

- [ ] **Step 1: Test meaningful editor transitions.** Define operations for `playbackPositionRecorded`, `timelineViewportChanged`, `fragmentSelected`, `fragmentCreated`, `fragmentBoundaryAdjusted`, `fragmentExportChanged`, `fragmentMetadataChanged`, and `pauseAfterCreationChanged`. Test selection, validated boundary replacement, fragment creation without selection change, and a no-op that does not mark a draft dirty:

```ts
expect(
  applyEditorOperation(project(), {
    kind: 'fragmentSelected',
    fragmentId: '20000000-0000-4000-8000-000000000001',
  }).selectedSegmentId,
).toBe('20000000-0000-4000-8000-000000000001');
```

- [ ] **Step 2: Run the focused tests and confirm the new cases fail.** Run `pnpm -C cut_on_eight/apps/web exec vitest run src/domain/editor-operations.test.ts src/app/workspace-session.test.ts`.

- [ ] **Step 3: Add the feature-local operation contract.** Use this union rather than an arbitrary `(project) => project` callback:

```ts
export type EditorOperation =
  | { kind: 'playbackPositionRecorded'; seconds: number }
  | { kind: 'timelineViewportChanged'; zoom: number; offsetSeconds: number }
  | { kind: 'fragmentSelected'; fragmentId: string | null }
  | { kind: 'fragmentCreated'; fragment: Segment }
  | { kind: 'fragmentBoundaryAdjusted'; fragment: Segment }
  | { kind: 'fragmentExportChanged'; fragmentId: string; selected: boolean }
  | { kind: 'fragmentMetadataChanged'; fragmentId: string; title: string | null; tagIds: string[]; exportSelected: boolean }
  | { kind: 'pauseAfterCreationChanged'; enabled: boolean };
```

Implement each branch as a focused immutable update in `applyEditorOperation`. Keep `createSegment` and `nudgeBoundary` validation at their current call sites and emit the resulting validated fragment. `WorkspaceSession.applyEditorOperation` writes a draft and calls `markDirty` only when the projection changes. Change `VideoEditor` and `EditorWorkspaceView` to pass these named operations; keep fast playback samples in `samplePlaybackPosition`. Remove public `updateProject` after its callers are migrated.

- [ ] **Step 4: Run the focused tests and web check.** Run the Task 2 Vitest command, `pnpm -C cut_on_eight/apps/web check`, and the required autofixer on changed Svelte files.

- [ ] **Step 5: Commit the editor operations.** Stage only Task 2 files and commit `refactor(cut-on-eight): name editor state operations`.

### Task 3: Make cross-feature workflows explicit

**Files:**
- Modify: `cut_on_eight/apps/web/src/app/app-model.svelte.ts`
- Modify: `cut_on_eight/apps/web/src/app/app-model.test.ts`
- Modify: `cut_on_eight/apps/web/src/app/workspace-session.svelte.ts`
- Modify: `cut_on_eight/apps/web/src/components/EditorWorkspaceView.svelte`
- Modify: `cut_on_eight/apps/web/src/components/LibraryView.svelte`
- Modify: `cut_on_eight/apps/web/src/App.svelte`

**Interfaces:**
- Consumes: Task 2 `selectFragment` and existing `WorkspaceSession.reopenProject`.
- Produces: `AppModel.openSearchResult(videoId, fragmentId)`, `openProcessingVideo(videoId)`, and explicit app-level open/import navigation flows; feature models still own their state.

- [ ] **Step 1: Test cross-feature order and missing fragments.** Extend `app-model.test.ts` with a workspace snapshot containing a video and fragment. Assert `openSearchResult` reopens the video before selecting the fragment. For a missing fragment, assert the video opens with `selectedSegmentId === null`. Assert a failed reopen leaves the current view and selection unchanged.

- [ ] **Step 2: Run the focused tests and confirm the new cases fail.** Run `pnpm -C cut_on_eight/apps/web exec vitest run src/app/app-model.test.ts`.

- [ ] **Step 3: Put coordination in `AppModel`.** Replace its current generic `workspace.updateProject` call with:

```ts
async openSearchResult(videoId: string, fragmentId: string): Promise<void> {
  if (!(await this.workspace.reopenProject(videoId))) return;
  this.workspace.selectFragment(videoId, fragmentId);
  this.changeView('editor');
}
```

`selectFragment` checks that the target exists; otherwise it clears selection. Route the library's import/open callbacks through named `AppModel` methods and let those methods change view after success. Remove `WorkspaceSessionCallbacks.onImported` and `.onProjectOpened` once those flows call the coordinator directly. Keep `onWorkspaceApplied` only if needed as a narrow integration notification; do not move autosave or thumbnail logic into `AppModel`.

- [ ] **Step 4: Run the focused tests and web check.** Run the Task 3 Vitest command, `pnpm -C cut_on_eight/apps/web check`, and the required autofixer on changed Svelte files.

- [ ] **Step 5: Commit the coordination change.** Stage only Task 3 files and commit `refactor(cut-on-eight): make frontend workflows explicit`.

### Task 4: Confirm remaining owners and document the pattern

**Files:**
- Modify: `cut_on_eight/apps/web/src/app/fragment-library.svelte.ts`
- Modify: `cut_on_eight/apps/web/src/app/search-model.svelte.ts`
- Modify: `cut_on_eight/apps/web/src/app/fragment-library.test.ts`
- Modify: `cut_on_eight/apps/web/src/app/search-model.test.ts`
- Inspect: `cut_on_eight/apps/web/src/app/processing-model.svelte.ts` and `cut_on_eight/apps/web/src/app/ui-preferences.svelte.ts`
- Create: `cut_on_eight/docs/frontend-state.md`

**Interfaces:**
- Consumes: feature ownership and operation rules from Tasks 1-3.
- Produces: a brief owner/operation/projection guide, without changing public API contracts.

- [ ] **Step 1: Add race tests where missing.** In `fragment-library.test.ts`, make two `loadFragments` calls resolve out of order and assert the newer result wins. In `search-model.test.ts`, resolve a search after a newer query or disposal and assert it is ignored. Existing `processing-model.test.ts` already checks that a failed refresh keeps the last good snapshot. These are meaningful transitions, not tests for every field assignment.

- [ ] **Step 2: Run the focused tests.** Run `pnpm -C cut_on_eight/apps/web exec vitest run src/app/fragment-library.test.ts src/app/search-model.test.ts src/app/processing-model.test.ts` and note which newly added checks fail.

- [ ] **Step 3: Remove only state ambiguity exposed by those tests.** Keep existing models when they already own their values and stale-request guards. Inspect `ProcessingModel` and `UiPreferences`; leave them unchanged if they already meet the ownership rule. Rename generic public mutators only when a caller's intent is unclear. Keep component-only transient state local; do not introduce a common request-state abstraction. Write `docs/frontend-state.md` with the owner table, the named-write rule, the projection rule, and one editor/save flow showing where to look in code.

- [ ] **Step 4: Verify all behavior.** Run `./scripts/check.sh` and `./scripts/test.sh` from the repository root. Run `./scripts/integration.sh` when Docker is available. Run the required Svelte autofixer on changed Svelte files. Do a short manual editor check: open two videos, create/select a fragment, adjust timing, save/close, reopen from search, and confirm processing display still updates.

- [ ] **Step 5: Commit the guide and focused cleanup.** Stage only Task 4 files and commit `docs(cut-on-eight): explain frontend state ownership` (use `refactor` if production code changed).
