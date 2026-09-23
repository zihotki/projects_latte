# Frontend state ownership and operations

## Intent

Make frontend state easy for a person or coding agent to understand and reason
about. For a displayed value, a reader should be able to find its owner, its
inputs, and the operation that can change those inputs. Preserve the current
Svelte 5 SPA and visible behavior.

## Decision

Keep Svelte runes and the existing feature-model direction. Do not add
SignalTree, a general store library, or an app-wide mutable tree. Borrow the
useful structure: feature-owned state, named operations, and explicit
projections. This is a code organization change, not frontend event sourcing.

Shared state changes through named operations. Component-only values, such as
an open tooltip or a local input focus, can remain local. An operation name
describes user or system intent (`selectFragment`, `saveAndClose`,
`refreshProcessing`), not a generic path update. Views read feature state and
call operations; they do not directly write another feature's state.

## Ownership

| Owner             | State and responsibility                                                                                         |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| Workspace/catalog | Server-owned workspace and video snapshots, open-video identity, and refresh lifecycle.                          |
| Editor session    | A working copy for each open video, selection and persisted editor settings, save status, and save coordination. |
| Fragment library  | Fragment-list snapshot, tag list, and fragment-list request state.                                               |
| Search            | Query/filter inputs, current result, and request state.                                                          |
| Processing        | Video-processing snapshot and its refresh state.                                                                 |
| UI preferences    | Shared view and persisted editor-panel preferences; browser storage is only an adapter.                          |

This is a conceptual ownership map, not a demand for six new stores. Keep or
split the current classes only where the boundary makes code simpler. In
particular, `WorkspaceSession` currently mixes a server snapshot, editable
documents, save state, and callbacks. Make the authoritative snapshot and
working copies distinct inside that feature. Keep the existing API contract;
adapt to it at the frontend boundary.

## Projections and coordination

Projections are read-only computations from owned state. A simple projection
may be a model getter; a projection with several inputs belongs in a focused,
plain TypeScript function. Do not cache a second mutable copy of a value that
can be derived cheaply. Projections do not call APIs or change state. Examples
include the active editor document, editor mode, close availability, and app
status.

`AppModel` remains a small composition root and coordinator for workflows that
cross features. For example, opening a search result opens its video and then
selects its fragment through the owning feature's operations. Replace hidden
cross-feature callbacks where they obscure this sequence; do not move all
feature logic into `AppModel`.

## Async and failure rules

An operation owns its pending, success, and failure transitions. Prevent stale
responses from replacing newer state; abort obsolete requests where useful.
For an editor save, retain the working copy while the request runs. On success,
apply the returned revision and data without losing edits made during the
request. On failure, keep the draft and show a retryable error. A refresh must
not silently erase unsaved work. Keep existing autosave and explicit-close
semantics.

Do not force every feature into one generic request-state type. Use a common
vocabulary where it helps (`idle`, `loading`, `ready`, `error`), but keep
feature-specific transitions explicit. Fast playback samples need not become
shared operations or trigger application-wide updates.

## Scope and rollout

Start with `WorkspaceSession` and its editor/save boundary. Then apply the
same rules to fragment, search, processing, and preference state where the
current code benefits. Migrate one flow at a time, keep adapters short-lived,
and retain current UI behavior. Add a brief repo-local frontend-state guide
that identifies owners, operations, and projection locations; do not enlarge
`AGENTS.md` with a long state-management manual.

Do not add an operation trace, DevTools integration, persistence layer, global
command bus, generic reducer framework, undo/redo framework, or new dependency
in this pass. Revisit tracing only when a concrete debugging need appears.

## Verification

Test meaningful transitions rather than every field assignment: draft edits,
save success/failure and in-flight edits, refresh with unsaved work, stale
responses, and cross-feature opening from search. Test nontrivial projections
as plain functions. Keep a few component tests for visible behavior and run
the repository check and test scripts. A successful refactor leaves the editor,
search, library, and processing flows working as before, while a reader can
trace each shared value to one owner and named operation.
