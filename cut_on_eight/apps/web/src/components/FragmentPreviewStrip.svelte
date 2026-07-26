<script lang="ts">
  import type { FragmentPreview } from '../domain/catalogue-model.js';
  import type { Attachment } from 'svelte/attachments';

  let { previews }: { previews: FragmentPreview[] } = $props();
  let visible = $state(false);

  const observeVisibility: Attachment<HTMLElement> = (element) => {
    if (typeof IntersectionObserver === 'undefined') {
      visible = true;
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          visible = true;
          observer.disconnect();
        }
      },
      { rootMargin: '240px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  };
</script>

<div
  class="fragment-preview-strip"
  {@attach observeVisibility}
  aria-label="Fragment preview frames"
>
  {#if previews.length === 0}
    <div class="preview-placeholder">Thumbnails unavailable</div>
  {:else}
    {#each previews as preview (`${preview.pageFileName}:${preview.x}:${preview.y}`)}
      <div class="fragment-preview-frame">
        {#if visible}
          <img
            src={preview.href ?? ''}
            alt=""
            loading="lazy"
            style:width={`${(preview.pageWidth / preview.width) * 100}%`}
            style:height={`${(preview.pageHeight / preview.height) * 100}%`}
            style:left={`${(-preview.x / preview.width) * 100}%`}
            style:top={`${(-preview.y / preview.height) * 100}%`}
          />
        {/if}
      </div>
    {/each}
  {/if}
</div>
