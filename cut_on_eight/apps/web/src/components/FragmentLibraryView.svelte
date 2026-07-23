<script lang="ts">
  import type { FragmentLibrary } from '../app/fragment-library.svelte.js';
  import FragmentsPanel from './FragmentsPanel.svelte';

  let { fragments }: { fragments: FragmentLibrary } = $props();
</script>

<FragmentsPanel
  catalogue={fragments.catalogue}
  loading={fragments.loading}
  error={fragments.error}
  onRefresh={() => void fragments.refresh()}
  onUpdate={(projectId, fragmentId, mutation) =>
    fragments.mutateFragment(projectId, fragmentId, mutation)}
  onCreateTag={(name) => fragments.createTag(name)}
  onDelete={(projectId, fragmentId) =>
    fragments.removeFragment(projectId, fragmentId)}
  onRestore={(deleted) => fragments.restoreDeletedFragment(deleted)}
  onRetryThumbnail={(jobId) => void fragments.retryThumbnail(jobId)}
/>
