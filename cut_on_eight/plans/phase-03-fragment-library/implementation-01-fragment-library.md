# Phase 3 Fragment Library Implementation Plan

**Status:** Complete

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cross-video fragment catalogue with shared editing, five-frame previews, inline looping playback, undoable fragment deletion, global lowercase tags, and safe managed-video deletion.

**Architecture:** Project sidecars remain authoritative. The server aggregates fragments on demand, owns catalogue metadata and destructive mutations, and derives compact sprite crop references; the Svelte SPA adds a dedicated Fragments view and reuses one player and one fragment editor. All mutations remain serialized behind the existing service queue.

**Tech Stack:** TypeScript 5.9, Zod, Fastify 5, Svelte 5 runes, Vitest, existing WebP sprite manifests.

## Global Constraints

- Keep all changes inside `projectslatte/cut_on_eight` and preserve both `AGENTS.md` files exactly.
- Keep the SPA client-only with a separate local backend; do not add SSR, SvelteKit, Electron, a database, or new runtime dependencies.
- Keep project sidecars authoritative; do not persist a duplicate fragment index or create per-fragment images.
- Normalize tag names with `trim().toLowerCase()` and keep stable tag IDs.
- Delete only managed copies and derived data; never touch an external original.
- Use focused contract and domain tests rather than broad UI test duplication.

---

### Task 1: Versioned Fragment and Catalogue Contracts

**Files:**
- Create: `packages/contracts/src/catalogue.ts`
- Modify: `packages/contracts/src/project.ts`
- Modify: `packages/contracts/src/index.ts`
- Test: `packages/contracts/test/project.test.ts`
- Test: `packages/contracts/test/catalogue.test.ts`

**Interfaces:**
- Produces `CatalogueMetadata`, `FragmentCatalogue`, `FragmentSummary`, `FragmentMutation`, `DeletedFragment`, and matching Zod schemas.
- Produces project schema version 3 with `Segment.title: string | null` and `Segment.tagIds: string[]`.

- [ ] Add failing migration, normalization, catalogue-response, and mutation-contract tests.
- [ ] Run `pnpm --filter @cut-on-eight/contracts test` and confirm the new tests fail.
- [ ] Implement schema-v2 migration to schema v3, trimmed nullable titles, unique tag IDs, lowercase catalogue tags, diagnostics, and up-to-five sprite crop references.
- [ ] Export every new schema and inferred type from `packages/contracts/src/index.ts`.
- [ ] Run `pnpm --filter @cut-on-eight/contracts test` and `pnpm --filter @cut-on-eight/contracts check`; expect both to pass.

### Task 2: Catalogue Metadata, Aggregation, and Fragment Mutations

**Files:**
- Create: `apps/server/src/storage/catalogue-metadata-repository.ts`
- Create: `apps/server/src/fragments/fragment-catalogue.ts`
- Create: `apps/server/src/http/fragment-routes.ts`
- Modify: `apps/server/src/storage/layout.ts`
- Modify: `apps/server/src/services.ts`
- Modify: `apps/server/src/app.ts`
- Test: `apps/server/test/fragment-catalogue.test.ts`
- Test: `apps/server/test/fragment-api.test.ts`
- Test: `apps/server/test/storage.test.ts`

**Interfaces:**
- `CatalogueMetadataRepository.read(): Promise<CatalogueMetadata>` and `.save(document): Promise<void>` use atomic JSON.
- `selectFragmentPreviews(segment, manifest)` maps 10/30/50/70/90 percent targets to distinct nearest samples.
- App services expose list, update, create-tag, delete, and restore operations using project and fragment IDs.

- [ ] Add focused failing tests for lowercase tag uniqueness, atomic persistence, open/closed aggregation, corrupt-sidecar diagnostics, nearest-sample selection, short-fragment deduplication, update validation, delete, restore, and conflicting restore.
- [ ] Run the new server test files and confirm expected failures.
- [ ] Add `catalogueMetadataFile` to `StorageLayout` and implement the atomic metadata repository.
- [ ] Implement pure preview selection and catalogue aggregation without opening source videos.
- [ ] Implement serialized mutation methods that validate source bounds and maximum overlap depth before saving.
- [ ] Register `GET /api/fragments`, `PUT /api/projects/:projectId/fragments/:fragmentId`, `POST /api/tags`, `DELETE /api/projects/:projectId/fragments/:fragmentId`, and `POST /api/projects/:projectId/fragments/:fragmentId/restore`.
- [ ] Run `pnpm --filter @cut-on-eight/server test` and `pnpm --filter @cut-on-eight/server check`; expect both to pass.

### Task 3: Crash-Safe Managed Video Deletion

**Files:**
- Create: `apps/server/src/storage/project-deletion.ts`
- Modify: `apps/server/src/storage/layout.ts`
- Modify: `apps/server/src/jobs/job-queue.ts`
- Modify: `apps/server/src/services.ts`
- Modify: `apps/server/src/http/project-routes.ts`
- Test: `apps/server/test/project-deletion.test.ts`
- Test: `apps/server/test/job-queue.test.ts`

**Interfaces:**
- `JobQueue.stopProject(projectId): Promise<void>` prevents dispatch and waits for active project work to stop before deletion proceeds.
- `ProjectDeletion.recover(library): Promise<void>` resolves tombstones before normal job recovery.
- `DELETE /api/projects/:id` returns the updated `WorkspaceSnapshot` and is idempotent for an already-removed project.

- [ ] Add failing tests for confirmation-independent server deletion, queued/running job coordination, tombstone recovery, retry, workspace active-project fallback, and preservation of the external original.
- [ ] Add project blocking to the queue; abort active thumbnail work and prevent blocked projects from being dispatched or publishing project files.
- [ ] Implement same-root tombstone rename, atomic library/workspace removal, rollback on catalogue failure, and asynchronous tombstone cleanup.
- [ ] Run deletion recovery before queue recovery in `ManagedWorkspaceServices.recover()`.
- [ ] Run the affected server tests and then the full server suite; expect all to pass.

### Task 4: Shared Fragment Editor and Catalogue State

**Files:**
- Create: `apps/web/src/components/FragmentEditor.svelte`
- Create: `apps/web/src/lib/fragment-catalogue.ts`
- Modify: `apps/web/src/components/BoundaryEditor.svelte`
- Modify: `apps/web/src/components/SegmentList.svelte`
- Modify: `apps/web/src/components/VideoEditor.svelte`
- Modify: `apps/web/src/lib/api.ts`
- Test: `apps/web/src/lib/fragment-catalogue.test.ts`

**Interfaces:**
- `FragmentEditor` accepts a `Segment`, tag definitions, timing callbacks, metadata callbacks, and export callback; it never starts playback.
- Catalogue helpers implement case-insensitive title/video filtering and all-selected-tags matching.

- [ ] Add failing pure tests for fallback labels, filters, normalized tag input, and immutable optimistic updates.
- [ ] Extend the API client with validated fragment and tag operations.
- [ ] Build a shared Svelte 5 fragment editor around the existing boundary controls, title input, tag chips/autocomplete, and export checkbox.
- [ ] Replace the Editor-only boundary/export controls with the shared editor while preserving video focus after segment creation.
- [ ] Run the web unit tests and Svelte checks; expect both to pass.

### Task 5: Fragments View, Five-Frame Cards, and Shared Player

**Files:**
- Create: `apps/web/src/components/FragmentPreviewStrip.svelte`
- Create: `apps/web/src/components/FragmentPlayer.svelte`
- Create: `apps/web/src/components/FragmentsPanel.svelte`
- Modify: `apps/web/src/components/AppBar.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app.css`
- Modify: `apps/web/src/lib/thumbnail-renderer.ts`
- Test: `apps/web/src/lib/thumbnail-renderer.test.ts`
- Test: `apps/web/src/lib/playback-controller.test.ts`

**Interfaces:**
- One `FragmentPlayer` owns the only catalogue `<video>` and loops `[startSeconds,endSeconds]`; modes are `floating`, `collapsed`, and `expanded`.
- `FragmentPreviewStrip` renders server-provided sprite crops and activates loading only while visible.

- [ ] Add failing tests for shared sprite-page cache behavior and exact fragment loop decisions.
- [ ] Add Editor/Library/Fragments navigation and load the aggregate catalogue only for the Fragments section.
- [ ] Implement responsive cards with fallback title, source/timing, lowercase tags, five readable crops, Play/Edit/Delete, and thumbnail placeholders.
- [ ] Implement text, video, and all-tags filters and the floating/collapsed/expanded shared player.
- [ ] Run the Svelte autofixer for every changed `.svelte` file until it reports no issues or suggestions.
- [ ] Run web tests and Svelte checks; expect both to pass.

### Task 6: Delete/Undo UX, Integration, and Verification

**Files:**
- Create: `apps/web/src/components/ConfirmDialog.svelte`
- Create: `apps/web/src/components/UndoToast.svelte`
- Modify: `apps/web/src/components/FragmentsPanel.svelte`
- Modify: `apps/web/src/components/LibraryPanel.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app.css`
- Modify: `plans/phase-03-fragment-library/design.md`

**Interfaces:**
- Fragment delete immediately removes the card and exposes one short-lived full-snapshot restore action.
- Video delete requires a named confirmation and only updates the SPA after the authoritative response.

- [ ] Add fragment Delete/Undo behavior with stable failure messages for expired, missing, or overlap-conflicting restores.
- [ ] Add the Library confirmation dialog describing deletion of managed source, fragments, thumbnails, and jobs; cancellation is side-effect free.
- [ ] Run the Svelte autofixer on all changed components.
- [ ] Run `pnpm test`, `pnpm check`, `pnpm build`, and `git diff --check`; expect all to pass.
- [ ] Browser-smoke navigation, five-frame cards, filters, inline loop, player modes, shared editing, lowercase tag creation, fragment Delete/Undo, video cancel/delete, and thumbnail fallback using disposable data only.
- [ ] Mark the Phase 3 design status complete only after the automated and browser checks pass.
