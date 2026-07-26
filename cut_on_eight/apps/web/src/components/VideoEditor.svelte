<script lang="ts">
  import type {
    ProjectDocument,
    Segment,
    TagDefinition,
    ThumbnailManifestV1,
  } from '@cut-on-eight/legacy-contracts';
  import { onDestroy, onMount, untrack } from 'svelte';
  import type { Attachment } from 'svelte/attachments';
  import { sourceUrl } from '../lib/api.js';
  import type { RegisterVideoEditorControl } from '../lib/editor-control.js';
  import {
    resolveEditorKeyboardContext,
    shouldDelegateSegmentSurfaceActivation,
    shouldRouteEditorKeyboard,
  } from '../lib/editor-keyboard-context.js';
  import {
    createSegment,
    deleteMostRecentSegment,
    deleteSelectedSegment,
  } from '../lib/segments.js';
  import {
    beginContextPreview,
    clearSelection,
    createPlaybackState,
    onPlaybackTime,
    playbackFailure,
    seekBy,
    selectSegment as selectPlaybackSegment,
    type PlaybackDecision,
    type PlaybackState,
  } from '../lib/playback-controller.js';
  import {
    adjacentSegment,
    boundaryStep,
    escapeEditing,
    focusBoundary,
    nudgeBoundary,
    type BoundaryFocus,
  } from '../lib/trim-controller.js';
  import FragmentEditor from './FragmentEditor.svelte';
  import PrecisionTimeline, {
    type TimelineViewportChange,
  } from './PrecisionTimeline.svelte';
  import SegmentList from './SegmentList.svelte';

  let {
    project,
    onChange,
    onPlaybackSample,
    registerControl,
    onSave,
    segmentsCollapsed,
    onSegmentsCollapsedChange,
    onBoundaryModeChange,
    thumbnailManifest,
    thumbnailState,
    thumbnailRetrying,
    onRetryThumbnails,
    onThumbnailLoadError,
    tags,
    onCreateTag,
  }: {
    project: ProjectDocument;
    onChange: (
      projectId: string,
      mutate: (project: ProjectDocument) => ProjectDocument,
    ) => void;
    onPlaybackSample: (projectId: string, seconds: number) => void;
    registerControl: RegisterVideoEditorControl;
    onSave: () => void;
    segmentsCollapsed: boolean;
    onSegmentsCollapsedChange: (collapsed: boolean) => void;
    onBoundaryModeChange: (projectId: string, focused: boolean) => void;
    thumbnailManifest: ThumbnailManifestV1 | null;
    thumbnailState: 'generating' | 'ready' | 'failed';
    thumbnailRetrying: boolean;
    onRetryThumbnails: () => void;
    onThumbnailLoadError: () => void;
    tags: TagDefinition[];
    onCreateTag: (name: string) => Promise<TagDefinition>;
  } = $props();

  let editor = $state<HTMLElement>();
  let workbench = $state<HTMLElement>();
  let video = $state<HTMLVideoElement>();
  let currentSeconds = $state(untrack(() => project.playbackPositionSeconds));
  let mediaDuration = $state(
    untrack(() => project.source.durationSeconds ?? 0),
  );
  let pendingStartSeconds = $state<number | null>(null);
  let playing = $state(false);
  let interactionLocked = $state(false);
  let segmentError = $state<string | null>(null);
  let playbackError = $state<string | null>(null);
  let boundaryFocus = $state.raw<BoundaryFocus>(null);
  let playbackState = $state.raw<PlaybackState>(
    untrack(() => initialPlaybackState(project)),
  );
  let timelineZoom = $state(untrack(() => project.editor.timelineZoom));
  let timelineOffsetSeconds = $state(
    untrack(() => project.editor.timelineOffsetSeconds),
  );
  let animationFrame: number | null = null;
  let viewportPersistenceTimer: ReturnType<typeof setTimeout> | null = null;
  let playbackCommandSequence = 0;
  let lastPublishedSeconds = untrack(() => project.playbackPositionSeconds);

  const attachEditor: Attachment<HTMLElement> = (element) => {
    editor = element;
    return () => {
      if (editor === element) editor = undefined;
    };
  };

  const attachWorkbench: Attachment<HTMLElement> = (element) => {
    workbench = element;
    return () => {
      if (workbench === element) workbench = undefined;
    };
  };

  const attachVideo: Attachment<HTMLVideoElement> = (element) => {
    video = element;
    return () => {
      if (video === element) video = undefined;
    };
  };

  const displayDuration = $derived(
    mediaDuration > 0 ? mediaDuration : (project.source.durationSeconds ?? 0),
  );
  const selectedSegment = $derived(
    project.segments.find(
      (segment) => segment.id === project.selectedSegmentId,
    ) ?? null,
  );
  const frameStep = $derived(boundaryStep(project, false));
  const keyboardContext = $derived(
    resolveEditorKeyboardContext(project.selectedSegmentId, boundaryFocus),
  );

  onMount(() =>
    registerControl({
      projectId: project.id,
      prepareForSave,
      releaseAfterSave,
    }),
  );

  onDestroy(() => {
    stopSampling();
    materializeTimelineViewport();
    onBoundaryModeChange(project.id, false);
  });

  function initialPlaybackState(document: ProjectDocument): PlaybackState {
    const state = createPlaybackState(document.source.durationSeconds ?? 0);
    const selected = document.segments.find(
      (segment) => segment.id === document.selectedSegmentId,
    );
    return selected === undefined
      ? state
      : selectPlaybackSegment(state, selected).state;
  }

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
    materializeTimelineViewport();
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

  function clearViewportPersistenceTimer(): void {
    if (viewportPersistenceTimer === null) return;
    clearTimeout(viewportPersistenceTimer);
    viewportPersistenceTimer = null;
  }

  function updateTimelineViewport(viewport: TimelineViewportChange): void {
    timelineZoom = viewport.zoom;
    timelineOffsetSeconds = viewport.offsetSeconds;
    clearViewportPersistenceTimer();
    viewportPersistenceTimer = setTimeout(materializeTimelineViewport, 300);
  }

  function materializeTimelineViewport(): void {
    clearViewportPersistenceTimer();
    updateProject((current) =>
      Math.abs(current.editor.timelineZoom - timelineZoom) < 0.000_001 &&
      Math.abs(current.editor.timelineOffsetSeconds - timelineOffsetSeconds) <
        0.000_001
        ? current
        : {
            ...current,
            editor: {
              timelineZoom,
              timelineOffsetSeconds,
            },
          },
    );
  }

  function samplePlayback(): void {
    animationFrame = null;
    if (video === undefined || video.paused || video.ended) {
      stopSampling();
      return;
    }

    currentSeconds = video.currentTime;
    onPlaybackSample(project.id, currentSeconds);
    publishPosition();
    const decision = onPlaybackTime(playbackState, currentSeconds, true);
    if (decision.command.kind !== 'none') {
      void applyPlaybackDecision(decision);
      return;
    }
    animationFrame = requestAnimationFrame(samplePlayback);
  }

  function handlePlay(): void {
    if (interactionLocked) {
      video?.pause();
      return;
    }

    scheduleSampling();
  }

  function scheduleSampling(): void {
    if (
      video === undefined ||
      video.paused ||
      video.ended ||
      animationFrame !== null
    ) {
      return;
    }
    playing = true;
    animationFrame = requestAnimationFrame(samplePlayback);
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
    if (video?.ended !== true) {
      playbackState = { ...playbackState, preview: null };
    }
    onPlaybackSample(project.id, currentSeconds);
    stopSampling();
    publishPosition(true);
  }

  function restorePosition(): void {
    if (video === undefined || interactionLocked) return;

    if (Number.isFinite(video.duration) && video.duration > 0) {
      mediaDuration = video.duration;
      if (playbackState.scope.kind === 'source') {
        playbackState = createPlaybackState(video.duration);
      }
    }
    const upperBound = playbackState.scope.end || mediaDuration || Infinity;
    const restored = Math.min(
      Math.max(playbackState.scope.start, project.playbackPositionSeconds),
      upperBound,
    );
    video.currentTime = restored;
    currentSeconds = restored;
    onPlaybackSample(project.id, currentSeconds);
  }

  function setMediaPosition(seconds: number): void {
    if (video === undefined) throw new Error('Video is not ready.');
    const upperBound = displayDuration > 0 ? displayDuration : seconds;
    const position = Math.min(Math.max(0, seconds), upperBound);
    video.currentTime = position;
    currentSeconds = position;
    onPlaybackSample(project.id, currentSeconds);
    publishPosition(true);
  }

  async function applyPlaybackDecision(
    decision: PlaybackDecision,
  ): Promise<void> {
    const commandSequence = ++playbackCommandSequence;
    playbackState = decision.state;
    const command = decision.command;
    if (command.kind === 'none') return;

    try {
      if (command.kind === 'pause') {
        video?.pause();
        playbackError = command.error ?? null;
        return;
      }

      playbackError = null;
      if (command.kind === 'pause-and-seek') video?.pause();
      setMediaPosition(command.seconds);
      if (command.kind === 'seek-and-play') {
        await video?.play();
        if (commandSequence !== playbackCommandSequence) return;
        scheduleSampling();
      }
    } catch {
      if (commandSequence !== playbackCommandSequence) return;
      const failed = playbackFailure(
        playbackState,
        command.kind === 'seek-and-play'
          ? 'Playback could not start at the requested time.'
          : 'The video could not seek to the requested time.',
      );
      playbackState = failed.state;
      video?.pause();
      playbackError =
        failed.command.kind === 'pause' ? (failed.command.error ?? null) : null;
    }
  }

  function setBoundaryFocus(focus: BoundaryFocus): void {
    boundaryFocus = focus;
    segmentError = null;
    onBoundaryModeChange(project.id, focus !== null);
  }

  function selectSegment(segment: Segment): void {
    setBoundaryFocus(null);
    updateProject((current) => ({
      ...current,
      selectedSegmentId: segment.id,
    }));
    void applyPlaybackDecision(selectPlaybackSegment(playbackState, segment));
    queueMicrotask(() => focusSegmentSurface(segment.id));
  }

  function focusSegmentSurface(segmentId: string): void {
    const listSurface = editor?.querySelector<HTMLElement>(
      `[data-editor-playback-surface][data-segment-focus-id="${segmentId}"]`,
    );
    const surface =
      listSurface ??
      editor?.querySelector<HTMLElement>(
        `.segment-range[data-segment-focus-id="${segmentId}"]`,
      );
    surface?.focus({ preventScroll: true });
    surface?.scrollIntoView({ block: 'nearest' });
  }

  function clearSegmentSelection(
    seconds = currentSeconds,
    preservePlayback = false,
  ): void {
    setBoundaryFocus(null);
    updateProject((current) =>
      current.selectedSegmentId === null
        ? current
        : { ...current, selectedSegmentId: null },
    );
    const decision = clearSelection(playbackState, displayDuration, seconds);
    if (preservePlayback) playbackState = decision.state;
    else void applyPlaybackDecision(decision);
    workbench?.focus({ preventScroll: true });
  }

  function seek(seconds: number): void {
    void applyPlaybackDecision(
      seekBy(playbackState, currentSeconds, seconds - currentSeconds, playing),
    );
  }

  function nudgeFocusedBoundary(deltaSeconds: number): void {
    const result = nudgeBoundary(project, boundaryFocus, deltaSeconds);
    if (!result.ok) {
      segmentError = result.message;
      return;
    }

    segmentError = null;
    updateProject(() => result.project);
    const adjusted = result.project.segments.find(
      (segment) => segment.id === result.focus.segmentId,
    );
    if (adjusted !== undefined) {
      playbackState = selectPlaybackSegment(playbackState, adjusted).state;
    }
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

  function updateSegmentMetadata(
    segmentId: string,
    change: Pick<Segment, 'title' | 'tagIds' | 'exportSelected'>,
  ): void {
    updateProject((current) => ({
      ...current,
      segments: current.segments.map((segment) =>
        segment.id === segmentId ? { ...segment, ...change } : segment,
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
      const commandSequence = ++playbackCommandSequence;
      try {
        await video.play();
      } catch {
        if (commandSequence !== playbackCommandSequence) return;
        const failed = playbackFailure(
          playbackState,
          'Playback could not start at the requested time.',
        );
        playbackState = failed.state;
        playbackError =
          failed.command.kind === 'pause'
            ? (failed.command.error ?? null)
            : null;
      }
    } else {
      playbackCommandSequence += 1;
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

  function isNativeButtonActivation(event: KeyboardEvent): boolean {
    if (event.code !== 'Space' && event.key !== 'Enter') return false;
    if (!(event.target instanceof Element)) return false;

    const button = event.target.closest<HTMLButtonElement>('button');
    if (button === null) return false;

    return !shouldDelegateSegmentSurfaceActivation({
      key: event.code === 'Space' ? 'Space' : event.key,
      focusedSegmentId: button.dataset.segmentFocusId ?? null,
      selectedSegmentId: project.selectedSegmentId,
    });
  }

  function isSaveShortcut(event: KeyboardEvent): boolean {
    return (
      (event.metaKey || event.ctrlKey) &&
      !event.altKey &&
      event.key.toLowerCase() === 's'
    );
  }

  function handleWindowKeyboard(event: KeyboardEvent): void {
    if (interactionLocked || event.defaultPrevented) return;

    if (isSaveShortcut(event)) {
      event.preventDefault();
      onSave();
      return;
    }

    if (
      shouldRouteEditorKeyboard({
        focusWithinEditor: editor?.contains(document.activeElement) === true,
        nativeInput: isTextEntryTarget(event.target),
        nativeButtonActivation: isNativeButtonActivation(event),
      })
    ) {
      handleKeyboard(event);
    }
  }

  function handleKeyboard(event: KeyboardEvent): void {
    if (interactionLocked || event.defaultPrevented) return;

    if (event.metaKey || event.ctrlKey || event.altKey) return;

    if (event.code === 'Space') {
      event.preventDefault();
      void togglePlayback();
      return;
    }

    if (event.key === 'Escape') {
      const escaped = escapeEditing(project, boundaryFocus);
      if (escaped.focus !== boundaryFocus) {
        event.preventDefault();
        setBoundaryFocus(escaped.focus);
        const selectedId = project.selectedSegmentId;
        if (escaped.focus === null && selectedId !== null) {
          queueMicrotask(() => focusSegmentSurface(selectedId));
        }
        return;
      }
      if (escaped.project !== project) {
        event.preventDefault();
        clearSegmentSelection();
        return;
      }
      if (pendingStartSeconds !== null) {
        event.preventDefault();
        pendingStartSeconds = null;
      }
      return;
    }

    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      const direction = event.key === 'ArrowLeft' ? -1 : 1;
      if (boundaryFocus !== null) {
        nudgeFocusedBoundary(
          direction * boundaryStep(project, event.shiftKey).seconds,
        );
      } else {
        const seconds = event.shiftKey ? 10 : 1;
        void applyPlaybackDecision(
          seekBy(playbackState, currentSeconds, direction * seconds, playing),
        );
      }
      return;
    }

    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      const target = adjacentSegment(
        project,
        event.key === 'ArrowUp' ? 'previous' : 'next',
      );
      if (target !== null) {
        event.preventDefault();
        selectSegment(target);
      }
      return;
    }

    if (event.key === 'Enter' && project.selectedSegmentId !== null) {
      event.preventDefault();
      void applyPlaybackDecision(
        beginContextPreview(playbackState, displayDuration),
      );
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

    if (event.key === 'Delete' && project.selectedSegmentId !== null) {
      event.preventDefault();
      const decision = clearSelection(
        playbackState,
        displayDuration,
        currentSeconds,
      );
      setBoundaryFocus(null);
      updateProject(deleteSelectedSegment);
      void applyPlaybackDecision(decision);
      return;
    }

    if (event.key === 'Backspace' && project.segments.length > 0) {
      event.preventDefault();
      const mostRecent = project.segments.at(-1);
      if (mostRecent?.id === project.selectedSegmentId) {
        setBoundaryFocus(null);
        void applyPlaybackDecision(
          clearSelection(playbackState, displayDuration, currentSeconds),
        );
      }
      updateProject(deleteMostRecentSegment);
    }
  }

  function handleVideoClick(event: MouseEvent): void {
    workbench?.focus({ preventScroll: true });
    if (video === undefined || project.selectedSegmentId === null) return;
    const nativeControlsClick =
      event.offsetY >= Math.max(0, video.clientHeight - 48);
    clearSegmentSelection(currentSeconds, nativeControlsClick);
  }

  function handleEditorFocusIn(event: FocusEvent): void {
    if (!(event.target instanceof Element)) return;
    const surface = event.target.closest<HTMLElement>(
      '[data-segment-focus-id]',
    );
    const segmentId = surface?.dataset.segmentFocusId;
    if (segmentId === undefined || segmentId === project.selectedSegmentId) {
      return;
    }

    const segment = project.segments.find((item) => item.id === segmentId);
    if (segment !== undefined) selectSegment(segment);
  }

  function handleSeeked(): void {
    publishPosition(true);
    const decision = onPlaybackTime(
      playbackState,
      currentSeconds,
      video?.paused === false,
    );
    if (
      decision.command.kind !== 'none' &&
      !(
        'seconds' in decision.command &&
        Math.abs(decision.command.seconds - currentSeconds) < 0.001
      )
    ) {
      void applyPlaybackDecision(decision);
    }
  }

  function handleEnded(): void {
    stopSampling();
    if (video !== undefined) currentSeconds = video.currentTime;
    const decision = onPlaybackTime(playbackState, currentSeconds, true);
    if (decision.command.kind !== 'none') {
      void applyPlaybackDecision(decision);
      return;
    }
    handlePause();
  }
</script>

<svelte:window onkeydown={handleWindowKeyboard} />

<div
  class={['video-editor', segmentsCollapsed && 'segments-collapsed']}
  data-keyboard-context={keyboardContext.kind}
  inert={interactionLocked}
  aria-busy={interactionLocked}
  onfocusin={handleEditorFocusIn}
  {@attach attachEditor}
>
  <section class="video-workbench" aria-label="Video editor">
    <!-- This custom media surface intentionally owns keyboard playback commands. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <div
      class={[
        'media-workbench',
        keyboardContext.kind === 'source' && 'keyboard-owner',
      ]}
      role="region"
      aria-label="Video and timeline controls"
      tabindex="0"
      {@attach attachWorkbench}
    >
      <!-- User-selected source files do not include a separately managed caption track. -->
      <!-- svelte-ignore a11y_media_has_caption -->
      <video
        {@attach attachVideo}
        src={sourceUrl(project.id)}
        controls={!interactionLocked}
        preload="metadata"
        onloadedmetadata={restorePosition}
        onplay={handlePlay}
        onpause={handlePause}
        onended={handleEnded}
        onclick={handleVideoClick}
        onseeking={() => {
          if (video !== undefined) currentSeconds = video.currentTime;
        }}
        onseeked={handleSeeked}
      ></video>

      <div class="transport-summary" aria-live="off">
        <span>{currentSeconds.toFixed(2)}s / {displayDuration.toFixed(2)}s</span
        >
        <span>{playing ? 'Playing' : 'Paused'}</span>
        <span
          >{project.selectedSegmentId === null ? 'Full video' : 'Segment'}</span
        >
        <span class="keyboard-target" aria-hidden="true">Keyboard active</span>
        {#if pendingStartSeconds !== null}
          <span class="pending-label"
            >In: {pendingStartSeconds.toFixed(2)}s</span
          >
        {/if}
        {#if segmentError !== null}
          <span class="error-text" aria-live="polite">{segmentError}</span>
        {/if}
        {#if playbackError !== null}
          <span class="error-text" aria-live="polite">{playbackError}</span>
        {/if}
      </div>

      <PrecisionTimeline
        projectId={project.id}
        {thumbnailManifest}
        {thumbnailState}
        {thumbnailRetrying}
        {onRetryThumbnails}
        {onThumbnailLoadError}
        durationSeconds={displayDuration}
        {currentSeconds}
        {pendingStartSeconds}
        segments={project.segments}
        selectedSegmentId={project.selectedSegmentId}
        zoom={timelineZoom}
        offsetSeconds={timelineOffsetSeconds}
        onSelect={selectSegment}
        onSeek={seek}
        onClearSelectionAndSeek={clearSegmentSelection}
        onViewportInput={updateTimelineViewport}
      />

      {#if selectedSegment !== null}
        <FragmentEditor
          segment={selectedSegment}
          {tags}
          focus={boundaryFocus}
          frameSeconds={frameStep.seconds}
          approximate={frameStep.approximate}
          error={segmentError}
          onFocus={(edge) => setBoundaryFocus(focusBoundary(project, edge))}
          onNudge={nudgeFocusedBoundary}
          onMetadataChange={(change) =>
            updateSegmentMetadata(selectedSegment.id, change)}
          {onCreateTag}
        />
      {/if}
    </div>

    <div class="editor-controls">
      <label>
        <input
          type="checkbox"
          checked={project.settings.pauseAfterCreation}
          onchange={(event) =>
            togglePauseAfterCreation(event.currentTarget.checked)}
        />
        Pause after creating a segment
      </label>
      <button
        class="secondary-action"
        type="button"
        aria-expanded={!segmentsCollapsed}
        aria-controls="segment-panel"
        onclick={() => onSegmentsCollapsedChange(!segmentsCollapsed)}
      >
        {segmentsCollapsed ? 'Show' : 'Hide'} segments ({project.segments
          .length})
      </button>
    </div>
  </section>

  {#if !segmentsCollapsed}
    <div id="segment-panel">
      <SegmentList
        segments={project.segments}
        selectedSegmentId={project.selectedSegmentId}
        onSelect={selectSegment}
        onToggleExport={toggleExport}
      />
    </div>
  {/if}
</div>
