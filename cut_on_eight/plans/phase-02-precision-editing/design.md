# Phase 2: Precision Editing

**Status:** Implementation complete; manual macOS acceptance pending

**Date:** 2026-07-21

**Product:** Cut on Eight

## Purpose

Phase 2 turns the rough timestamp ranges created in Phase 1 into precisely reviewable and adjustable dance clips. It adds an editor-first workspace, a standalone Library view, asynchronous thumbnail generation, an efficient zoomable timeline, click-and-keyboard boundary editing, contextual preview, selection-scoped looping, chronological navigation, and duration guidance.

At the end of this phase, a user should be able to refine every marked movement without opening another video editor. Export, metadata entry, and catalogue search remain later work.

## Dependency on Phase 1

Phase 2 builds on the contracts defined in `plans/phase-01-foundation-and-marking/design.md`:

- Svelte 5 client-only SPA and separate local Fastify backend.
- Shared Zod contracts.
- Managed per-video folders under `~/cut-on-eight_data`.
- Multiple open projects with one active editor.
- Versioned project sidecars and atomic persistence.
- HTTP byte-range source streaming.
- Durable file-backed background jobs and Server-Sent Events.
- FFprobe source inspection.
- Basic timeline, segment list, and rough `I`/`O` marking.

Phase 2 extends these boundaries rather than replacing them.

## Scope

### Included

- Backend-generated adaptive overview thumbnails.
- Compact grouping policy for thumbnails and other immutable derived assets.
- Editor-first application layout with standalone Editor and Library views.
- Collapsible segment panel and minimized operational status.
- One central, context-sensitive shortcut help popover.
- Versioned thumbnail manifests and bounded sprite pages.
- Hybrid Canvas and DOM/SVG timeline rendering.
- Timeline zoom anchored at the pointer or playhead.
- Horizontal scrolling and fit-source reset.
- Two visual segment rows.
- Maximum overlap depth of two segments.
- Click-selectable start and end controls with keyboard and button nudging.
- Normal and fast keyboard seeking outside boundary-edit mode.
- Reliable-frame-rate and approximate-frame-rate behavior.
- One-shot contextual preview.
- Exact selected-range looping.
- Previous and next segment navigation.
- Three-to-eight-second duration guidance.
- Per-project persisted timeline viewport.
- Focused automated and manual verification.

### Deferred

- Zoom-specific or frame-by-frame thumbnail generation.
- Pointer-dragging segment boundaries.
- Moving a complete segment as one block.
- Manual segment reordering.
- Title, tags, and notes editing.
- Export and output progress.
- Exact variable-frame-rate frame indexing.
- Waveforms, audio editing, transitions, filters, and overlays.

## Application Layout

The application has two top-level views:

- **Editor** contains the open-project strip, active video, timeline, and segment panel.
- **Library** is a standalone view for importing, reopening, and inspecting managed projects.

The Editor is the initial view when a project is active and becomes active after an import or library reopen. Explicitly opening Library keeps Library active until the user returns to Editor. Video receives the largest share of the Editor viewport, followed by the timeline and then the segment panel. The segment panel can be collapsed without affecting selection or playback, and the preference is stored locally in the browser.

The top navigation contains only Editor, Library, one compact operational-status indicator, and a `?` help button. Detailed backend, FFprobe, and job state appears inside a small status popover or only when action is required. Operational chrome must not compete visually with the video or segments.

The `?` button is the single help location. Its unobtrusive popover shows the controls relevant to the current mode: full-video playback, selected-segment looping, or focused-boundary editing. The interface still labels the current playback scope and focused boundary near the timeline so state is never hidden exclusively inside help.

## Timeline Architecture

### Shared coordinate model

All timeline behavior depends on one framework-independent `TimeScale` model. It owns:

- Source duration.
- Viewport width.
- Zoom level.
- Horizontal offset.
- Timestamp-to-pixel conversion.
- Pixel-to-timestamp conversion.
- Bounds clamping.
- Zoom anchoring.

Canvas drawing, DOM/SVG positioning, pointer hit-testing, clicking, seeking, and tests must use this model. No rendering layer may maintain an independent conversion formula.

### Hybrid rendering

The timeline is one semantic range-selection component with two rendering layers:

- Canvas draws thumbnail sprite cells efficiently.
- DOM/SVG draws the playhead, pending in-point, segment ranges, two visual rows, selection, boundary controls, and warnings.

The interactive layer remains keyboard-focusable and exposes appropriate accessible names and values. Canvas is decorative and does not own interaction state. Clicking empty timeline space selects the main video playback scope; clicking a segment selects that segment without starting playback.

High-frequency playhead painting uses `requestAnimationFrame` and focused DOM or Canvas updates. It must not cause broad Svelte component invalidation.

### Extensibility boundary

The frontend consumes a generic versioned thumbnail-manifest interface. The timeline does not assume that only one thumbnail resolution can exist. Phase 2 supplies one bounded overview set; a later phase may add viewport-detail sets without changing project data or the timeline coordinate model.

## Thumbnail Generation

### Job flow

After a source has usable inspection metadata, the backend durably queues `generate-thumbnails` through the Phase 1 job system.

The worker:

1. Computes a bounded sampling plan from source duration.
2. Invokes FFmpeg through an isolated process adapter.
3. Generates small WebP frames.
4. Packs frames into sprite pages of safe dimensions.
5. Writes a versioned timing manifest.
6. Atomically promotes the complete generated set.
7. Publishes job completion or failure through the existing event stream.

Closing a project does not cancel thumbnail generation. Backend shutdown pauses it; queue recovery resumes it on the next start.

### Adaptive overview policy

The initial policy targets approximately one image every two seconds and caps the set at roughly 600 images. Short sources therefore receive denser coverage, while long sources remain bounded. The exact interval, maximum count, thumbnail dimensions, and sprite-page capacity are implementation configuration, not persisted product contracts.

Zoom enlarges the existing overview images. It does not enqueue denser thumbnails in Phase 2. Video preview, timestamps, and frame nudging remain the authoritative precision tools.

### Derived storage

Generated files live inside the managed project:

```text
<video-project>/thumbnails/
├── manifest.json
├── sprite-001.webp
├── sprite-002.webp
└── ...
```

Individual sampled frames exist only inside the generation staging directory. Successful promotion retains bounded WebP sprite pages and one compact manifest; it never leaves one file per thumbnail in the managed project.

The manifest identifies:

- Schema version.
- Generator version.
- Source fingerprint.
- Source duration used for generation.
- Thumbnail dimensions.
- Sprite pages.
- Timestamp and sprite rectangle for every sample.

The persisted representation remains versioned JSON for portability, browser parsing, diagnostics, and straightforward migrations, but repetitive sample data uses documented positional arrays instead of repeating object keys for every thumbnail. The HTTP response may additionally use normal compression. A binary manifest format is deferred until measured size or parsing evidence justifies its migration cost.

Thumbnail data is disposable. A missing, stale, corrupt, or incompatible set is removed and regenerated without changing the project sidecar.

The same rule applies to future immutable derived assets: group many small outputs into bounded pages or bundles with one versioned index when they share a lifecycle. Mutable project sidecars, workspace/catalogue documents, and durable job records remain separate atomic files because they are updated and recovered independently.

## Timeline Navigation

The timeline initially fits the complete source.

Supported navigation is:

- `Cmd/Ctrl + wheel` zooms around the pointer when it is over the timeline.
- Visible `+` and `−` controls zoom around the playhead.
- Trackpad or mouse scrolling moves horizontally while zoomed.
- A fit-source action returns to the full-duration view.
- Selecting a segment ensures that its boundaries are visible.

Zoom has bounded minimum and maximum values. The minimum always fits the complete source. The maximum provides useful trim precision without implying exact decoded-frame indexing.

Zoom level and horizontal offset are stored as per-project editor view state. Each open project restores its own viewport when activated, after refresh, and after backend restart.

## Overlap Model

Segments may overlap, but the maximum overlap depth is two: at no timestamp may three segments be active.

A segment may overlap both its preceding and following chronological neighbours when those overlaps occur at different times. The renderer assigns valid overlapping ranges to two visual rows. Non-overlapping segments use the primary row.

The selected segment receives the strongest visual treatment and its boundary controls render above neighbouring ranges without changing the semantic ordering.

The overlap constraint applies equally to:

- New segment creation.
- Start-boundary clicking and keyboard nudging.
- End-boundary clicking and keyboard nudging.
- Future programmatic project migrations or imports.

An operation that would create a third simultaneous segment is rejected with an inline explanation. Existing persisted data that violates the constraint loads in a visible validation-error state and is never silently rewritten.

## Boundary Editing

Selecting a segment reveals independent **Start** and **End** controls with their timestamps. Clicking one focuses that boundary; no text entry or drag handle is required.

The focused control provides compact click targets for one-frame and 0.1-second movement in both directions. The same operations are available from the arrow keys. Each valid action commits one project mutation and follows the normal autosave path.

Boundaries remain within the source and satisfy `start < end`. An adjustment stops at the nearest valid timestamp when further movement would violate source bounds, segment order, or the overlap-depth rule. A short inline reason appears beside the focused control. `Escape` clears boundary focus first; a second `Escape` clears the selected segment and returns to main-video playback scope.

## Frame and Time Nudging

FFprobe inspection classifies the source frame-rate signal as reliable or approximate.

When reliable:

```text
nudge interval = 1 / reported frame rate
```

When missing, variable, or otherwise unreliable:

```text
nudge interval = 1 / 30 second
```

The UI displays **Approximate frame stepping** whenever the fallback is active. Browser preview may not stop on the same decoded frame that a later FFmpeg export uses; timestamps remain authoritative.

Keyboard commands depend on focus:

| Context | Key | Action |
| --- | --- | --- |
| No boundary focused | `←` / `→` | Seek the current playback scope by one second |
| No boundary focused | `Shift + ←` / `Shift + →` | Seek by ten seconds |
| Start or End focused | `←` / `→` | Move the focused boundary by one frame interval |
| Start or End focused | `Shift + ←` / `Shift + →` | Move the focused boundary by 0.1 seconds |
| Segment selected | `↑` / `↓` | Select the previous or next chronological segment |
| Any editor mode | `Space` | Play or pause the current playback scope |
| Boundary or segment selected | `Escape` | Clear boundary focus, then segment selection |

Seeking clamps to the main video or selected segment range as appropriate. Boundary nudges use the shared range and overlap validation and commit immediately to project state.

Editor shortcuts remain inactive while text-entry controls have focus, preserving compatibility with later metadata fields.

## Preview and Looping

### Contextual preview

`Enter` plays the selected segment once with fixed context:

```text
preview start = max(0, segment start - 1 second)
preview end   = min(source duration, segment end + 1 second)
```

Playback stops at the preview end. The segment itself stays visibly emphasized so the user can judge both transitions.

### Playback scope and exact loop

Selecting a segment sets the playback scope to that segment and seeks to its start, but does not start playback. `Space` or the native Play control then loops the exact selected range. When playback reaches or passes the segment end, the controller seeks to its start and continues.

Clicking the video, empty timeline space, or clearing selection returns to main-video playback scope. Playback does not start automatically; `Space` or Play resumes normal source playback. Changing segment selection while playing stops playback and moves the scope to the newly selected segment so no unexpected clip begins automatically.

Context preview and loop playback are mutually exclusive active playback modes. Starting the contextual preview temporarily replaces looping; finishing or cancelling it returns to the selected-segment scope in a paused state.

### Segment navigation

Previous and next navigation follows recalculated chronological ordering. Selection seeks to the segment start and ensures the segment is visible in both the list and timeline. Navigation does not start playback automatically.

## Duration Guidance

Every segment displays its duration. Durations outside the expected three-to-eight-second range show non-blocking guidance:

- Below three seconds: short-duration warning.
- Above eight seconds: long-duration warning.

Warnings appear in the segment list and selected timeline range. They never prevent saving, previewing, further editing, or later export.

## Component and Module Boundaries

Phase 2 introduces focused units with stable public contracts:

- `timeline-geometry`: viewport state and coordinate conversion.
- `timeline-viewport`: zoom and scrolling commands.
- `segment-constraints`: range and overlap-depth validation.
- `two-row-layout`: deterministic visual-row allocation.
- `trim-controller`: focused-boundary and click/keyboard mutations.
- `playback-controller`: main-video, selected-segment loop, and context-preview modes.
- `editor-shell`: Editor/Library navigation, collapsible panels, and compact status/help popovers.
- `thumbnail-manifest`: schema and compatibility checks.
- `thumbnail-renderer`: Canvas sprite drawing only.
- `thumbnail-worker`: backend generation orchestration.

Domain modules are plain TypeScript. Svelte components compose them and render state but do not absorb their algorithms.

## Persistence Changes

The project schema gains versioned source-inspection data needed for stepping:

- Reported frame-rate numerator and denominator when present.
- Frame-rate reliability classification.
- Inspection timestamp and inspector version.

Per-project editor view state gains:

- Timeline zoom.
- Horizontal offset.

The active top-level view, collapsed segment-panel preference, and help-popover state are browser UI preferences, not project content. Only the active view and collapsed-panel preference persist locally; popovers always reopen closed.

Thumbnail manifests are not embedded in the sidecar. Their compatibility is determined independently from the source fingerprint and generator version.

Existing Phase 1 projects migrate forward without changing segment timestamps.

## Failure Handling

Required Phase 2 behavior includes:

- Thumbnail failure leaves the timeline usable with a neutral background and retry action.
- A corrupt or incompatible manifest is quarantined or removed and regenerated.
- Partial sprite generation is never presented as complete.
- One project's thumbnail failure does not affect other projects.
- Invalid click or keyboard nudge values never mutate saved state.
- Triple-overlap attempts provide a stable validation code and inline explanation.
- Event-stream disconnection falls back to a job snapshot and reconnects.
- Failed seeking exits preview or loop mode with a visible playback error.
- Approximate stepping is labeled rather than presented as frame exact.

## Performance Requirements

Phase 2 must remain responsive for at least a one-hour source and 100 segments.

- Thumbnail generation remains outside the frontend process.
- Sprite count and dimensions remain bounded.
- Only visible thumbnail cells are drawn.
- Playhead painting is scheduled with `requestAnimationFrame`.
- Boundary editing writes one mutation per click or key command.
- Segment layout is recalculated from source data without manual ordering state.
- Switching open projects does not regenerate valid thumbnail data.

## Verification Strategy

Automated verification remains focused:

- `TimeScale` timestamp/pixel round-trip tests.
- Zoom-anchor and viewport-clamping tests.
- Deterministic two-row allocation tests.
- Triple-overlap rejection for create and boundary nudge.
- Playback-scope selection and clearing tests.
- Normal and fast seek-clamping tests.
- Focused Start/End click and keyboard nudge tests.
- Reliable and fallback nudge-interval tests.
- Context-preview clamping tests at both source ends.
- Exact-loop boundary, pause, and selection-change tests.
- Thumbnail-manifest compatibility tests.
- Thumbnail-worker tests using a fake FFmpeg process adapter.
- Optional real-FFmpeg integration test using a tiny generated fixture.
- Browser smoke test for Editor/Library navigation, collapsing panels, zoom, scrolling, nudge, preview, loop, and project switching.
- Svelte check and official Svelte autofixer for changed components.

Manual macOS verification covers trackpad behavior, compact layout usability, normal and fast video seeking, click/keyboard boundary editing, contextual preview, looping, and asynchronous thumbnail appearance.

## Acceptance Criteria

Phase 2 is complete when:

1. Thumbnail generation is durably queued after source inspection.
2. Editing remains available while thumbnails generate or fail.
3. A bounded adaptive thumbnail strip appears without loading individual image elements for every frame.
4. Valid cached thumbnails survive close, reopen, refresh, and backend restart.
5. The timeline fits the complete source by default.
6. Zoom remains anchored at the pointer or playhead and supports horizontal scrolling.
7. Timeline view state remains independent for every open project.
8. Valid overlapping segments occupy at most two visual rows.
9. Creating or editing a triple overlap is rejected with a clear explanation.
10. Start and End controls adjust boundaries by click or keyboard without requiring text entry or dragging.
11. Invalid boundary adjustments do not alter saved state and explain the active constraint.
12. Arrow commands perform normal and fast seeking or adjust the focused boundary by the configured interval.
13. Approximate stepping is shown for unreliable frame rates.
14. `Enter` plays one second of context around the selected segment, clamped to the source.
15. Selecting a segment changes playback scope without starting it; Space or Play loops the exact range.
16. Previous and next navigation follows chronological segment order.
17. Duration warnings appear below three seconds and above eight seconds without blocking edits.
18. A user can refine all rough segments without another editor.
19. Library is a standalone top-level view and the Editor keeps video, timeline, and segments visually dominant.
20. One central context-sensitive help popover explains the active controls without persistent instructional clutter.
21. Automated checks pass and the precision workflow is manually verified on macOS.

## Verification Status

Implementation and automated acceptance completed on 2026-07-22. The complete suite passes with 223 tests, all static checks and production builds pass, and a real FFmpeg smoke produced a compact manifest plus one WebP sprite page without loose sampled frames. Browser automation covered the integrated Editor workflow, including project switching, selection-only scope changes, contextual preview and looping, precision nudges, zoom/fit, two-row overlap, triple-overlap rejection, durable thumbnail regeneration, and a clean console.

The following human macOS checks remain before changing the status to `Implemented`:

- Native file-picker behavior during normal import.
- Trackpad zoom and horizontal-pan feel.
- Precision and responsiveness with representative real dance videos.
- Native video Play control looping feel at exact segment boundaries.

## References

- [Phase 1 design](../phase-01-foundation-and-marking/design.md)
- [Svelte effects and Canvas integration](https://svelte.dev/docs/svelte/$effect)
- [Svelte AI skills and autofixer](https://svelte.dev/docs/ai/skills)
