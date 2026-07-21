<script lang="ts">
  import type { JobCounts } from '../lib/job-events.js';

  type ServiceState = 'checking' | 'ready' | 'unavailable';

  let {
    backendState,
    ffprobeState,
    jobCounts,
    importing,
    onImport,
  }: {
    backendState: ServiceState;
    ffprobeState: ServiceState;
    jobCounts: JobCounts | null;
    importing: boolean;
    onImport: () => void;
  } = $props();

  const jobsLabel = $derived(
    jobCounts === null
      ? 'checking'
      : `${jobCounts.queued} queued · ${jobCounts.running} running · ${jobCounts.completed} done · ${jobCounts.failed} failed`,
  );
</script>

<header class="app-bar">
  <div class="brand">
    <span class="brand-mark" aria-hidden="true">8</span>
    <div>
      <p class="eyebrow">Local video workspace</p>
      <h1>Cut on Eight</h1>
    </div>
  </div>

  <div class="app-actions">
    <div class="service-states" aria-label="Service status">
      <span class="service-state" data-state={backendState}
        >Backend: {backendState}</span
      >
      <span class="service-state" data-state={ffprobeState}
        >FFprobe: {ffprobeState}</span
      >
      <span
        class="service-state"
        data-state={jobCounts === null
          ? 'checking'
          : jobCounts.failed > 0
            ? 'unavailable'
            : jobCounts.queued + jobCounts.running === 0
              ? 'ready'
              : 'checking'}
      >
        Jobs: {jobsLabel}
      </span>
    </div>
    <button
      class="primary-action"
      type="button"
      onclick={onImport}
      disabled={importing}
    >
      {importing ? 'Selecting…' : 'Import MP4'}
    </button>
  </div>
</header>
