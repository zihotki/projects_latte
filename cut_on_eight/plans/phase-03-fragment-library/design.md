# Phase 3: Fragment Library and Metadata

**Status:** Approved

**Date:** 2026-07-22

**Product:** Cut on Eight

## Purpose

Phase 3 adds a cross-video fragment catalogue without moving authority away from the portable JSON project files. Users can browse every fragment, preview it inline, refine timing and metadata, organize it with reusable tags, undo fragment deletion, and permanently remove managed videos through an explicit safe confirmation flow.

## Scope

### Included

- A standalone **Fragments** top-level section beside Editor and Library.
- Aggregated fragment browsing across open and closed managed videos.
- A floating side preview player with collapse and expanded overlay modes.
- Five-frame visual preview strips for every fragment.
- Shared timing, title, tag, and export editing in Editor and Fragments.
- A root-level versioned tag registry with lowercase unique names.
- Immediate fragment deletion with a short-lived Undo action.
- Confirmed permanent deletion of a managed video and its derived data.
- Text, video, and tag filtering.
- Crash-safe project-folder deletion and startup cleanup.

### Deferred

- SQLite or another database.
- Persisted duplicate fragment indexes.
- Tag rename, merge, color, and administration screens.
- Automatic removal of globally registered tags that are no longer assigned.
- Fragment export and catalogue search beyond the included filters.
- Replacing the existing overview thumbnail generation policy.

## Information Architecture

The top-level navigation contains **Editor**, **Library**, and **Fragments**. Library remains responsible for managed videos: import, reopen, inspection state, and deletion. Fragments is a separate cross-video catalogue optimized for browsing and previewing clips. Opening Fragments does not implicitly open every source project in the Editor workspace.

Fragments defaults to video name followed by chronological fragment order. Users can filter by free text, source video, and one or more tags. Free text matching is case-insensitive across fragment title and source video display name. A fragment must contain every selected tag. Filter state is a browser preference and is not project content.

## Authoritative Data Model

Fragments remain authoritative inside each video's versioned project sidecar. The segment schema gains:

```ts
type Segment = {
  id: string;
  startSeconds: number;
  endSeconds: number;
  exportSelected: boolean;
  title: string | null;
  tagIds: string[];
};
```

The migration preserves all existing timing, export, selection, and editor state while assigning `title: null` and `tagIds: []` to old fragments. Titles are trimmed; an empty title is stored as `null`. Tag IDs inside a fragment are unique.

The backend builds the fragment catalogue from managed project sidecars when requested. It does not persist a second fragment index. This avoids coordinated writes and keeps future database migration straightforward.

## Root Catalogue Metadata

Global catalogue metadata is stored under the managed data root:

```text
~/cut-on-eight_data/_system/catalogue-metadata.json
```

Its initial version contains tag definitions:

```ts
type CatalogueMetadataV1 = {
  schemaVersion: 1;
  tags: Array<{
    id: string;
    name: string;
  }>;
};
```

Tag names are trimmed and normalized to lowercase before validation. Names are non-empty and unique after normalization. Tags use stable IDs so later display metadata such as color or description can be added without rewriting every fragment. Unused tags remain registered until a later tag-management feature exists.

Tag creation and catalogue updates use the existing atomic JSON persistence approach. Project sidecar updates and tag creation are serialized through backend mutation boundaries so a fragment never references a tag that was not durably registered.

## Fragment Catalogue Cards

Each fragment card contains:

- Its optional title, falling back to `Fragment N · <video name>`.
- Source video name and start/end/duration values.
- Lowercase tag chips.
- Five clearly visible 16:9 preview frames.
- Play, Edit, and Delete actions.

The five target times are 10%, 30%, 50%, 70%, and 90% through the fragment. Each target resolves to the nearest available sample in the compatible project thumbnail manifest. Duplicate samples are removed only when a short fragment cannot provide five distinct frames; the layout keeps the remaining images large rather than repeating identical frames.

Preview references are derived by the backend and point to crop rectangles in existing immutable WebP sprite pages. No per-fragment image files or duplicate manifests are created. The frontend renders only visible card previews and shares the existing sprite-page image cache. On narrow layouts, the preview strip scrolls horizontally instead of shrinking frames until they are unreadable.

If compatible thumbnails are missing, generating, or failed, the card remains usable and shows a compact placeholder plus the existing retry state where appropriate.

## Inline Playback

Fragments uses one shared floating side player instead of creating one video element per card. Playing a card loads its managed source, selects the fragment range, loops that exact range, and visibly marks the active card. Switching cards reuses the same player.

The player has three states:

- **Floating:** a compact side player that stays available while the catalogue scrolls.
- **Collapsed:** an unobtrusive control retaining the current fragment identity and play state.
- **Expanded:** a larger overlay for closer inspection, without leaving Fragments.

Closing or navigating away stops playback and releases media sampling. Playback failures affect only the player and do not block metadata editing.

## Shared Fragment Editor

A shared fragment editor is used below the Editor timeline and from an expanded fragment card. It combines:

- Existing Start and End click/keyboard timing controls.
- Optional title editing.
- Tag autocomplete and removable assignment chips.
- Creation of a normalized lowercase tag by pressing Enter.
- Existing export selection.

Editor changes use the current autosave and explicit-save behavior. A closed video's fragment can be edited from Fragments through a backend mutation endpoint without adding the project to the open Editor workspace. Successful edits update the visible catalogue response immediately.

Timing changes continue to enforce source bounds and the maximum-two-overlaps rule. Metadata changes do not affect playback scope. Selecting Edit does not start playback.

## Deletion Semantics

### Fragment deletion

Fragment deletion is immediate and has no confirmation dialog. The UI displays a short-lived Undo toast containing the complete deleted fragment snapshot and its original position. Undo restores the same ID, timing, title, tag assignments, and export state.

Undo revalidates source bounds and overlap depth against the current project. If intervening edits make restoration invalid, the fragment remains deleted and the toast explains the active constraint. Refreshing or navigating away ends the undo opportunity; already saved deletion remains authoritative.

### Video deletion

Video deletion is available from Library and always requires a confirmation dialog. The dialog names the video and explicitly states that the managed source, fragments, thumbnails, and jobs will be permanently removed. External originals are never touched.

Deletion runs under the workspace/library mutation boundary:

1. Stop or detach work associated with the project.
2. Atomically rename the managed project directory to a deletion tombstone inside the managed root.
3. Atomically remove the project from the open workspace and library documents.
4. Delete the tombstone asynchronously.
5. Complete or recover interrupted tombstones during startup.

If the safe rename fails, system documents remain unchanged. If a later catalogue write fails, recovery restores or finishes the tombstone consistently before exposing the workspace. The UI removes the video only after the backend confirms the authoritative deletion transition.

## Backend Interfaces

Phase 3 adds task-specific endpoints rather than exposing filesystem paths:

- List aggregated fragment summaries with source display data, tag definitions, and derived five-frame preview references.
- Update one fragment's timing, title, tags, and export selection using its project and fragment IDs.
- Create or return an existing normalized tag.
- Delete and restore one fragment.
- Permanently delete one managed project after explicit browser confirmation.

All request and response payloads use shared Zod contracts. Project and sprite routes keep the existing managed-root containment checks. Delete endpoints are idempotent where practical so a lost response can be retried safely.

## Failure Handling

- A corrupt project sidecar is omitted from the aggregate result with a visible per-video diagnostic; other fragments remain available.
- Missing thumbnails show placeholders and never block metadata or playback.
- Tag creation failure leaves fragment assignments unchanged.
- Invalid timing edits preserve the saved fragment and return the existing stable constraint code and message.
- A fragment deleted by another action returns a stable not-found response and refreshes the catalogue.
- Video deletion failure keeps or restores the video in Library and reports the failure without touching the external source.
- Running background work cannot recreate files inside a project after its deletion transition begins.

## Performance

- Catalogue aggregation reads managed sidecars but does not open source videos.
- Responses include only five preview references per fragment, not complete thumbnail manifests.
- Card preview rendering is visibility-driven and shares immutable sprite pages across fragments.
- Only the floating player owns an active video element.
- The catalogue remains responsive for at least 100 managed videos and 5,000 fragments.

## Verification

Automated coverage includes:

- Project migration and title/tag validation.
- Lowercase tag normalization and uniqueness.
- Atomic catalogue metadata persistence.
- Aggregation across open and closed videos.
- Five-target selection, nearest-sample mapping, and short-fragment deduplication.
- Thumbnail fallback and shared-page caching.
- Shared fragment editor updates and overlap rejection.
- Exact inline looping and player lifecycle.
- Fragment deletion, valid Undo, and rejected Undo after conflicting edits.
- Confirmed video deletion, active-job coordination, tombstone recovery, and idempotent retry.

Browser acceptance covers navigation, filters, five-frame visibility, floating/collapsed/expanded playback, title editing, lowercase tag creation and assignment, shared timing controls, fragment Delete/Undo, video confirmation/cancellation/deletion, thumbnail fallback, and restoration after backend restart.

## Acceptance Criteria

Phase 3 is complete when:

1. Fragments is a standalone top-level catalogue across every managed video.
2. Each fragment card shows up to five distinct, clearly visible frames from different points in its range without creating per-fragment image files.
3. One floating side player loops the active fragment and supports collapsed and expanded modes.
4. Users can edit fragment timing, optional title, lowercase tags, and export selection through the shared editor.
5. New tag definitions are durable, unique, lowercase, and stored in the root catalogue metadata document.
6. Fragment deletion is immediate and offers a valid short-lived Undo path without confirmation.
7. Video deletion requires explicit confirmation and permanently removes only the managed copy and its application data.
8. Interrupted video deletion and running background work cannot leave a visible half-deleted project.
9. Missing thumbnails or one corrupt project do not block the rest of the catalogue.
10. Automated checks pass and the full catalogue workflow is browser-smoked with representative videos.

## References

- [Phase 1 design](../phase-01-foundation-and-marking/design.md)
- [Phase 2 precision editing design](../phase-02-precision-editing/design.md)
- [Media workbench focus design](../phase-02-precision-editing/design-02-media-workbench-focus.md)
