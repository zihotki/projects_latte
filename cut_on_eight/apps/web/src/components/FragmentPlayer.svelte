<script lang="ts">
  import type { FragmentSummary } from '@cut-on-eight/contracts';
  import { sourceUrl } from '../lib/api.js';
  import { fragmentLabel } from '../lib/fragment-catalogue.js';
  import type { Attachment } from 'svelte/attachments';

  let {
    fragment,
    onClose,
  }: {
    fragment: FragmentSummary | null;
    onClose: () => void;
  } = $props();

  let mode = $state<'floating' | 'collapsed' | 'expanded'>('floating');
  let video = $state<HTMLVideoElement>();
  let playbackError = $state<string | null>(null);
  let animationFrame: number | null = null;

  function stopSampling(): void {
    if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    animationFrame = null;
  }

  function samplePlayback(): void {
    if (video === undefined || fragment === null || video.paused) {
      stopSampling();
      return;
    }
    if (
      video.currentTime >= fragment.segment.endSeconds - 0.001 ||
      video.currentTime < fragment.segment.startSeconds
    ) {
      video.currentTime = fragment.segment.startSeconds;
    }
    animationFrame = requestAnimationFrame(samplePlayback);
  }

  function startSampling(): void {
    stopSampling();
    animationFrame = requestAnimationFrame(samplePlayback);
  }

  const attachVideo: Attachment<HTMLVideoElement> = (element) => {
    video = element;
    return () => {
      stopSampling();
      if (video === element) video = undefined;
    };
  };

  async function start(): Promise<void> {
    if (video === undefined || fragment === null) return;
    video.currentTime = fragment.segment.startSeconds;
    try {
      await video.play();
      startSampling();
      playbackError = null;
    } catch {
      playbackError = 'Playback could not start.';
    }
  }

  function keepInRange(): void {
    if (video === undefined || fragment === null) return;
    if (
      video.currentTime >= fragment.segment.endSeconds ||
      video.currentTime < fragment.segment.startSeconds
    ) {
      video.currentTime = fragment.segment.startSeconds;
      if (!video.paused) void video.play();
    }
  }
</script>

{#if fragment !== null}
  <aside
    class={['fragment-player', `player-${mode}`]}
    aria-label="Fragment player"
  >
    <header>
      <strong>{fragmentLabel(fragment)}</strong>
      <div>
        <button
          type="button"
          onclick={() =>
            (mode = mode === 'collapsed' ? 'floating' : 'collapsed')}
        >
          {mode === 'collapsed' ? 'Show' : 'Minimize'}
        </button>
        <button
          type="button"
          onclick={() => (mode = mode === 'expanded' ? 'floating' : 'expanded')}
        >
          {mode === 'expanded' ? 'Float' : 'Expand'}
        </button>
        <button type="button" aria-label="Close player" onclick={onClose}
          >×</button
        >
      </div>
    </header>
    <div class="fragment-player-content">
      {#key fragment.segment.id}
        <!-- Managed local videos do not include a separate caption track. -->
        <!-- svelte-ignore a11y_media_has_caption -->
        <video
          {@attach attachVideo}
          src={sourceUrl(fragment.projectId)}
          controls
          preload="metadata"
          onloadedmetadata={() => void start()}
          onplay={startSampling}
          onpause={stopSampling}
          ontimeupdate={keepInRange}
          onended={() => void start()}
        ></video>
      {/key}
      <p>
        {fragment.segment.startSeconds.toFixed(
          2,
        )}–{fragment.segment.endSeconds.toFixed(2)}s · loops
      </p>
      {#if playbackError !== null}<p class="error-text">{playbackError}</p>{/if}
    </div>
  </aside>
{/if}
