# Cut on Eight

Local browser-based dance-video segmentation and cataloguing for macOS.

## Prerequisites

- macOS (the importer uses the native file picker)
- Node.js 24 or newer
- pnpm 11.9.0 (`corepack enable` can provide the pinned version)
- `ffprobe` on `PATH` for source metadata inspection (usually installed with
  FFmpeg)

Missing `ffprobe` does not block importing, playback, marking, or saving. The
inspection fails visibly and can be retried after `ffprobe` is installed.

## Start

```bash
pnpm install
pnpm dev
```

Open <http://127.0.0.1:5173>. `pnpm dev` starts the Fastify API on
<http://127.0.0.1:4318>, starts Vite on <http://127.0.0.1:5173>, and normally
opens the browser. Set `CI=1` to suppress automatic browser opening.

Projects are stored outside the repository in `~/cut-on-eight_data`. To use a
different location, pass an absolute path when starting the app:

```bash
CUT_ON_EIGHT_DATA_ROOT=/absolute/path/to/data pnpm dev
```

`CUT_ON_EIGHT_PORT` can override the API port; the development proxy uses the
same value.

## Phase 1 workflow

Choose **Import MP4** to open the native macOS picker. The backend validates the
selection, creates a project under the managed data root, and attempts an APFS
copy-on-write clone before falling back to a full copy. Editing always uses this
managed copy, not the external file.

Several projects can remain open. The project strip identifies the active one
and shows save and inspection state. Switching projects saves the current
playback position before activating the next project. Closing a project saves
it and removes it from the open workspace without waiting for background jobs;
it does not delete the managed project. Closed projects remain in the library
and can be reopened without copying the video again.

### Keyboard controls

Shortcuts are ignored while typing in a form control.

| Key            | Action                                                                    |
| -------------- | ------------------------------------------------------------------------- |
| `Space`        | Play or pause                                                             |
| `I`            | Set or replace the pending in-point at the current time                   |
| `O`            | Create and select a segment from the pending in-point to the current time |
| `Escape`       | Cancel the pending in-point                                               |
| `Delete`       | Delete the selected segment                                               |
| `Backspace`    | Delete the most recently created segment                                  |
| `Cmd/Ctrl + S` | Save the active project immediately                                       |

When the timeline is focused, `Left` and `Right` seek by one second,
`Shift + Left/Right` seek by ten seconds, and `Home`/`End` seek to the start/end.
Creating a segment continues playback unless **Pause after creating a segment**
is enabled.

### Saving and background work

Edits autosave after one second. **Cmd/Ctrl + S** saves immediately. Project
switching flushes pending changes. Close also saves first; if saving fails, the
project stays open so it can be retried.

Source inspection jobs are persisted in each project directory. Work continues
after a project is closed, and queued or interrupted work resumes when the
backend restarts. Failed retryable jobs expose a **Retry** action. Missing or
failed `ffprobe` affects metadata inspection only and never blocks editing.

> [!WARNING]
> Treat the managed data root as application-owned storage. Deleting or editing
> files there can remove the managed video, sidecar, catalogue, workspace, or
> durable jobs and may make projects impossible to reopen. Closing a project in
> the UI is safe and does not delete these files.

## Verify

```bash
pnpm check
pnpm test
pnpm build
```

## Workspace

- `apps/web`: Svelte 5 client-only SPA
- `apps/server`: local Fastify backend
- `packages/contracts`: shared runtime schemas and TypeScript types
- `.agents` and `.codex`: repository-scoped Svelte agent tooling
- `plans`: approved designs and implementation plans

Start future Codex tasks with this `cut_on_eight` folder as the working directory so its nested skills, MCP configuration, and `AGENTS.md` are discovered.
