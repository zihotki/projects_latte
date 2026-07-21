# Phase 1: Foundation and Marking

**Status:** Approved design, pending review of this written version

**Date:** 2026-07-21

**Product:** Cut on Eight

## Purpose

Phase 1 establishes a browser-based local application and validates its primary interaction: import local MP4 files into managed storage, keep several projects open, play one active video, mark rough segments with the keyboard, save those segments, and explicitly close a project without blocking its background work.

This phase also establishes repository-scoped AI guidance and Svelte validation so later agent-written code consistently uses modern Svelte 5 patterns.

## Scope

### Included

- pnpm workspace contained entirely in `projectslatte/cut_on_eight`.
- Svelte 5 and Vite client-only SPA with strict TypeScript.
- Separate Node.js and Fastify local backend with strict TypeScript.
- Shared Zod API schemas and inferred TypeScript types.
- One development command that starts both applications and opens the browser.
- Backend bound only to `127.0.0.1`.
- Backend-triggered native macOS MP4 picker.
- Import into the managed library at `~/cut-on-eight_data` before editing.
- Multiple open projects with one visibly active project.
- HTTP byte-range video streaming for browser playback and seeking.
- Rough segment marking, selection, seeking, and deletion.
- Autosave, explicit save, workspace restoration, and explicit close.
- Durable file-backed background-job queue.
- FFprobe source inspection as the first background job.
- Repository-scoped Svelte AI skills, MCP configuration, and instructions.
- Linting, formatting, type checking, focused tests, and Git ignores.

### Deferred

- Installable application packaging and Electron.
- SSR or SvelteKit.
- Thumbnail generation.
- Timeline zoom, scrolling, and boundary dragging.
- Frame nudging and selected-segment loop preview.
- Title, tags, and notes editing.
- Clip export, retries, and export progress.
- Authentication, remote access, collaboration, and cloud storage.
- Full catalogue search or taxonomy management.

## Repository Boundary

All product and agentic configuration lives below `cut_on_eight`:

```text
projectslatte/
└── cut_on_eight/
    ├── .agents/
    │   └── skills/
    ├── .codex/
    │   └── config.toml
    ├── apps/
    │   ├── server/
    │   └── web/
    ├── packages/
    │   └── contracts/
    ├── plans/
    │   └── phase-01-foundation-and-marking/
    ├── AGENTS.md
    ├── .gitignore
    ├── package.json
    └── pnpm-workspace.yaml
```

No root-level pnpm workspace, MCP configuration, Svelte skill, application instruction, or ignore rule is added to `projectslatte`.

Future Codex tasks for this application should start with `projectslatte/cut_on_eight` as their working directory. Codex discovers nested `AGENTS.md`, `.agents/skills`, and `.codex/config.toml` from the task working directory up to the Git root.

## Architecture

### Frontend

`apps/web` is a Svelte 5 SPA built with Vite. It uses runes-mode components and keeps domain behavior in plain TypeScript modules wherever possible. It does not contain filesystem, process, or FFmpeg access.

The frontend owns:

- Open-project and active-project presentation.
- Native HTML video element integration.
- Keyboard command routing.
- Pending in-point and segment editing state.
- Save and background-job status presentation.
- Confirmation before replacing or closing state when required.

High-frequency playback and timeline painting must not drive broad component reactivity. Playback sampling uses `requestAnimationFrame`, and later Canvas work will remain behind a focused adapter.

### Backend

`apps/server` is a Fastify service that listens only on the loopback interface. It owns all trusted local operations:

- Native macOS file selection.
- Managed-file import and validation.
- Workspace, library, sidecar, and job persistence.
- Video byte-range streaming.
- FFprobe process execution.
- Durable background-job scheduling and recovery.

The backend never exposes unrestricted filesystem paths, arbitrary file reads, arbitrary process execution, or a generic shell endpoint to the frontend.

### Shared contracts

`packages/contracts` contains Zod schemas for API messages and persisted versioned data. Types are inferred from schemas rather than duplicated. The package contains no browser or Node-specific behavior.

### Communication

The frontend uses task-specific JSON HTTP endpoints. Video bytes use a dedicated endpoint with standard range-request behavior. Background status is streamed with Server-Sent Events, with a normal snapshot endpoint for initial load and reconnection.

Representative operations are:

```text
GET    /api/health
GET    /api/workspace
GET    /api/library
POST   /api/imports/select
POST   /api/projects/:id/open
POST   /api/projects/:id/activate
PUT    /api/projects/:id
POST   /api/projects/:id/close
GET    /api/sources/:id/content
GET    /api/jobs
GET    /api/events
POST   /api/jobs/:id/retry
```

Exact endpoint naming may be refined during implementation, but the task-specific boundary and capabilities must remain unchanged.

## Managed Storage

The managed data root is:

```text
~/cut-on-eight_data
```

It is created on first use when absent. Each imported source receives one collision-safe folder:

```text
~/cut-on-eight_data/
├── _system/
│   ├── workspace.json
│   └── library.json
└── cross-body-lead--a1b2c3d4/
    ├── original-name.mp4
    ├── original-name.mp4.danceclips.json
    ├── thumbnails/
    ├── exports/
    └── jobs/
```

The human-readable slug makes the folder recognizable; the short stable ID prevents collisions. The generic `.danceclips.json` suffix remains independent of the product name.

`workspace.json` stores which managed projects are open and which one is active. `library.json` stores the minimal import index needed to locate managed projects and recognize a previously imported external source. Project state remains in the sidecar beside its managed MP4.

All JSON writes use temporary files followed by atomic replacement. Persisted objects include a schema version.

## Import Lifecycle

Opening an external MP4 is an import operation:

1. The user selects **Import MP4**.
2. The backend opens the standard macOS file picker.
3. The backend validates the selection and allocates a temporary managed folder.
4. It attempts an APFS copy-on-write clone and falls back to a full copy.
5. It validates the managed copy and writes the initial sidecar.
6. It atomically promotes the temporary folder into the library.
7. It adds the project to the persisted workspace and makes it active.
8. It durably queues source inspection through FFprobe.

Editing never starts against the external source. A failed or cancelled import never exposes a partially imported project. Temporary imports are safe to clean up on restart.

When a known external source is selected again, the user is offered its existing managed project rather than receiving a silent duplicate. A user may still explicitly import another independent copy later; Phase 1 does not require that override.

## Multi-Project Workspace

Several projects may be open concurrently, with exactly one active editor.

The application bar contains import, managed-library reopen, backend health, FFmpeg/FFprobe health, and global background-job status.

An open-project strip shows each open file with:

- Filename.
- Active state.
- Save state.
- Background-job state.
- Explicit close action.

Switching projects saves the current playback position in project state, activates the chosen project, and restores that project's player and selection state. Browser refresh and backend restart restore the open-project set and active project.

Closing a project performs this sequence:

1. Save its sidecar immediately.
2. If saving fails, keep it open and show an actionable error.
3. Remove it from the persisted open workspace.
4. Remove it from the UI without waiting for background jobs.

Closing does not delete the managed folder or cancel jobs. A lightweight managed-library list can reopen closed projects; full catalogue browsing remains deferred.

## Editor Behavior

The active editor contains:

- Native video player.
- Current time and duration.
- A basic source timeline without thumbnails or zoom.
- Pending in-point and segment overlays.
- Chronological segment list.

Phase 1 keyboard behavior is:

| Key | Action |
| --- | --- |
| `Space` | Play or pause |
| `I` | Set or replace the pending segment start |
| `O` | Create and select a segment ending at the current time |
| `Esc` | Cancel the pending segment |
| `Delete` | Delete the selected segment |
| `Backspace` | Delete the most recently created segment |
| `Cmd/Ctrl + S` | Save the active project immediately |

`I` continues playback. `O` creates a segment only when a pending start exists and the current position is later than that start. The default is to continue playback after creation. Overlapping segments are valid.

Clicking a segment selects it and seeks to its start. Segment ordering is recalculated from start time. Phase 1 boundaries are rough timestamps from the browser player; precision editing is deferred.

## Persistence Model

The initial versioned project schema contains:

- Managed source filename and duration when known.
- Pause-after-creation setting.
- Playback position.
- Selected segment ID.
- Segment IDs, start/end timestamps, and export-selection default.
- Reserved optional metadata fields compatible with later title, tags, and notes work.

Project mutations autosave after a one-second debounce. Explicit save bypasses the debounce. Save states are `saved`, `saving`, `unsaved`, and `failed`.

Malformed sidecars are never overwritten automatically. They produce a structured error and preserve the original bytes for diagnosis.

## Durable Background Jobs

Jobs are persisted as versioned JSON records in the owning project's `jobs` directory. The queue uses atomic file replacement and a single local worker initially.

Job states are:

```text
queued → running → completed
                 ↘ failed
```

On backend startup, jobs left in `running` are returned to `queued` and retried according to their stored attempt policy. Closing a project does not affect its jobs. Stopping the backend pauses work; the next backend start resumes it.

The first job type is `inspect-source`. It invokes FFprobe and records duration, dimensions, frame-rate information, audio presence, and inspection errors. A missing or failed FFprobe is visible and retryable but does not block browser playback or segment marking.

Thumbnail and export job types are deferred, but they must use this queue rather than introduce another scheduler.

## Error Handling

API failures use a shared structured error envelope with a stable code, user-facing message, retryability, and optional safe details.

Required Phase 1 behavior includes:

- Invalid or unsupported selections do not enter the workspace.
- Import failure leaves the external source and existing library untouched.
- Video stream failures identify the affected project.
- Backend unavailability is visible without presenting stale state as saved.
- Sidecar save failure blocks explicit close.
- Malformed sidecars are not silently replaced.
- Failed inspection jobs remain retryable.
- Missing FFprobe does not block editing.
- One project's error does not close or corrupt other open projects.

## Repository-Scoped AI Tooling

The AI setup is intentionally scoped below `cut_on_eight`:

- `.agents/skills/svelte-code-writer` is a pinned, attributed copy of the official Svelte skill.
- `.agents/skills/svelte-core-bestpractices` is a pinned, attributed copy of the official Svelte skill.
- `.codex/config.toml` registers the official Svelte MCP server using a pinned project dependency.
- Root `AGENTS.md` describes architecture, commands, boundaries, and verification.
- `apps/web/AGENTS.md` requires modern Svelte 5 syntax and Svelte-specific validation.

The web instructions require:

- Runes mode for new code.
- `$state`, `$derived`, and `$props` where appropriate.
- No legacy `$:`, `export let`, `on:click`, slots, or legacy component APIs.
- Effects only for actual side effects.
- Plain TypeScript for domain logic.
- Official Svelte autofixer on changed `.svelte` and `.svelte.ts` files.
- `svelte-check --fail-on-warnings` before completion.

The project config and skills load automatically only when a future Codex task starts in `cut_on_eight` or a descendant directory. This is the intended isolation boundary.

## Development Plumbing

The pnpm workspace provides root commands for:

```text
pnpm dev
pnpm build
pnpm lint
pnpm format
pnpm format:check
pnpm check
pnpm test
```

`pnpm check` combines TypeScript checks, Svelte checks, linting, and formatting validation. Application packages may expose narrower commands, but the root commands remain authoritative.

The nested `.gitignore` covers dependencies, build output, coverage, logs, local environment files, macOS metadata, temporary imports, and MP4 files. It does not ignore `.agents`, `.codex`, plans, lockfiles, or example configuration.

## Verification Strategy

Testing is deliberately focused rather than exhaustive:

- Unit tests for segment creation, ordering, selection, and deletion.
- Persistence tests for atomic sidecar and workspace writes.
- Server integration test for HTTP byte-range responses.
- Queue recovery test proving an interrupted job resumes after restart.
- One browser smoke test for open, switch, mark, save, and close using controlled fixtures.
- Manual macOS verification of the native picker and APFS clone fallback behavior.

Generated and edited Svelte files additionally pass the official Svelte autofixer without remaining issues or suggestions.

## Acceptance Criteria

Phase 1 is complete when:

1. `pnpm dev` starts the backend and SPA and opens the browser.
2. The backend accepts connections only from the local machine.
3. An external MP4 can be selected with the native macOS picker.
4. The source is copied or cloned into a unique folder under `~/cut-on-eight_data` before editing.
5. The managed source plays and seeks through a byte-range endpoint.
6. Several projects can remain open and the active project is unambiguous.
7. Open projects and the active selection survive refresh and backend restart.
8. `I` and `O` create at least five valid, possibly overlapping segments during playback.
9. Segments appear on the basic timeline and in chronological list order.
10. Segment state and playback position remain independent across open projects.
11. Autosave and explicit save persist sidecars atomically.
12. Closing saves, removes the project from the open workspace, and does not wait for jobs.
13. Save failure prevents closing.
14. A closed managed project can be reopened without copying the video again.
15. FFprobe inspection is durably queued, survives restart, and can fail without blocking editing.
16. Svelte-specific AI skills and MCP configuration are scoped to `cut_on_eight`.
17. All automated checks pass, and the native picker is manually verified on macOS.

## References

- [Svelte AI tools](https://svelte.dev/docs/ai/overview)
- [Svelte AI skills and autofixer](https://svelte.dev/docs/ai/skills)
- [Svelte TypeScript support](https://svelte.dev/docs/svelte/typescript)
- [Codex repository skills](https://developers.openai.com/codex/skills)
- [Codex project configuration](https://developers.openai.com/codex/config-advanced)
- [Codex AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
