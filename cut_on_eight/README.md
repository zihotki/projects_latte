# Cut on Eight

Local browser-based dance-video segmentation and cataloguing.

## Prerequisites

- macOS
- Node.js 24 or newer
- pnpm 11.9.0

## Start

```bash
pnpm install
pnpm dev
```

The command starts the Fastify backend on `127.0.0.1:4318`, starts Vite on `127.0.0.1:5173`, and opens the browser. Set `CI=1` to suppress automatic browser opening.

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
