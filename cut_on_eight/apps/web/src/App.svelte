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
        message:
          error instanceof Error ? error.message : 'Unknown backend error',
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
