# Phase 2: Precision Editing

**Status:** Approved design, pending review of this written version

**Date:** 2026-07-21

**Product:** Cut on Eight

## Purpose

Phase 2 turns the rough timestamp ranges created in Phase 1 into precisely reviewable and adjustable dance clips. It adds asynchronous thumbnail generation, an efficient zoomable timeline, drag and keyboard boundary editing, contextual preview, exact-range looping, chronological navigation, and duration guidance.

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
- Versioned thumbnail manifests and bounded sprite pages.
- Hybrid Canvas and DOM/SVG timeline rendering.
- Timeline zoom anchored at the pointer or playhead.
- Horizontal scrolling and fit-source reset.
- Two visual segment rows.
- Maximum overlap depth of two segments.
- Draggable start and end handles.
- Keyboard playhead and boundary nudging.
- Reliable-frame-rate and approximate-frame-rate behavior.
- One-shot contextual preview.
- Exact selected-range looping.
- Previous and next segment navigation.
- Three-to-eight-second duration guidance.
- Per-project persisted timeline viewport.
- Focused automated and manual verification.

### Deferred

- Zoom-specific or frame-by-frame thumbnail generation.
- Moving a complete segment as one block.
- Manual segment reordering.
- Title, tags, and notes editing.
- Export and output progress.
- Exact variable-frame-rate frame indexing.
- Waveforms, audio editing, transitions, filters, and overlays.

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

Canvas drawing, DOM/SVG positioning, pointer hit-testing, dragging, seeking, and tests must use this model. No rendering layer may maintain an independent conversion formula.

### Hybrid rendering

The timeline is one semantic range-selection component with two rendering layers:

- Canvas draws thumbnail sprite cells efficiently.
- DOM/SVG draws the playhead, pending in-point, segment ranges, two visual rows, handles, selection, warnings, and live drag feedback.

The interactive layer remains keyboard-focusable and exposes appropriate accessible names and values. Canvas is decorative and does not own interaction state.

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

The manifest identifies:

- Schema version.
- Generator version.
- Source fingerprint.
- Source duration used for generation.
- Thumbnail dimensions.
- Sprite pages.
- Timestamp and sprite rectangle for every sample.

Thumbnail data is disposable. A missing, stale, corrupt, or incompatible set is removed and regenerated without changing the project sidecar.

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

The selected segment receives the strongest visual treatment and its handles render above neighbouring ranges without changing the semantic ordering.

The overlap constraint applies equally to:

- New segment creation.
- Start-boundary dragging.
- End-boundary dragging.
- Keyboard boundary nudging.
- Future programmatic project migrations or imports.

An operation that would create a third simultaneous segment is rejected with an inline explanation. Existing persisted data that violates the constraint loads in a visible validation-error state and is never silently rewritten.

## Boundary Dragging

Selecting a segment reveals independent start and end handles.

During a drag:

1. Pointer capture keeps the interaction stable outside the handle bounds.
2. Pointer position is converted through `TimeScale`.
3. A temporary boundary updates continuously.
4. Range and overlap validation runs against the temporary value.
5. The video can seek for immediate visual feedback at a throttled rate.
6. Pointer release commits one project mutation and triggers autosave.

The saved project is not rewritten for every pointer movement. Losing pointer capture or pressing `Esc` cancels the uncommitted drag.

Boundaries must remain within the source and satisfy `start < end`. A handle stops at the nearest valid timestamp when further movement would violate source bounds, segment order, or the overlap-depth rule. The reason is shown inline while constrained.

Dragging the body of a segment to move both boundaries together is deferred.

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

Keyboard commands are:

| Key | Action |
| --- | --- |
| `,` | Move playhead backward one frame interval |
| `.` | Move playhead forward one frame interval |
| `[` | Move selected segment start earlier |
| `]` | Move selected segment start later |
| `{` | Move selected segment end earlier |
| `}` | Move selected segment end later |
| `↑` | Select previous chronological segment |
| `↓` | Select next chronological segment |

Playhead movement clamps to the source. Boundary nudges use the same range and overlap validation as dragging and commit immediately to project state.

Editor shortcuts remain inactive while text-entry controls have focus, preserving compatibility with later metadata fields.

## Preview and Looping

### Contextual preview

`Enter` plays the selected segment once with fixed context:

```text
preview start = max(0, segment start - 1 second)
preview end   = min(source duration, segment end + 1 second)
```

Playback stops at the preview end. The segment itself stays visibly emphasized so the user can judge both transitions.

### Exact loop

`L` toggles looping of the exact selected range without context. The playback controller seeks to the segment start whenever current time reaches or passes the end. Changing selection while loop mode is active moves the loop to the newly selected segment. Explicit pause stops playback without disabling the loop preference.

Context preview and loop playback are mutually exclusive active playback modes. Starting one replaces the other cleanly.

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
- `trim-controller`: drag and keyboard boundary mutations.
- `playback-controller`: normal, context-preview, and loop modes.
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

Thumbnail manifests are not embedded in the sidecar. Their compatibility is determined independently from the source fingerprint and generator version.

Existing Phase 1 projects migrate forward without changing segment timestamps.

## Failure Handling

Required Phase 2 behavior includes:

- Thumbnail failure leaves the timeline usable with a neutral background and retry action.
- A corrupt or incompatible manifest is quarantined or removed and regenerated.
- Partial sprite generation is never presented as complete.
- One project's thumbnail failure does not affect other projects.
- Losing pointer capture cancels the unfinished drag.
- Invalid drag or nudge values never mutate saved state.
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
- Drag feedback does not write sidecars until commit.
- Segment layout is recalculated from source data without manual ordering state.
- Switching open projects does not regenerate valid thumbnail data.

## Verification Strategy

Automated verification remains focused:

- `TimeScale` timestamp/pixel round-trip tests.
- Zoom-anchor and viewport-clamping tests.
- Deterministic two-row allocation tests.
- Triple-overlap rejection for create, drag, and nudge.
- Drag commit and cancellation tests.
- Reliable and fallback nudge-interval tests.
- Context-preview clamping tests at both source ends.
- Exact-loop boundary and selection-change tests.
- Thumbnail-manifest compatibility tests.
- Thumbnail-worker tests using a fake FFmpeg process adapter.
- Optional real-FFmpeg integration test using a tiny generated fixture.
- Browser smoke test for zoom, scrolling, drag, nudge, preview, loop, and project switching.
- Svelte check and official Svelte autofixer for changed components.

Manual macOS verification covers trackpad behavior, handle usability, video seeking, contextual preview, looping, and asynchronous thumbnail appearance.

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
10. Start and end handles adjust boundaries and commit one saved mutation per drag.
11. Cancelled or interrupted drags do not alter saved state.
12. Keyboard commands move the playhead and both boundaries by the configured nudge interval.
13. Approximate stepping is shown for unreliable frame rates.
14. `Enter` plays one second of context around the selected segment, clamped to the source.
15. `L` loops the exact selected range and follows selection changes.
16. Previous and next navigation follows chronological segment order.
17. Duration warnings appear below three seconds and above eight seconds without blocking edits.
18. A user can refine all rough segments without another editor.
19. Automated checks pass and the precision workflow is manually verified on macOS.

## References

- [Phase 1 design](../phase-01-foundation-and-marking/design.md)
- [Svelte effects and Canvas integration](https://svelte.dev/docs/svelte/$effect)
- [Svelte AI skills and autofixer](https://svelte.dev/docs/ai/skills)
