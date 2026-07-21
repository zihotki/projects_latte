<script lang="ts">
  import type { ProjectDocument, Segment } from '@cut-on-eight/contracts';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { sourceUrl } from '../lib/api.js';
  import type { RegisterVideoEditorControl } from '../lib/editor-control.js';
  import {
    createSegment,
    deleteMostRecentSegment,
    deleteSelectedSegment,
  } from '../lib/segments.js';
  import BasicTimeline from './BasicTimeline.svelte';
  import SegmentList from './SegmentList.svelte';

  let {
    project,
    onChange,
    onPlaybackSample,
    registerControl,
    onSave,
  }: {
    project: ProjectDocument;
    onChange: (
      projectId: string,
      mutate: (project: ProjectDocument) => ProjectDocument,
    ) => void;
    onPlaybackSample: (projectId: string, seconds: number) => void;
    registerControl: RegisterVideoEditorControl;
    onSave: () => void;
  } = $props();

  let video = $state<HTMLVideoElement>();
  let currentSeconds = $state(untrack(() => project.playbackPositionSeconds));
  let mediaDuration = $state(
    untrack(() => project.source.durationSeconds ?? 0),
  );
  let pendingStartSeconds = $state<number | null>(null);
  let playing = $state(false);
  let interactionLocked = $state(false);
  let segmentError = $state<string | null>(null);
  let animationFrame: number | null = null;
  let lastPublishedSeconds = untrack(() => project.playbackPositionSeconds);

  const displayDuration = $derived(
    mediaDuration > 0 ? mediaDuration : (project.source.durationSeconds ?? 0),
  );

  onMount(() =>
    registerControl({
      projectId: project.id,
      prepareForSave,
      releaseAfterSave,
    }),
  );

  onDestroy(stopSampling);

  function updateProject(
    mutate: (project: ProjectDocument) => ProjectDocument,
  ): void {
    onChange(project.id, mutate);
  }

  function publishPosition(force = false): void {
    const position = Math.max(0, currentSeconds);
    if (!force && Math.abs(position - lastPublishedSeconds) < 0.5) return;
    if (Math.abs(position - project.playbackPositionSeconds) < 0.01) return;

    lastPublishedSeconds = position;
    materializePosition(position);
  }

  function materializePosition(position: number): void {
    updateProject((current) =>
      Math.abs(current.playbackPositionSeconds - position) < 0.01
        ? current
        : { ...current, playbackPositionSeconds: position },
    );
  }

  function prepareForSave(): void {
    interactionLocked = true;
    stopSampling();
    video?.pause();
    if (video !== undefined) video.controls = false;
    if (video !== undefined) currentSeconds = video.currentTime;

    const position = Math.max(0, currentSeconds);
    onPlaybackSample(project.id, position);
    lastPublishedSeconds = position;
    materializePosition(position);
  }

  function releaseAfterSave(): void {
    interactionLocked = false;
    if (video !== undefined) video.controls = true;
  }

  function samplePlayback(): void {
    if (video === undefined || video.paused || video.ended) {
      stopSampling();
      return;
    }

    currentSeconds = video.currentTime;
    onPlaybackSample(project.id, currentSeconds);
    publishPosition();
    animationFrame = requestAnimationFrame(samplePlayback);
  }

  function handlePlay(): void {
    if (interactionLocked) {
      video?.pause();
      return;
    }

    playing = true;
    if (animationFrame === null) {
      animationFrame = requestAnimationFrame(samplePlayback);
    }
  }

  function stopSampling(): void {
    playing = false;
    if (animationFrame !== null) {
      cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }
  }

  function handlePause(): void {
    if (video !== undefined) currentSeconds = video.currentTime;
    onPlaybackSample(project.id, currentSeconds);
    stopSampling();
    publishPosition(true);
  }

  function restorePosition(): void {
    if (video === undefined || interactionLocked) return;

    if (Number.isFinite(video.duration) && video.duration > 0) {
      mediaDuration = video.duration;
    }
    const upperBound = mediaDuration > 0 ? mediaDuration : Infinity;
    const restored = Math.min(project.playbackPositionSeconds, upperBound);
    video.currentTime = restored;
    currentSeconds = restored;
    onPlaybackSample(project.id, currentSeconds);
  }

  function seek(seconds: number): void {
    if (video === undefined) return;
    const upperBound = displayDuration > 0 ? displayDuration : seconds;
    const position = Math.min(Math.max(0, seconds), upperBound);
    video.currentTime = position;
    currentSeconds = position;
    onPlaybackSample(project.id, currentSeconds);
    publishPosition(true);
  }

  function selectSegment(segment: Segment): void {
    updateProject((current) => ({
      ...current,
      selectedSegmentId: segment.id,
    }));
    seek(segment.startSeconds);
  }

  function toggleExport(segmentId: string, selected: boolean): void {
    updateProject((current) => ({
      ...current,
      segments: current.segments.map((segment) =>
        segment.id === segmentId
          ? { ...segment, exportSelected: selected }
          : segment,
      ),
    }));
  }

  function togglePauseAfterCreation(checked: boolean): void {
    updateProject((current) => ({
      ...current,
      settings: { ...current.settings, pauseAfterCreation: checked },
    }));
  }

  async function togglePlayback(): Promise<void> {
    if (video === undefined) return;
    if (video.paused) {
      try {
        await video.play();
      } catch {
        // The native player remains authoritative when playback is unavailable.
      }
    } else {
      video.pause();
    }
  }

  function isTextEntryTarget(target: EventTarget | null): boolean {
    return (
      target instanceof Element &&
      target.closest(
        'input, textarea, select, [contenteditable]:not([contenteditable="false"])',
      ) !== null
    );
  }

  function handleKeyboard(event: KeyboardEvent): void {
    if (interactionLocked || isTextEntryTarget(event.target)) return;

    const saveShortcut =
      (event.metaKey || event.ctrlKey) &&
      !event.altKey &&
      event.key.toLowerCase() === 's';
    if (saveShortcut) {
      event.preventDefault();
      onSave();
      return;
    }

    if (event.metaKey || event.ctrlKey || event.altKey) return;

    if (event.code === 'Space') {
      event.preventDefault();
      void togglePlayback();
      return;
    }

    if (event.key.toLowerCase() === 'i') {
      event.preventDefault();
      pendingStartSeconds = currentSeconds;
      segmentError = null;
      return;
    }

    if (event.key.toLowerCase() === 'o') {
      if (
        pendingStartSeconds === null ||
        currentSeconds <= pendingStartSeconds
      ) {
        return;
      }

      event.preventDefault();
      const segmentStart = pendingStartSeconds;
      pendingStartSeconds = null;
      let created = false;
      updateProject((current) => {
        const result = createSegment(
          current,
          segmentStart,
          currentSeconds,
          displayDuration,
        );
        segmentError = result.ok ? null : result.message;
        created = result.ok;
        return result.state;
      });
      if (created && project.settings.pauseAfterCreation) video?.pause();
      return;
    }

    if (event.key === 'Escape' && pendingStartSeconds !== null) {
      event.preventDefault();
      pendingStartSeconds = null;
      return;
    }

    if (event.key === 'Delete' && project.selectedSegmentId !== null) {
      event.preventDefault();
      updateProject(deleteSelectedSegment);
      return;
    }

    if (event.key === 'Backspace' && project.segments.length > 0) {
      event.preventDefault();
      updateProject(deleteMostRecentSegment);
    }
  }
</script>

<svelte:window onkeydown={handleKeyboard} />

<div
  class="video-editor"
  inert={interactionLocked}
  aria-busy={interactionLocked}
>
  <section class="video-workbench" aria-label="Video editor">
    <!-- User-selected source files do not include a separately managed caption track. -->
    <!-- svelte-ignore a11y_media_has_caption -->
    <video
      bind:this={video}
      src={sourceUrl(project.id)}
      controls={!interactionLocked}
      preload="metadata"
      onloadedmetadata={restorePosition}
      onplay={handlePlay}
      onpause={handlePause}
      onended={handlePause}
      onseeking={() => {
        if (video !== undefined) currentSeconds = video.currentTime;
      }}
      onseeked={() => publishPosition(true)}
    ></video>

    <div class="transport-summary" aria-live="off">
      <span>{currentSeconds.toFixed(2)}s / {displayDuration.toFixed(2)}s</span>
      <span>{playing ? 'Playing' : 'Paused'}</span>
      {#if pendingStartSeconds !== null}
        <span class="pending-label">In: {pendingStartSeconds.toFixed(2)}s</span>
      {/if}
      {#if segmentError !== null}
        <span class="error-text" aria-live="polite">{segmentError}</span>
      {/if}
    </div>

    <BasicTimeline
      durationSeconds={displayDuration}
      {currentSeconds}
      {pendingStartSeconds}
      segments={project.segments}
      selectedSegmentId={project.selectedSegmentId}
      onSelect={selectSegment}
      onSeek={seek}
    />

    <div class="editor-controls">
      <span><kbd>Space</kbd> play · <kbd>I</kbd> in · <kbd>O</kbd> out</span>
      <label>
        <input
          type="checkbox"
          checked={project.settings.pauseAfterCreation}
          onchange={(event) =>
            togglePauseAfterCreation(event.currentTarget.checked)}
        />
        Pause after creating a segment
      </label>
    </div>
  </section>

  <SegmentList
    segments={project.segments}
    selectedSegmentId={project.selectedSegmentId}
    onSelect={selectSegment}
    onToggleExport={toggleExport}
  />
</div>
