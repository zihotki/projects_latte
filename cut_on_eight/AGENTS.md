# Cut on Eight

## Architecture

- `apps/web` is a client-only Svelte 5 SPA. Do not add SvelteKit or SSR.
- `apps/server` is a local Fastify service bound to `127.0.0.1`.
- `packages/contracts` owns shared Zod schemas and inferred TypeScript types.
- Keep filesystem and process access in the backend.
- Keep domain logic in focused plain TypeScript modules.
