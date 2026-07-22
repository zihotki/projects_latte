# Editor Keyboard Context Repair

**Status:** Complete

**Date:** 2026-07-22

## Problem

The editor currently derives keyboard ownership from whether DOM focus is inside the media workbench. The segment list is outside that container and its selection control is a native button. Clicking a segment therefore selects segment playback scope but leaves keyboard focus on a button that intercepts Space. Clicking the video moves DOM focus into the media workbench while preserving segment playback scope, producing a visible focus state that disagrees with the command state.

## Intended Behavior

Keyboard ownership is an explicit editor state rather than an inference from layout:

- `source`: Space toggles full-video playback; Left and Right seek the source.
- `segment`: Space toggles the selected segment loop; Left and Right seek within its bounds; Up and Down select adjacent segments.
- `boundary`: Left and Right adjust the focused start or end boundary.
- `native-input`: text fields, checkboxes, selects, content-editable elements, and their native actions retain browser behavior.

Clicking a segment selects it, changes keyboard ownership to `segment`, and moves visible DOM focus to that segment's focus surface. Clicking the video or empty timeline changes ownership to `source`, clears segment selection, and focuses the media surface. Focusing a timing boundary changes ownership to `boundary`. Entering a native input temporarily suspends editor shortcuts without changing the underlying source or segment playback scope.

## Design

`VideoEditor` owns the keyboard context because it already coordinates selection, playback scope, boundary focus, and commands. It routes window key events only when focus belongs to this editor and the target is not a native input. Playback scope and keyboard context transition together through focused functions rather than through ad hoc DOM containment checks.

`SegmentList` exposes a focusable segment surface and reports both selection and focus intent. Selecting a segment focuses that surface after updating playback scope. The selected card receives the keyboard-focus indicator; the video container must not appear focused while segment context owns the keyboard.

The timeline keeps its existing selection behavior. Clicking an existing segment enters segment context. Clicking empty timeline space seeks in source context and clears selection. Native buttons remain native only when their action is distinct from the editor playback surface; the segment selection surface itself delegates Space to the editor.

## State Transitions

| Event | Resulting context | Playback scope | Visible focus |
| --- | --- | --- | --- |
| Click segment | `segment` | Selected segment | Segment card |
| Space on selected segment | `segment` | Selected segment loop | Segment card |
| Up or Down | `segment` | Adjacent segment | Adjacent card |
| Click video | `source` | Full video | Media surface |
| Click empty timeline | `source` | Full video at seek point | Media surface |
| Focus boundary | `boundary` | Selected segment | Boundary control |
| Focus native editor input | `native-input` while focused | Unchanged | Native control |
| Escape from boundary | `segment` | Selected segment | Segment card |
| Escape from segment | `source` | Full video | Media surface |

## Error and Accessibility Behavior

Playback failures remain reported through the existing playback error state. Focus changes use `preventScroll` except when selecting an adjacent off-screen segment, which may scroll into view. Focus indicators use `:focus-visible` or an equivalent explicit class and remain distinct from selection styling. The segment focus surface has an accessible label describing the segment and its keyboard playback role.

## Verification

Focused controller tests cover context transitions independently of Svelte and media side effects. Component checks cover native-input exclusion and focus routing. Browser verification covers clicking a segment, toggling its loop with Space without visual focus moving to the video, changing segments with Up and Down, returning to full-video context by clicking the video or empty timeline, and retaining native behavior in title and tag inputs.
