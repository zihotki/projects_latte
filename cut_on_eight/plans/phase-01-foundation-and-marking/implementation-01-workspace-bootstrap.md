# Phase 1 Workspace Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable pnpm monorepo with a Svelte 5 hello-world SPA, a separate Fastify health API, shared runtime contracts, and repository-scoped Svelte/Codex tooling.

**Architecture:** `cut_on_eight` is a self-contained pnpm workspace. Vite serves the client-only Svelte SPA and proxies `/api` to a Fastify server bound to `127.0.0.1`; a compiled shared package owns Zod contracts. Codex guidance, MCP configuration, and official Svelte skills live below `cut_on_eight` so sibling projects remain unaffected.

**Tech Stack:** Node.js 24+, pnpm 11.9.0, TypeScript, Svelte 5, Vite, Fastify, Zod, Vitest, ESLint, Prettier, official `@sveltejs/mcp`.

## Global Constraints

- Make no changes outside `projectslatte/cut_on_eight`.
- Use a client-only Svelte 5 SPA; do not add SvelteKit or SSR.
- Keep frontend and backend as separate workspace packages.
- Bind development servers to `127.0.0.1`.
- Use strict TypeScript and shared Zod contracts.
- Use Svelte 5 runes and modern event syntax; do not add legacy Svelte syntax.
- Keep tests focused: one contract/API test and build/check verification are sufficient for this checkpoint.
- Track `.agents`, `.codex`, lockfiles, and plans; ignore MP4 and generated files.
- Do not implement file import, video playback, persistence, jobs, or segment marking in this checkpoint.

---

## File Map

### Workspace root

- `cut_on_eight/package.json`: authoritative workspace commands and pinned package-manager declaration.
- `cut_on_eight/pnpm-workspace.yaml`: package discovery.
- `cut_on_eight/tsconfig.base.json`: shared strict compiler defaults.
- `cut_on_eight/eslint.config.js`: TypeScript linting for browser, server, scripts, and shared packages.
- `cut_on_eight/.prettierrc.json`: repository formatting rules and Svelte plugin registration.
- `cut_on_eight/.prettierignore`: generated-file exclusions.
- `cut_on_eight/.gitignore`: project-local generated, secret, media, and macOS exclusions.
- `cut_on_eight/README.md`: setup, commands, architecture, and Codex working-directory guidance.

### Shared contracts

- `cut_on_eight/packages/contracts/package.json`: compiled workspace package definition.
- `cut_on_eight/packages/contracts/tsconfig.json`: declaration-emitting build.
- `cut_on_eight/packages/contracts/src/health.ts`: health response schema and inferred type.
- `cut_on_eight/packages/contracts/src/index.ts`: public exports.
- `cut_on_eight/packages/contracts/test/health.test.ts`: runtime schema contract.

### Backend

- `cut_on_eight/apps/server/package.json`: Fastify application commands and dependencies.
- `cut_on_eight/apps/server/tsconfig.json`: Node ESM build.
- `cut_on_eight/apps/server/src/app.ts`: Fastify construction and routes, without starting a socket.
- `cut_on_eight/apps/server/src/config.ts`: host and port parsing.
- `cut_on_eight/apps/server/src/server.ts`: process entrypoint and graceful shutdown.
- `cut_on_eight/apps/server/test/health.test.ts`: injected HTTP health test.

### Frontend

- `cut_on_eight/apps/web/package.json`: Svelte/Vite commands and dependencies.
- `cut_on_eight/apps/web/svelte.config.js`: Svelte preprocessing.
- `cut_on_eight/apps/web/tsconfig.json`: browser/Svelte compiler settings.
- `cut_on_eight/apps/web/vite.config.ts`: loopback server, browser opening, and API proxy.
- `cut_on_eight/apps/web/src/vite-env.d.ts`: Vite client types.
- `cut_on_eight/apps/web/src/main.ts`: Svelte mount entrypoint.
- `cut_on_eight/apps/web/src/App.svelte`: hello-world UI and backend health display.
- `cut_on_eight/apps/web/src/app.css`: minimal editor-shell styling.
- `cut_on_eight/apps/web/index.html`: Vite HTML entrypoint.

### Repository-scoped AI artifacts

- `cut_on_eight/AGENTS.md`: product-wide boundaries, commands, and verification expectations.
- `cut_on_eight/apps/web/AGENTS.md`: Svelte 5-specific instructions.
- `cut_on_eight/.codex/config.toml`: project-local Svelte MCP configuration.
- `cut_on_eight/.agents/skills/svelte-code-writer/SKILL.md`: official Svelte code-writer skill.
- `cut_on_eight/.agents/skills/svelte-core-bestpractices/SKILL.md`: official Svelte best-practices skill.
- `cut_on_eight/.agents/skills/UPSTREAM.md`: source repository and captured upstream revision.

---

### Task 1: Establish the pnpm workspace and shared tooling

**Files:**

- Create: `cut_on_eight/package.json`
- Create: `cut_on_eight/pnpm-workspace.yaml`
- Create: `cut_on_eight/tsconfig.base.json`
- Create: `cut_on_eight/eslint.config.js`
- Create: `cut_on_eight/.prettierrc.json`
- Create: `cut_on_eight/.prettierignore`
- Create: `cut_on_eight/.gitignore`
- Create: `cut_on_eight/apps/server/package.json`
- Create: `cut_on_eight/apps/web/package.json`
- Create: `cut_on_eight/packages/contracts/package.json`

**Interfaces:**

- Consumes: Node.js 24+ and pnpm 11.9.0 installed on the developer machine.
- Produces: authoritative root scripts `dev`, `build`, `check`, `test`, `lint`, `format`, and `format:check`; workspace package names used by every later task.

- [ ] **Step 1: Create the root package manifest**

```json
{
  "name": "cut-on-eight",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "packageManager": "pnpm@11.9.0",
  "engines": {
    "node": ">=24"
  },
  "scripts": {
    "predev": "pnpm --filter @cut-on-eight/contracts build",
    "dev": "concurrently --kill-others-on-fail --names contracts,server,web --prefix-colors yellow,cyan,magenta \"pnpm --filter @cut-on-eight/contracts dev\" \"pnpm --filter @cut-on-eight/server dev\" \"wait-on http-get://127.0.0.1:4318/api/health && pnpm --filter @cut-on-eight/web dev\"",
    "build": "pnpm -r build",
    "precheck": "pnpm --filter @cut-on-eight/contracts build",
    "check": "pnpm -r check && pnpm lint && pnpm format:check",
    "pretest": "pnpm --filter @cut-on-eight/contracts build",
    "test": "pnpm -r --if-present test",
    "lint": "eslint \"apps/**/*.ts\" \"packages/**/*.ts\"",
    "format": "prettier --write .",
    "format:check": "prettier --check ."
  },
  "devDependencies": {}
}
```

- [ ] **Step 2: Create workspace and TypeScript configuration**

`pnpm-workspace.yaml`:

```yaml
packages:
  - apps/*
  - packages/*
```

`tsconfig.base.json`:

```json
{
  "compilerOptions": {
    "allowJs": false,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "noEmitOnError": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitOverride": true,
    "noUncheckedIndexedAccess": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "strict": true,
    "target": "ES2023",
    "useDefineForClassFields": true,
    "verbatimModuleSyntax": true
  }
}
```

- [ ] **Step 3: Create package manifests with stable workspace names**

`packages/contracts/package.json`:

```json
{
  "name": "@cut-on-eight/contracts",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    }
  },
  "files": ["dist"],
  "scripts": {
    "dev": "tsc --watch --preserveWatchOutput",
    "build": "tsc",
    "check": "tsc --noEmit",
    "test": "vitest run"
  }
}
```

`apps/server/package.json`:

```json
{
  "name": "@cut-on-eight/server",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "tsx watch src/server.ts",
    "build": "tsc",
    "check": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@cut-on-eight/contracts": "workspace:*"
  }
}
```

`apps/web/package.json`:

```json
{
  "name": "@cut-on-eight/web",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "check": "svelte-check --tsconfig ./tsconfig.json --fail-on-warnings",
    "test": "vitest run --passWithNoTests"
  },
  "dependencies": {
    "@cut-on-eight/contracts": "workspace:*"
  }
}
```

- [ ] **Step 4: Create formatting, linting, and ignore configuration**

`.prettierrc.json`:

```json
{
  "plugins": ["prettier-plugin-svelte"],
  "singleQuote": true,
  "trailingComma": "all"
}
```

`.prettierignore`:

```text
**/dist
**/coverage
**/node_modules
.agents
plans
pnpm-lock.yaml
```

`.gitignore`:

```text
node_modules/
dist/
coverage/
.vite/
*.log
.env
.env.*
!.env.example
.DS_Store
*.mp4
*.mov
*.m4v
*.tmp
*.swp
```

`eslint.config.js`:

```js
import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['**/dist/**', '**/coverage/**', '**/node_modules/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['apps/web/**/*.ts'],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ['apps/server/**/*.ts', 'packages/**/*.ts'],
    languageOptions: { globals: globals.node },
  },
);
```

- [ ] **Step 5: Install root development dependencies**

Run from `cut_on_eight`:

```bash
pnpm add -Dw concurrently wait-on typescript vitest prettier prettier-plugin-svelte eslint @eslint/js typescript-eslint globals @types/node @sveltejs/mcp
```

Expected: `package.json` receives version ranges and `pnpm-lock.yaml` pins their resolved versions.

- [ ] **Step 6: Install package-specific dependencies**

```bash
pnpm --filter @cut-on-eight/contracts add zod
pnpm --filter @cut-on-eight/server add fastify
pnpm --filter @cut-on-eight/server add -D tsx @types/node
pnpm --filter @cut-on-eight/web add svelte
pnpm --filter @cut-on-eight/web add -D vite @sveltejs/vite-plugin-svelte svelte-check
```

Expected: all three package manifests receive their external dependencies and the lockfile remains current.

- [ ] **Step 7: Verify workspace resolution**

Run:

```bash
pnpm list -r --depth -1
```

Expected: output lists `cut-on-eight`, `@cut-on-eight/contracts`, `@cut-on-eight/server`, and `@cut-on-eight/web`.

- [ ] **Step 8: Commit the workspace skeleton**

```bash
git add cut_on_eight/package.json cut_on_eight/pnpm-lock.yaml cut_on_eight/pnpm-workspace.yaml cut_on_eight/tsconfig.base.json cut_on_eight/eslint.config.js cut_on_eight/.prettierrc.json cut_on_eight/.prettierignore cut_on_eight/.gitignore cut_on_eight/apps/server/package.json cut_on_eight/apps/web/package.json cut_on_eight/packages/contracts/package.json
git commit -m "chore: scaffold Cut on Eight workspace"
```

### Task 2: Add the shared health contract and Fastify server

**Files:**

- Create: `cut_on_eight/packages/contracts/tsconfig.json`
- Create: `cut_on_eight/packages/contracts/src/health.ts`
- Create: `cut_on_eight/packages/contracts/src/index.ts`
- Create: `cut_on_eight/packages/contracts/test/health.test.ts`
- Create: `cut_on_eight/apps/server/tsconfig.json`
- Create: `cut_on_eight/apps/server/src/config.ts`
- Create: `cut_on_eight/apps/server/src/app.ts`
- Create: `cut_on_eight/apps/server/src/server.ts`
- Create: `cut_on_eight/apps/server/test/health.test.ts`

**Interfaces:**

- Consumes: workspace package `@cut-on-eight/contracts` and installed Fastify/Zod/Vitest dependencies.
- Produces: `healthResponseSchema`, `HealthResponse`, `createApp()`, `getServerConfig()`, and `GET /api/health` returning `{ status: "ok", service: "cut-on-eight-server" }`.

- [ ] **Step 1: Write the failing shared contract test**

`packages/contracts/test/health.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { healthResponseSchema } from '../src/health.js';

describe('healthResponseSchema', () => {
  it('accepts the server health payload', () => {
    expect(
      healthResponseSchema.parse({
        status: 'ok',
        service: 'cut-on-eight-server',
      }),
    ).toEqual({
      status: 'ok',
      service: 'cut-on-eight-server',
    });
  });
});
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run:

```bash
pnpm --filter @cut-on-eight/contracts test
```

Expected: FAIL because `src/health.ts` does not exist.

- [ ] **Step 3: Implement and export the health contract**

`packages/contracts/src/health.ts`:

```ts
import { z } from 'zod';

export const healthResponseSchema = z.object({
  status: z.literal('ok'),
  service: z.literal('cut-on-eight-server'),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;
```

`packages/contracts/src/index.ts`:

```ts
export { healthResponseSchema } from './health.js';
export type { HealthResponse } from './health.js';
```

`packages/contracts/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "declaration": true,
    "declarationMap": true,
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "sourceMap": true
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 4: Run contract tests and build**

```bash
pnpm --filter @cut-on-eight/contracts test
pnpm --filter @cut-on-eight/contracts build
```

Expected: one passing test and generated `packages/contracts/dist` output.

- [ ] **Step 5: Write the failing server health test**

`apps/server/test/health.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';

describe('GET /api/health', () => {
  it('returns the shared health contract', async () => {
    const app = createApp();

    const response = await app.inject({
      method: 'GET',
      url: '/api/health',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      status: 'ok',
      service: 'cut-on-eight-server',
    });

    await app.close();
  });
});
```

- [ ] **Step 6: Run the server test to verify it fails**

```bash
pnpm --filter @cut-on-eight/server test
```

Expected: FAIL because `src/app.ts` does not exist.

- [ ] **Step 7: Implement configuration, app construction, and process entrypoint**

`apps/server/src/config.ts`:

```ts
export interface ServerConfig {
  host: '127.0.0.1';
  port: number;
}

export function getServerConfig(
  environment: NodeJS.ProcessEnv = process.env,
): ServerConfig {
  const port = Number.parseInt(environment.CUT_ON_EIGHT_PORT ?? '4318', 10);

  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error('CUT_ON_EIGHT_PORT must be an integer from 1 to 65535');
  }

  return { host: '127.0.0.1', port };
}
```

`apps/server/src/app.ts`:

```ts
import { healthResponseSchema } from '@cut-on-eight/contracts';
import Fastify, { type FastifyInstance } from 'fastify';

export function createApp(): FastifyInstance {
  const app = Fastify({ logger: true });

  app.get('/api/health', async () =>
    healthResponseSchema.parse({
      status: 'ok',
      service: 'cut-on-eight-server',
    }),
  );

  return app;
}
```

`apps/server/src/server.ts`:

```ts
import { createApp } from './app.js';
import { getServerConfig } from './config.js';

const app = createApp();
const config = getServerConfig();

const shutdown = async (): Promise<void> => {
  await app.close();
  process.exitCode = 0;
};

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await app.listen(config);
} catch (error) {
  app.log.error(error);
  process.exitCode = 1;
}
```

`apps/server/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "sourceMap": true,
    "types": ["node"]
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 8: Run server tests and build**

```bash
pnpm --filter @cut-on-eight/server test
pnpm --filter @cut-on-eight/server build
```

Expected: one passing server test and generated `apps/server/dist` output.

- [ ] **Step 9: Commit the shared contract and health API**

```bash
git add cut_on_eight/packages/contracts cut_on_eight/apps/server
git commit -m "feat: add local health API"
```

### Task 3: Add the Svelte 5 hello-world SPA

**Files:**

- Create: `cut_on_eight/apps/web/svelte.config.js`
- Create: `cut_on_eight/apps/web/tsconfig.json`
- Create: `cut_on_eight/apps/web/vite.config.ts`
- Create: `cut_on_eight/apps/web/index.html`
- Create: `cut_on_eight/apps/web/src/vite-env.d.ts`
- Create: `cut_on_eight/apps/web/src/main.ts`
- Create: `cut_on_eight/apps/web/src/App.svelte`
- Create: `cut_on_eight/apps/web/src/app.css`

**Interfaces:**

- Consumes: `HealthResponse` and `healthResponseSchema` from `@cut-on-eight/contracts`; `GET /api/health` from Task 2.
- Produces: browser UI showing product name, workspace readiness, and validated backend connection state.

- [ ] **Step 1: Create the Svelte/Vite build configuration**

`apps/web/svelte.config.js`:

```js
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
};
```

`apps/web/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "moduleResolution": "Bundler",
    "types": ["node", "svelte", "vite/client"]
  },
  "include": ["src/**/*.d.ts", "src/**/*.ts", "src/**/*.svelte", "vite.config.ts"]
}
```

`apps/web/vite.config.ts`:

```ts
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '127.0.0.1',
    open: process.env.CI !== '1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:4318',
    },
  },
});
```

- [ ] **Step 2: Create the browser entrypoint**

`apps/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#101114" />
    <title>Cut on Eight</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`apps/web/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
```

`apps/web/src/main.ts`:

```ts
import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

const target = document.querySelector<HTMLDivElement>('#app');

if (!target) {
  throw new Error('Application root was not found');
}

mount(App, { target });
```

- [ ] **Step 3: Create the modern Svelte 5 hello-world component**

`apps/web/src/App.svelte`:

```svelte
<script lang="ts">
  import {
    healthResponseSchema,
    type HealthResponse,
  } from '@cut-on-eight/contracts';

  type HealthState =
    | { kind: 'loading' }
    | { kind: 'ready'; value: HealthResponse }
    | { kind: 'failed'; message: string };

  let health = $state<HealthState>({ kind: 'loading' });

  async function loadHealth(): Promise<void> {
    try {
      const response = await fetch('/api/health');

      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }

      health = {
        kind: 'ready',
        value: healthResponseSchema.parse(await response.json()),
      };
    } catch (error) {
      health = {
        kind: 'failed',
        message: error instanceof Error ? error.message : 'Unknown backend error',
      };
    }
  }

  void loadHealth();
</script>

<svelte:head>
  <meta
    name="description"
    content="Local dance-video segmentation and cataloguing"
  />
</svelte:head>

<main>
  <section class="hero" aria-labelledby="page-title">
    <p class="eyebrow">Local dance-video workspace</p>
    <h1 id="page-title">Cut on Eight</h1>
    <p class="summary">
      The workspace is ready. Video importing and segment marking arrive in the
      next implementation checkpoint.
    </p>

    <div class="status" data-state={health.kind} aria-live="polite">
      {#if health.kind === 'loading'}
        Connecting to the local backend…
      {:else if health.kind === 'ready'}
        Backend connected: {health.value.service}
      {:else}
        Backend unavailable: {health.message}
      {/if}
    </div>
  </section>
</main>
```

- [ ] **Step 4: Add minimal shell styling**

`apps/web/src/app.css`:

```css
:root {
  color: #f4f1ea;
  background: #101114;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

* {
  box-sizing: border-box;
}

body {
  min-width: 320px;
  min-height: 100vh;
  margin: 0;
}

button,
input,
textarea {
  font: inherit;
}

main {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem;
  background:
    radial-gradient(circle at 20% 10%, #293448 0, transparent 34rem),
    #101114;
}

.hero {
  width: min(46rem, 100%);
  padding: clamp(2rem, 8vw, 5rem);
  border: 1px solid #343943;
  border-radius: 1.5rem;
  background: rgb(22 24 29 / 88%);
  box-shadow: 0 2rem 5rem rgb(0 0 0 / 35%);
}

.eyebrow {
  margin: 0 0 1rem;
  color: #e5bd64;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: clamp(3rem, 10vw, 6rem);
  letter-spacing: -0.065em;
  line-height: 0.9;
}

.summary {
  max-width: 34rem;
  margin: 2rem 0;
  color: #b8bdc8;
  font-size: 1.1rem;
  line-height: 1.6;
}

.status {
  display: inline-flex;
  padding: 0.7rem 0.9rem;
  border-radius: 999px;
  background: #242832;
  color: #d9dde6;
  font-size: 0.9rem;
}

.status[data-state='ready'] {
  background: #183c2f;
  color: #a8f0ce;
}

.status[data-state='failed'] {
  background: #4a2025;
  color: #ffc5ca;
}
```

- [ ] **Step 5: Validate the Svelte application**

Run:

```bash
pnpm --filter @cut-on-eight/web check
pnpm --filter @cut-on-eight/web build
```

Expected: Svelte check reports zero errors and warnings; Vite produces `apps/web/dist`.

- [ ] **Step 6: Commit the hello-world SPA**

```bash
git add cut_on_eight/apps/web
git commit -m "feat: add Cut on Eight web shell"
```

### Task 4: Add repository-scoped Codex and Svelte AI artifacts

**Files:**

- Create: `cut_on_eight/AGENTS.md`
- Create: `cut_on_eight/apps/web/AGENTS.md`
- Create: `cut_on_eight/.codex/config.toml`
- Create: `cut_on_eight/.agents/skills/svelte-code-writer/SKILL.md`
- Create: `cut_on_eight/.agents/skills/svelte-core-bestpractices/SKILL.md`
- Create: `cut_on_eight/.agents/skills/UPSTREAM.md`

**Interfaces:**

- Consumes: locally installed `@sveltejs/mcp` exposing the `svelte-mcp` binary; official skills from `https://github.com/sveltejs/ai-tools`.
- Produces: project-local skill discovery and Svelte MCP availability when Codex starts with `cut_on_eight` as its working directory.

- [ ] **Step 1: Install the pinned official skills into the universal repository scope**

From `cut_on_eight`, install both skills from the approved upstream revision:

```bash
npx -y skills add https://github.com/sveltejs/ai-tools/tree/8152ed9fd4e8a8c2e7d9d65fb5c5f9eae290168b --skill svelte-code-writer --skill svelte-core-bestpractices --agent codex --yes
```

Expected: the installer creates:

```text
.agents/skills/svelte-code-writer/SKILL.md
.agents/skills/svelte-core-bestpractices/SKILL.md
```

- [ ] **Step 2: Record skill provenance**

Create `.agents/skills/UPSTREAM.md`:

```markdown
# Svelte skill provenance

- Source: https://github.com/sveltejs/ai-tools
- Revision: `8152ed9fd4e8a8c2e7d9d65fb5c5f9eae290168b`
- Installed skills: `svelte-code-writer`, `svelte-core-bestpractices`
- Installed for: repository-scoped Codex discovery under `cut_on_eight`
```

- [ ] **Step 3: Configure the repository-local MCP server**

`.codex/config.toml`:

```toml
[mcp_servers.svelte]
command = "pnpm"
args = ["exec", "svelte-mcp"]
```

- [ ] **Step 4: Add product-wide agent guidance**

`AGENTS.md`:

```markdown
# Cut on Eight

These instructions apply only inside `projectslatte/cut_on_eight`.

## Architecture

- `apps/web` is a client-only Svelte 5 SPA. Do not add SvelteKit or SSR.
- `apps/server` is a local Fastify service bound to `127.0.0.1`.
- `packages/contracts` owns shared Zod schemas and inferred TypeScript types.
- Keep filesystem and process access in the backend.
- Keep domain logic in focused plain TypeScript modules.

## Commands

- Install: `pnpm install`
- Develop: `pnpm dev`
- Verify: `pnpm check && pnpm test && pnpm build`
- Format: `pnpm format`

## Working agreements

- Use strict TypeScript and avoid `any`.
- Keep tests focused on contracts and behavior; do not overbuild test scaffolding.
- Preserve the approved designs under `plans/`.
- Do not write source videos or runtime data into the repository.
- Run the narrowest relevant checks while iterating and the full verification command before completion.
```

- [ ] **Step 5: Add Svelte-specific agent guidance**

`apps/web/AGENTS.md`:

```markdown
# Cut on Eight web app

- Use the repository `svelte-code-writer` and `svelte-core-bestpractices` skills whenever creating, editing, or reviewing `.svelte`, `.svelte.ts`, or `.svelte.js` files.
- Use Svelte 5 runes mode for new code.
- Prefer `$state`, `$derived`, and `$props`; use `$effect` only for genuine side effects.
- Do not use legacy `$:`, `export let`, `on:click`, `<slot>`, or legacy component APIs.
- Use normal event attributes such as `onclick`.
- Keep reusable state and domain behavior in focused TypeScript modules.
- Run the `svelte-mcp svelte-autofixer` command with every changed Svelte file as its argument and target Svelte version 5 until it reports no remaining issues or suggestions.
- Run `pnpm --filter @cut-on-eight/web check` before completion.
```

- [ ] **Step 6: Verify the installed artifacts and MCP CLI**

Run:

```bash
pnpm exec svelte-mcp --version
pnpm exec svelte-mcp svelte-autofixer apps/web/src/App.svelte --svelte-version 5
rg -n "^name: svelte-(code-writer|core-bestpractices)$" .agents/skills/*/SKILL.md
```

Expected: the CLI prints a version; the autofixer reports no unresolved issues after any required corrections; both skill names are found.

- [ ] **Step 7: Commit AI artifacts**

```bash
git add cut_on_eight/.agents cut_on_eight/.codex cut_on_eight/AGENTS.md cut_on_eight/apps/web/AGENTS.md cut_on_eight/apps/web/src/App.svelte
git commit -m "chore: add repository-scoped Svelte AI tooling"
```

### Task 5: Document and verify the runnable hello-world workspace

**Files:**

- Create: `cut_on_eight/README.md`
- Modify only if verification requires a correction: files created in Tasks 1-4.

**Interfaces:**

- Consumes: all workspace commands and runtime endpoints created earlier.
- Produces: a documented, reproducible developer entrypoint and fresh evidence that the checkpoint works end to end.

- [ ] **Step 1: Write concise developer documentation**

`README.md`:

````markdown
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
````

- [ ] **Step 2: Run full static and automated verification**

```bash
pnpm format
pnpm check
pnpm test
pnpm build
```

Expected: all commands exit successfully; tests report the contract and server health cases passing; both application packages build.

- [ ] **Step 3: Start the stack without opening a browser**

```bash
CI=1 pnpm dev
```

Expected: contracts watch starts, Fastify listens on `http://127.0.0.1:4318`, and Vite listens on `http://127.0.0.1:5173`.

- [ ] **Step 4: Verify backend and proxied frontend access in another terminal**

```bash
curl --fail --silent http://127.0.0.1:4318/api/health
curl --fail --silent http://127.0.0.1:5173/
```

Expected health JSON:

```json
{"status":"ok","service":"cut-on-eight-server"}
```

Expected frontend response: HTML containing `<title>Cut on Eight</title>`.

- [ ] **Step 5: Manually verify browser rendering**

Run `pnpm dev` without `CI=1` and confirm the default browser opens once. Verify that the page shows **Cut on Eight** and **Backend connected: cut-on-eight-server**.

- [ ] **Step 6: Commit documentation and any verification fixes**

```bash
git add cut_on_eight
git commit -m "docs: add Cut on Eight developer quickstart"
```

- [ ] **Step 7: Confirm the checkpoint is clean**

```bash
git status --short --branch
git log --oneline -7
```

Expected: clean worktree and the planning plus workspace-bootstrap commits visible in history.
