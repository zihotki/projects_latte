# Media Workbench Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve full-video playback while marking fragments and make the focused keyboard target explicit around the video and thumbnail timeline.

**Architecture:** Segment creation preserves the current selection instead of selecting the new fragment. `VideoEditor.svelte` owns a focusable media workbench and routes media keys only from that subtree while retaining the global save shortcut; CSS supplies an outline plus a compact keyboard-active label.

**Tech Stack:** TypeScript 5.9, Svelte 5 runes, Vitest 4, CSS.

## Global Constraints

- Keep changes inside `projectslatte/cut_on_eight` and preserve both `AGENTS.md` files exactly.
- Keep media side effects in `VideoEditor.svelte` and reuse the existing playback controller.
- Do not change persisted schemas, backend contracts, or dependencies.
- Do not intercept text entry or native button/form activation.
- Creating a fragment during full-video playback must not select it, seek, pause, or change playback scope.

---

### Task 1: Preserve playback scope during fragment creation

**Files:**

- Modify: `apps/web/src/lib/segments.ts`
- Test: `apps/web/src/lib/segments.test.ts`

**Interfaces:**

- Consumes: `createSegment<T extends SegmentState>(state, startSeconds, endSeconds, durationSeconds, createId)`.
- Produces: the same result type, with successful creation preserving `state.selectedSegmentId`.

- [x] **Step 1: Change the segment test to require selection preservation**

  Rename the creation test to `creates segments in creation order without changing playback selection`. Assert a null selection remains null, then add a case whose existing selected segment remains selected after another valid fragment is created.

- [x] **Step 2: Run the focused test and confirm the old selection behavior fails**

  ```bash
  node_modules/.bin/vitest run apps/web/src/lib/segments.test.ts
  ```

  Expected: the creation selection assertions fail because `createSegment` currently selects the new fragment.

- [x] **Step 3: Preserve the incoming selection**

  Return the appended segment list without assigning `validated.segment.id`:

  ```ts
  state: {
    ...state,
    segments: [...state.segments, validated.segment],
    selectedSegmentId: state.selectedSegmentId,
  }
  ```

- [x] **Step 4: Run the focused test**

  ```bash
  node_modules/.bin/vitest run apps/web/src/lib/segments.test.ts
  ```

  Expected: all segment-operation tests pass.

### Task 2: Add the focused media workbench

**Files:**

- Modify: `apps/web/src/components/VideoEditor.svelte`
- Modify: `apps/web/src/app.css`

**Interfaces:**

- Consumes: existing `handleKeyboard`, `togglePlayback`, playback decisions, and `handleVideoClick`.
- Produces: a `tabindex="0"` media region that owns media shortcuts and visibly communicates `:focus-within`; the window listener retains only Cmd/Ctrl+S.

- [x] **Step 1: Bind and focus the workbench from video interaction**

  Add `let workbench = $state<HTMLElement>();`, bind it to `.video-workbench`, and call:

  ```ts
  workbench?.focus({ preventScroll: true });
  ```

  at the start of `handleVideoClick`. This keeps video clicks on the keyboard surface before optionally clearing fragment selection.

- [x] **Step 2: Scope keyboard routing to the workbench**

  Replace the unconditional media-wide `<svelte:window onkeydown={handleKeyboard} />` listener with a window handler that always retains save but routes media commands only when the active element is inside the focusable workbench. In `handleKeyboard`, ignore all media keys from inputs, textareas, selects, and editable content. Preserve native Space/Enter activation on buttons, but allow arrow commands from focused boundary buttons to reach the existing boundary controller. The timeline slider and workbench itself forward the complete media command set.

- [x] **Step 3: Stop selecting newly created fragments in component playback state**

  Remove `createdSegment` and the `selectPlaybackSegment(...)` call from the `O` branch. Successful creation only updates the project, clears the pending in-point, optionally applies the existing pause-after-creation setting, and leaves `playbackState` unchanged.

- [x] **Step 4: Add a restrained visual focus indicator**

  Add an `aria-hidden="true"` `Keyboard active` label to the transport summary. Show it only under `.video-workbench:focus-within`, and give the workbench a two-pixel outline with offset under `:focus-visible`/`:focus-within`. Keep the label compact and do not overlay the video or timeline.

- [x] **Step 5: Run focused and component validation**

  ```bash
  node_modules/.bin/vitest run apps/web/src/lib/segments.test.ts apps/web/src/lib/playback-controller.test.ts apps/web/src/lib/trim-controller.test.ts
  apps/web/node_modules/.bin/svelte-check --tsconfig apps/web/tsconfig.json --fail-on-warnings
  node_modules/.bin/eslint "apps/web/src/**/*.ts"
  node_modules/.bin/prettier --check apps/web/src/components/VideoEditor.svelte apps/web/src/app.css apps/web/src/lib/segments.ts apps/web/src/lib/segments.test.ts
  git diff --check
  ```

  Expected: focused tests pass, Svelte reports zero errors and warnings, and all static checks pass.

- [x] **Step 6: Browser smoke and commit**

  Verify that the workbench indicator appears on keyboard focus; full-video playback continues after `I`/`O`; the new fragment stays unselected; Space and seek keys work from the workbench/timeline; clicking a fragment still selects and seeks without autoplay; and keys outside the workbench do not control video.

  ```bash
  git add apps/web/src plans/phase-02-precision-editing/implementation-02-media-workbench-focus.md
  git commit -m "fix: keep media focus while marking segments"
  ```
