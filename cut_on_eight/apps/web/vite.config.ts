import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

const backendPort = process.env.CUT_ON_EIGHT_PORT ?? '4318';

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '127.0.0.1',
    open: process.env.CI !== '1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
    },
  },
});
