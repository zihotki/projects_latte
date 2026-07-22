# Frontend Application State Refactor

**Status:** Approved

**Date:** 2026-07-23

## Goal

Make the frontend application structure comprehensible without changing visible behavior, API contracts, persistence semantics, or keyboard interaction. `App.svelte` becomes a small composition root instead of owning every application workflow.

## Current Problem

`App.svelte` currently combines six responsibilities in one 960-line component:

- application initialization and disposal;
- open-project workspace state and autosave coordination;
- background job events, capabilities, retries, and thumbnails;
- fragment catalogue and tag mutations;
- UI preferences and editor mode;
- shell status, alerts, and three top-level views.

The individual workflows mostly work, but their state and side effects are interleaved. A change to one feature requires understanding unrelated features, and cross-feature mutation is implicit.

## Design Principles

- Preserve all visible behavior and backend contracts.
- Split by cohesive feature ownership, not by technical layer alone.
- Keep reactive state instance-scoped in Svelte 5 `.svelte.ts` classes.
- Keep domain calculations and immutable transformations in plain TypeScript.
- Use explicit narrow ports for cross-feature collaboration.
- Perform side effects in named commands and lifecycle methods, not reactive effects.
- Keep `App.svelte` declarative and small enough to understand in one pass.
- Avoid a replacement god object, global singleton stores, or speculative abstractions.

## Architecture

### Composition Root

`App.svelte` creates one `AppModel`, starts it, disposes it, and passes focused feature models to top-level view components. It owns only document metadata and shell composition.

`AppModel` wires dependencies and exposes application-wide derived status. It does not reimplement feature commands.

### Feature Models

#### `WorkspaceSession`

Owns:

- the workspace snapshot and active project;
- loading, importing, opening, switching, and closing state;
- per-project autosave controllers, save state, and save errors;
- sampled playback positions;
- active `VideoEditorControl` registration;
- import, open, activate, close, update, flush, retry, and disposal commands.

It is the sole frontend authority for open `ProjectDocument` instances. Other features update an open project only through a narrow `WorkspacePort`.

#### `BackgroundProcessing`

Owns:

- job snapshots and event-stream lifecycle;
- FFprobe capability state;
- job warnings and retry state;
- thumbnail manifests, request deduplication, and load failures;
- inspection and thumbnail job lookup.

Job event handlers explicitly request relevant thumbnail refreshes. No reactive effect coordinates network calls.

#### `FragmentLibrary`

Owns:

- catalogue and tag state;
- loading and error state;
- catalogue refresh and tag creation;
- fragment update, deletion, restoration, and thumbnail retry commands.

It depends on narrow ports for flushing or patching an open project and retrying a background job. Catalogue mutations remain consistent with the editor when the affected video is open.

#### `UiPreferences`

Owns:

- active top-level view;
- segment-panel collapsed state;
- the project currently editing a boundary;
- guarded local-storage reads and writes;
- derived editor mode.

The initial view remains library unless a restored workspace has an active project or a saved valid preference exists.

### Top-Level Views

- `AppStatus.svelte` renders backend, FFprobe, job, connection, and save alerts.
- `EditorWorkspaceView.svelte` renders the project strip, empty state, and active `VideoEditor`.
- `LibraryView.svelte` renders loading and `LibraryPanel` state.
- `FragmentLibraryView.svelte` adapts the fragment model to `FragmentsPanel`.

These components contain view composition only. They do not call API modules directly and do not duplicate feature state.

## State and Command Flow

### Initialization

1. `AppModel.start()` loads the workspace through `WorkspaceSession`.
2. `UiPreferences` chooses the initial view from persisted valid preferences and workspace state.
3. `BackgroundProcessing` loads capabilities and starts job events.
4. The fragment model loads either the catalogue or tags according to the active view.
5. Initialization failures remain visible through the existing shell alerts.

### Project Editing and Autosave

1. `VideoEditor` sends immutable project mutations to `WorkspaceSession.updateProject()`.
2. `WorkspaceSession` merges the latest sampled playback position and marks the corresponding `SaveController` dirty.
3. Save, switch, close, import, and catalogue mutation commands flush the relevant controller before continuing.
4. Editor prepare/release hooks retain the current save-boundary behavior.

### Background Processing and Thumbnails

1. Job events merge into `BackgroundProcessing.jobs`.
2. The event command explicitly checks the active project and newest thumbnail job.
3. Manifest requests are deduplicated by project and job revision.
4. Completed manifests, not-ready responses, corrupt records, retry state, and sprite load errors retain their current presentation.

### Fragment Mutations

1. `FragmentLibrary` flushes the affected open project through `WorkspacePort`.
2. It performs the API mutation.
3. It updates catalogue state and patches the open project through the port.
4. Delete returns the existing undo payload; restore reinserts the segment at its recorded index and refreshes the catalogue.

## Error Handling

- Each feature model owns errors produced by its commands.
- Application-wide workspace/import/switch failures appear in the existing general alert.
- Save failures remain keyed by project and retryable.
- Fragment catalogue errors remain inside the fragment view.
- Background connection, corrupt-job, capability, and thumbnail failures retain their existing messages and retry paths.
- Models ignore late async results after disposal or after a newer request supersedes them.
- Expected cleanup and save-controller errors remain contained where a safe UI status already represents them.

## Lifecycle and Reactivity

- Reactive UI-facing fields use `$state` or `$state.raw` according to mutation style.
- Cross-feature derived values are getters or `$derived` values; `$effect` is not used for orchestration.
- Each model is an instance created for the mounted app, not module-global state.
- `AppModel.dispose()` closes job events, cancels save controllers, clears editor control references, and prevents late writes.
- Svelte context is reserved for a future case where deeply nested consumers genuinely share a service. This refactor passes focused models explicitly to top-level views.

## Testing

- Preserve all existing tests as the behavior regression suite.
- Add focused tests for each model's public state transitions and coordination ports.
- Test autosave preservation, project switching, fragment/open-project synchronization, job-driven thumbnail refresh, request supersession, initialization, and disposal.
- Keep component tests minimal; use pure or model-level tests for orchestration and retain a browser smoke check for the three top-level views and editor state.
- Run TypeScript checks, Svelte check with warnings as failures, Svelte autofixer for every changed Svelte file, Vitest, ESLint, Prettier, production build, and `git diff --check`.

## Migration Strategy

1. Introduce model ports and pure helpers with characterization tests.
2. Extract `UiPreferences` and application status derivation.
3. Extract `WorkspaceSession` without changing component wiring.
4. Extract `BackgroundProcessing` and thumbnail coordination.
5. Extract `FragmentLibrary` and its workspace/job ports.
6. Add focused top-level view components and reduce `App.svelte` to composition.
7. Run the full automated and browser verification gates.

Each step must compile and preserve behavior. Temporary adapters are allowed during migration but removed before completion.

## Success Criteria

- `App.svelte` is a clear composition root containing no more than 180 lines.
- No feature model becomes a renamed copy of the old component.
- State ownership and cross-feature dependencies are explicit from file names and constructor interfaces.
- Existing UX, persistence, background processing, fragment operations, keyboard behavior, and API contracts are unchanged.
- Tests cover the extracted orchestration boundaries and all repository validation passes.
