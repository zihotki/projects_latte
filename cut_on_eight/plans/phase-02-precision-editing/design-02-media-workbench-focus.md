# Media Workbench Focus

**Status:** Approved

**Date:** 2026-07-22

## Goal

Keep uninterrupted full-video playback while the user marks fragments, and make the destination of keyboard playback commands visually clear.

## Interaction Model

- The video, transport summary, thumbnail timeline, and precision controls form one focusable media workbench.
- The workbench has a restrained visible focus indicator when it or one of its media controls has keyboard focus.
- Clicking the video or empty timeline focuses the workbench and uses full-video playback scope.
- Creating a fragment with `O` persists it without selecting the new fragment, seeking, pausing, changing the current playback scope, or moving focus. During the intended full-video marking workflow, `selectedSegmentId` therefore remains unset and playback continues unless it was already paused.
- Clicking a fragment explicitly selects it, seeks to its start, and changes playback scope to that fragment. Its boundary controls then become available.
- Clearing the selection returns to full-video playback scope.

## Keyboard Routing

The media workbench forwards its keyboard events to the existing `VideoEditor` controller. Space, arrow keys, Shift+arrow keys, `I`, `O`, Enter, Escape, Delete, and Backspace keep their existing meanings for the active playback scope.

Keyboard commands do not intercept text entry. Focused buttons and form controls retain their native activation behavior. Application save remains available through the existing shortcut.

The window-level shortcut listener is removed or narrowed so an unfocused media workbench does not silently consume media commands. This makes the visual focus indicator truthful.

## Accessibility

- The workbench uses a semantic region with an accessible label and `tabindex="0"`.
- The visual treatment uses `:focus-visible` and `:focus-within` without relying on color alone.
- Segment selection remains distinct from keyboard focus: selected styling communicates playback scope, while the workbench outline communicates the keyboard target.
- Fragment buttons remain reachable and activatable by keyboard.

## Implementation Boundaries

- Keep browser and media side effects in `VideoEditor.svelte`.
- Reuse the existing playback, trimming, and segment domain modules.
- Do not change persisted schemas or backend contracts.
- Do not add a second keyboard-command abstraction unless tests show the component handler cannot remain focused and readable.

## Verification

- Creating a fragment while in full-video scope leaves `selectedSegmentId` unset and preserves that scope.
- Creating a fragment does not move DOM focus away from the media workbench or interrupt playback.
- Selecting a fragment manually still seeks without autoplay and enables scoped looping and boundary editing.
- Media shortcuts work when focus is on the workbench or timeline.
- Media shortcuts do not fire when focus is outside the workbench or inside text/form controls.
- The workbench focus indicator is visible for keyboard focus and does not obscure video or thumbnails.
- Focused component tests, Svelte validation, linting, formatting, and a browser smoke pass.
