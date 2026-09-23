# Frontend state

The web app uses Svelte 5 runes in feature models. It has no global store or
frontend event log. To explain a value on screen, find its owner, the operation
that changes it, and the projection that the view reads.

| Owner             | State                                                             | Main file                                      |
| ----------------- | ----------------------------------------------------------------- | ---------------------------------------------- |
| Workspace session | Server workspace snapshot, open-video working copies, save status | `apps/web/src/app/workspace-session.svelte.ts` |
| Fragment library  | Fragment and tag catalogue, refresh and undo state                | `apps/web/src/app/fragment-library.svelte.ts`  |
| Search            | Query, filters, result, request state                             | `apps/web/src/app/search-model.svelte.ts`      |
| Processing        | Video-work status and refresh state                               | `apps/web/src/app/processing-model.svelte.ts`  |
| UI preferences    | Active view and editor-panel preferences                          | `apps/web/src/app/ui-preferences.svelte.ts`    |
| App coordinator   | Startup and flows that cross feature owners                       | `apps/web/src/app/app-model.svelte.ts`         |

Views read these models and call named operations. A component can keep focus,
hover, and live playback samples locally. It must not write another feature's
shared state. `EditorOperation` in `apps/web/src/domain/editor-operations.ts`
names editor changes and applies them as plain TypeScript transitions. The
`projectWorkspace` projection in `apps/web/src/app/workspace-projections.ts`
combines server data with open-video working copies without changing either
input. Simple projections can be model getters; projections do not call APIs.

For an editor change, `VideoEditor` sends a named operation to
`WorkspaceSession`. The session updates the working copy; `SaveController`
marks it unsaved and queues autosave. The projected workspace shows that copy.
On save success, the returned project becomes the server snapshot. A newer edit
made during the request stays in the working copy until its own save finishes.
On failure, the working copy remains and the save error offers retry. A
workspace refresh accepts new server facts while preserving unsaved editor
fields. Fast playback samples stay outside the shared projection until they
are materialized for save.

For a cross-feature flow, start at `AppModel`. For example,
`openSearchResult` reopens the video through the workspace owner, selects the
fragment through a named editor operation, then changes the active view.
Fragment and search models reject late responses from obsolete requests.

Add tracing only if a real debugging case needs it. Keep this guide short;
feature tests are the main record of why each transition behaves as it does.
