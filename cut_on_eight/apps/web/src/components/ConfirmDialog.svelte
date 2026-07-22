<script lang="ts">
  let {
    open,
    title,
    confirmLabel,
    busy,
    onConfirm,
    onCancel,
    children,
  }: {
    open: boolean;
    title: string;
    confirmLabel: string;
    busy: boolean;
    onConfirm: () => void;
    onCancel: () => void;
    children: import('svelte').Snippet;
  } = $props();
</script>

{#if open}
  <div class="dialog-backdrop" role="presentation">
    <div
      class="confirm-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <h2 id="confirm-title">{title}</h2>
      {@render children()}
      <div class="dialog-actions">
        <button
          class="secondary-action"
          type="button"
          disabled={busy}
          onclick={onCancel}>Cancel</button
        >
        <button
          class="danger-action"
          type="button"
          disabled={busy}
          onclick={onConfirm}
        >
          {busy ? 'Deleting…' : confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}
