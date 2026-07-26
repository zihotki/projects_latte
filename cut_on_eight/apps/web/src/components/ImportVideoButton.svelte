<script lang="ts">
  let {
    importing = false,
    onImport,
  }: {
    importing?: boolean;
    onImport: (file: File) => void | Promise<void>;
  } = $props();

  let input: HTMLInputElement;

  function openPicker(): void {
    input.value = '';
    input.click();
  }

  function choose(event: Event): void {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (file !== undefined) void onImport(file);
  }
</script>

<input
  bind:this={input}
  class="visually-hidden"
  type="file"
  accept="video/mp4,.mp4"
  onchange={choose}
/>
<button
  class="primary-action"
  type="button"
  disabled={importing}
  onclick={openPicker}
>
  {importing ? 'Importing…' : 'Import MP4'}
</button>
