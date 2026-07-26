<script lang="ts">
  import type { TagDefinition } from '@cut-on-eight/legacy-contracts';
  import type { Segment } from '../domain/editor-model.js';
  import type { BoundaryFocus } from '../lib/trim-controller.js';
  import BoundaryEditor from './BoundaryEditor.svelte';

  let {
    segment,
    tags,
    focus,
    frameSeconds,
    approximate,
    error,
    onFocus,
    onNudge,
    onMetadataChange,
    onCreateTag,
  }: {
    segment: Segment;
    tags: TagDefinition[];
    focus: BoundaryFocus;
    frameSeconds: number;
    approximate: boolean;
    error: string | null;
    onFocus: (edge: 'start' | 'end') => void;
    onNudge: (deltaSeconds: number) => void;
    onMetadataChange: (change: {
      title: string | null;
      tagIds: string[];
      exportSelected: boolean;
    }) => void;
    onCreateTag: (name: string) => Promise<TagDefinition>;
  } = $props();

  let tagInput = $state('');
  let creatingTag = $state(false);

  const assignedTags = $derived(
    tags.filter((tag) => segment.tagIds.includes(tag.id)),
  );
  const availableTags = $derived(
    tags.filter(
      (tag) =>
        !segment.tagIds.includes(tag.id) &&
        tag.name.includes(tagInput.trim().toLowerCase()),
    ),
  );

  function update(
    change: Partial<Pick<Segment, 'title' | 'tagIds' | 'exportSelected'>>,
  ): void {
    onMetadataChange({
      title: segment.title,
      tagIds: segment.tagIds,
      exportSelected: segment.exportSelected,
      ...change,
    });
  }

  async function submitTag(): Promise<void> {
    const name = tagInput.trim().toLowerCase();
    if (name === '' || creatingTag) return;
    const existing = tags.find((tag) => tag.name === name);
    creatingTag = true;
    try {
      const tag = existing ?? (await onCreateTag(name));
      if (!segment.tagIds.includes(tag.id))
        update({ tagIds: [...segment.tagIds, tag.id] });
      tagInput = '';
    } finally {
      creatingTag = false;
    }
  }
</script>

<section class="fragment-editor" aria-label="Fragment editor">
  <BoundaryEditor
    {segment}
    {focus}
    {frameSeconds}
    {approximate}
    {error}
    {onFocus}
    {onNudge}
  />

  <label class="fragment-title">
    <span>Title</span>
    <input
      value={segment.title ?? ''}
      placeholder="Optional fragment title"
      onchange={(event) =>
        update({ title: event.currentTarget.value.trim() || null })}
    />
  </label>

  <div class="tag-editor">
    <span>Tags</span>
    <div class="tag-chips">
      {#each assignedTags as tag (tag.id)}
        <button
          type="button"
          class="tag-chip"
          title={`Remove ${tag.name}`}
          onclick={() =>
            update({ tagIds: segment.tagIds.filter((id) => id !== tag.id) })}
          >{tag.name} ×</button
        >
      {/each}
    </div>
    <div class="tag-entry">
      <input
        bind:value={tagInput}
        list={`tags-${segment.id}`}
        placeholder="add tag"
        onkeydown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            void submitTag();
          }
        }}
      />
      <datalist id={`tags-${segment.id}`}>
        {#each availableTags as tag (tag.id)}<option value={tag.name}
          ></option>{/each}
      </datalist>
      <button
        type="button"
        disabled={creatingTag || tagInput.trim() === ''}
        onclick={() => void submitTag()}
      >
        {creatingTag ? 'Adding…' : 'Add'}
      </button>
    </div>
  </div>

  <label class="export-choice">
    <input
      type="checkbox"
      checked={segment.exportSelected}
      onchange={(event) =>
        update({ exportSelected: event.currentTarget.checked })}
    />
    Export
  </label>
</section>
