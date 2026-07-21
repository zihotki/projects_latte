<script lang="ts">
  type ServiceState = 'checking' | 'ready' | 'unavailable';

  let {
    backendState,
    ffprobeState,
    jobsLabel,
    importing,
    onImport,
  }: {
    backendState: ServiceState;
    ffprobeState: ServiceState;
    jobsLabel: string;
    importing: boolean;
    onImport: () => void;
  } = $props();
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
        data-state={jobsLabel === 'idle' ? 'ready' : 'checking'}
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
