# Editor Keyboard Context Repair Implementation Plan

**Status:** Complete

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep editor keyboard commands, playback scope, DOM focus, and visual focus aligned when switching between full-video, segment, boundary, and native-input interaction.

**Architecture:** A small pure controller names the effective keyboard context and decides whether an event belongs to the editor. `VideoEditor` remains the coordinator for playback and focus transitions; `SegmentList` exposes focusable segment surfaces so selecting or navigating to a segment leaves Space available for loop playback instead of native button activation.

**Tech Stack:** TypeScript 5.9, Svelte 5 runes and attachments, Vitest, existing playback and trim controllers.

## Global Constraints

- Keep all changes inside `projectslatte/cut_on_eight` and preserve both `AGENTS.md` files exactly.
- Do not change segment creation behavior: marking a new segment keeps source-video selection and focus.
- Native text inputs, checkboxes, selects, content-editable elements, and unrelated buttons retain browser keyboard behavior.
- Do not add dependencies or move layout solely to implement keyboard routing.

---

### Task 1: Explicit Keyboard Context Controller

**Files:**
- Create: `apps/web/src/lib/editor-keyboard-context.ts`
- Create: `apps/web/src/lib/editor-keyboard-context.test.ts`

**Interfaces:**
- Produces `EditorKeyboardContext`, `resolveEditorKeyboardContext(selectedSegmentId, boundaryFocus)`, and `shouldRouteEditorKeyboard(input)`.
- Consumes the existing `BoundaryFocus` type without browser or media dependencies.

- [ ] **Step 1: Add failing context and routing tests**

Cover source, selected segment, focused boundary, editor-contained focus, native input exclusion, and Space/Enter native-button activation. In particular:

```ts
expect(resolveEditorKeyboardContext(segmentId, null)).toEqual({
  kind: 'segment',
  segmentId,
});
expect(
  shouldRouteEditorKeyboard({
    focusWithinEditor: true,
    nativeButtonActivation: false,
    nativeInput: false,
  }),
).toBe(true);
```

- [ ] **Step 2: Verify the new tests fail**

Run:

```bash
node_modules/.bin/vitest run apps/web/src/lib/editor-keyboard-context.test.ts
```

Expected: failure because `editor-keyboard-context.ts` does not exist.

- [ ] **Step 3: Implement the pure controller**

Use discriminated contexts:

```ts
export type EditorKeyboardContext =
  | { readonly kind: 'source' }
  | { readonly kind: 'segment'; readonly segmentId: string }
  | {
      readonly kind: 'boundary';
      readonly segmentId: string;
      readonly edge: 'start' | 'end';
    };
```

`resolveEditorKeyboardContext` gives boundary focus precedence over segment selection. `shouldRouteEditorKeyboard` returns true only for focus inside the editor that is neither a native input nor a Space/Enter activation of an unrelated native button.

- [ ] **Step 4: Run the controller tests**

Run the focused Vitest command again; expect all new tests to pass.

### Task 2: Align Segment Focus and Command Routing

**Files:**
- Modify: `apps/web/src/components/VideoEditor.svelte`
- Modify: `apps/web/src/components/SegmentList.svelte`
- Modify: `apps/web/src/app.css`
- Test: `apps/web/src/lib/editor-keyboard-context.test.ts`

**Interfaces:**
- `VideoEditor` routes keys when focus is anywhere inside its root editor, then applies native-control exclusions through `shouldRouteEditorKeyboard`.
- `SegmentList` selection cards have `tabindex="0"`, `data-segment-id`, and an accessible playback-focus label.

- [ ] **Step 1: Add editor-root and segment-surface attachments**

Attach the outer `.video-editor` element to an `editor` reference. Keep the existing media-workbench reference for source focus. Make each segment `<li>` programmatically focusable and move focus from its selection button to the list item after selection.

- [ ] **Step 2: Centralize segment and source focus transitions**

After `selectSegment`, focus the matching `[data-segment-id]` surface with `preventScroll`, then scroll it into view. After `clearSegmentSelection`, focus the media workbench. Boundary controls and native inputs keep their own focus.

- [ ] **Step 3: Route keyboard events from the whole editor**

Replace the media-only containment condition with controller input derived from the editor root and event target. Preserve the existing Save shortcut. Space on a focused segment surface reaches `togglePlayback`; Space or Enter on unrelated buttons remains native.

- [ ] **Step 4: Align the visual indicator**

Show the blue media outline and “Keyboard active” badge only while the media workbench itself owns focus. Add a distinct focus-visible outline to the selected segment card so visual focus follows keyboard ownership.

- [ ] **Step 5: Validate Svelte and focused behavior**

Run:

```bash
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/components/VideoEditor.svelte --svelte-version 5
node_modules/.bin/svelte-mcp svelte-autofixer apps/web/src/components/SegmentList.svelte --svelte-version 5
apps/web/node_modules/.bin/svelte-check --tsconfig apps/web/tsconfig.json --fail-on-warnings
node_modules/.bin/vitest run apps/web/src/lib/editor-keyboard-context.test.ts apps/web/src/lib/playback-controller.test.ts apps/web/src/lib/segments.test.ts
```

Expected: both autofixer runs report no issues or suggestions, Svelte reports zero errors and warnings, and all focused tests pass.

### Task 3: Regression Gate and Browser Verification

**Files:**
- Modify: `plans/phase-03-fragment-library/design-02-editor-keyboard-context.md`
- Modify: `plans/phase-03-fragment-library/implementation-02-editor-keyboard-context.md`

- [ ] **Step 1: Run the full automated gate**

Run contract/server TypeScript builds, Svelte check, all Vitest tests, ESLint, Prettier, Vite production build, and `git diff --check`. All must pass.

- [ ] **Step 2: Browser-smoke the state transitions without editing data**

Verify: click an existing segment card; its card receives focus; Space starts and pauses the selected segment loop without moving focus to the video; Up and Down move selection and focus; clicking the video clears selection and returns visible focus to the media surface; title/tag inputs accept Space natively.

- [ ] **Step 3: Complete documentation and commit**

Set both design and implementation statuses to `Complete`, verify both `AGENTS.md` hashes are unchanged, stage only scoped files, and commit:

```bash
git commit -m "fix: align editor keyboard focus with playback"
```
