<script lang="ts">
  let {
    visible,
    message,
    onUndo,
    onDismiss,
  }: {
    visible: boolean;
    message: string;
    onUndo: () => void;
    onDismiss: () => void;
  } = $props();
</script>

{#if visible}
  <aside class="undo-toast" role="status">
    <span>{message}</span>
    <button type="button" onclick={onUndo}>Undo</button>
    <button type="button" aria-label="Dismiss" onclick={onDismiss}>×</button>
  </aside>
{/if}
