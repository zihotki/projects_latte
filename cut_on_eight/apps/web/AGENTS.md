# Cut on Eight web app

- Use the repository `svelte-code-writer` and `svelte-core-bestpractices` skills whenever creating, editing, or reviewing `.svelte`, `.svelte.ts`, or `.svelte.js` files.
- Use Svelte 5 runes mode for new code.
- Prefer `$state`, `$derived`, and `$props`; use `$effect` only for genuine side effects.
- Do not use legacy `$:`, `export let`, `on:click`, `<slot>`, or legacy component APIs.
- Use normal event attributes such as `onclick`.
- Keep reusable state and domain behavior in focused TypeScript modules.
- Run the `svelte-mcp svelte-autofixer` command with every changed Svelte file as its argument and target Svelte version 5 until it reports no remaining issues or suggestions.
- Run `pnpm --filter @cut-on-eight/web check` before completion.
