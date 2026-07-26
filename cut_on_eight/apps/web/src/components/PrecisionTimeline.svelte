<script lang="ts">
  import type {
    Segment,
    ThumbnailManifestV1,
  } from '@cut-on-eight/legacy-contracts';
  import { thumbnailPageUrl } from '../lib/api.js';
  import { segmentDurationStatus } from '../lib/segment-constraints.js';
  import { TimeScale } from '../lib/timeline-geometry.js';
  import {
    ensureRangeVisible,
    fitSource,
    panByPixels,
    zoomAt,
  } from '../lib/timeline-viewport.js';
  import { assignSegmentRows } from '../lib/two-row-layout.js';
  import {
    drawVisibleThumbnails,
    loadBrowserImage,
    ThumbnailImageCache,
    visibleThumbnailPageIndexes,
  } from '../lib/thumbnail-renderer.js';

  export interface TimelineViewportChange {
    readonly offsetSeconds: number;
    readonly zoom: number;
  }

  let {
    durationSeconds,
    currentSeconds,
    pendingStartSeconds,
    segments,
    selectedSegmentId,
    zoom,
    offsetSeconds,
    onSelect,
    onSeek,
    onClearSelectionAndSeek,
    onViewportInput,
    projectId,
    thumbnailManifest,
    thumbnailState,
    thumbnailRetrying,
    onRetryThumbnails,
    onThumbnailLoadError,
  }: {
    durationSeconds: number;
    currentSeconds: number;
    pendingStartSeconds: number | null;
    segments: Segment[];
    selectedSegmentId: string | null;
    zoom: number;
    offsetSeconds: number;
    onSelect: (segment: Segment) => void;
    onSeek: (seconds: number) => void;
    onClearSelectionAndSeek: (seconds: number) => void;
    onViewportInput: (viewport: TimelineViewportChange) => void;
    projectId: string;
    thumbnailManifest: ThumbnailManifestV1 | null;
    thumbnailState: 'generating' | 'ready' | 'failed';
    thumbnailRetrying: boolean;
    onRetryThumbnails: () => void;
    onThumbnailLoadError: () => void;
  } = $props();

  let viewportWidth = $state(0);
  let canvas = $state<HTMLCanvasElement>();
  let lastEnsuredSegmentId: string | null = null;
  let thumbnailPaintVersion = 0;
  const thumbnailImages = new ThumbnailImageCache(loadBrowserImage);

  const scale = $derived(
    new TimeScale({
      durationSeconds,
      offsetSeconds,
      viewportWidth,
      zoom,
    }),
  );
  const rowResult = $derived(assignSegmentRows(segments));
  const selectedSegment = $derived(
    segments.find((segment) => segment.id === selectedSegmentId) ?? null,
  );

  $effect(() => {
    if (selectedSegment === null) {
      lastEnsuredSegmentId = null;
      return;
    }
    if (viewportWidth === 0 || selectedSegment.id === lastEnsuredSegmentId) {
      return;
    }
    lastEnsuredSegmentId = selectedSegment.id;
    applyViewport(
      ensureRangeVisible(
        scale,
        selectedSegment.startSeconds,
        selectedSegment.endSeconds,
      ),
    );
  });

  $effect(() => {
    const element = canvas;
    const manifest = thumbnailManifest;
    const currentScale = scale;
    const width = viewportWidth;
    const version = ++thumbnailPaintVersion;

    if (element === undefined || width <= 0) return;
    paintThumbnailBackground(element, null, null, currentScale, width);
    if (manifest === null || thumbnailState !== 'ready') {
      thumbnailImages.deactivate();
      return;
    }

    const pageIndexes = visibleThumbnailPageIndexes(manifest, currentScale);
    void thumbnailImages
      .loadVisible(projectId, manifest, pageIndexes, (fileName) =>
        thumbnailPageUrl(
          projectId,
          fileName,
          `${manifest.generatorVersion}:${manifest.sourceFingerprint}`,
        ),
      )
      .then((result) => {
        if (result === null || version !== thumbnailPaintVersion) return;
        if (result.failed > 0) {
          onThumbnailLoadError();
          return;
        }
        paintThumbnailBackground(
          element,
          manifest,
          result.images,
          currentScale,
          width,
        );
      });
  });

  function paintThumbnailBackground(
    element: HTMLCanvasElement,
    manifest: ThumbnailManifestV1 | null,
    images: ReadonlyMap<number, HTMLImageElement> | null,
    currentScale: TimeScale,
    width: number,
  ): void {
    const height = Math.max(1, element.clientHeight);
    const density = window.devicePixelRatio || 1;
    element.width = Math.max(1, Math.round(width * density));
    element.height = Math.max(1, Math.round(height * density));
    const context = element.getContext('2d');
    if (context === null) return;
    context.setTransform(density, 0, 0, density, 0, 0);
    context.fillStyle = '#242931';
    context.fillRect(0, 0, width, height);
    if (manifest !== null && images !== null) {
      drawVisibleThumbnails(context, manifest, images, currentScale, {
        width,
        height,
      });
    }
  }

  function applyViewport(next: TimeScale): void {
    if (
      Math.abs(next.zoom - zoom) < 0.000_001 &&
      Math.abs(next.offsetSeconds - offsetSeconds) < 0.000_001
    ) {
      return;
    }
    onViewportInput({
      zoom: next.zoom,
      offsetSeconds: next.offsetSeconds,
    });
  }

  function seekFromPointer(event: MouseEvent): void {
    if (durationSeconds <= 0 || !(event.currentTarget instanceof HTMLElement)) {
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    onClearSelectionAndSeek(scale.pixelToTime(event.clientX - bounds.left));
  }

  function seekFromKeyboard(event: KeyboardEvent): void {
    const target =
      event.key === 'Home' ? 0 : event.key === 'End' ? durationSeconds : null;
    if (target === null) return;

    event.preventDefault();
    onSeek(target);
  }

  function handleWheel(event: WheelEvent): void {
    if (viewportWidth === 0) return;

    if (event.metaKey || event.ctrlKey) {
      if (!(event.currentTarget instanceof HTMLElement)) return;
      event.preventDefault();
      const bounds = event.currentTarget.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * 0.002);
      applyViewport(
        zoomAt(scale, scale.zoom * factor, event.clientX - bounds.left),
      );
      return;
    }

    if (scale.zoom <= 1) return;
    const deltaPixels = event.deltaX !== 0 ? event.deltaX : event.deltaY;
    if (deltaPixels === 0) return;
    event.preventDefault();
    applyViewport(panByPixels(scale, deltaPixels));
  }

  function zoomAroundPlayhead(factor: number): void {
    const withVisiblePlayhead = ensureRangeVisible(
      scale,
      currentSeconds,
      currentSeconds,
    );
    applyViewport(
      zoomAt(
        withVisiblePlayhead,
        withVisiblePlayhead.zoom * factor,
        withVisiblePlayhead.timeToPixel(currentSeconds),
      ),
    );
  }
</script>

<div class="precision-timeline">
  <div class="timeline-toolbar" aria-label="Timeline view controls">
    <span
      >{scale.visibleRange().startSeconds.toFixed(1)}–{scale
        .visibleRange()
        .endSeconds.toFixed(1)}s</span
    >
    {#if thumbnailState === 'generating'}
      <span class="thumbnail-status">Thumbnails…</span>
    {:else if thumbnailState === 'failed'}
      <span class="thumbnail-status" data-state="failed">No thumbnails</span>
      <button
        type="button"
        disabled={thumbnailRetrying}
        onclick={onRetryThumbnails}
        >{thumbnailRetrying ? 'Retrying…' : 'Retry'}</button
      >
    {/if}
    <button
      type="button"
      aria-label="Zoom timeline out"
      disabled={scale.zoom <= 1}
      onclick={() => zoomAroundPlayhead(0.5)}>−</button
    >
    <button
      type="button"
      aria-label="Zoom timeline in"
      onclick={() => zoomAroundPlayhead(2)}>+</button
    >
    <button
      type="button"
      disabled={scale.zoom <= 1 && scale.offsetSeconds === 0}
      onclick={() => applyViewport(fitSource(durationSeconds, viewportWidth))}
      >Fit</button
    >
  </div>

  <div
    class="timeline-viewport"
    bind:clientWidth={viewportWidth}
    onwheel={handleWheel}
  >
    <canvas bind:this={canvas} class="timeline-canvas" aria-hidden="true"
    ></canvas>
    <div
      class="timeline-lane"
      role="slider"
      tabindex="0"
      aria-label="Video timeline"
      aria-valuemin="0"
      aria-valuemax={Math.max(0, durationSeconds)}
      aria-valuenow={Math.min(currentSeconds, Math.max(0, durationSeconds))}
      onclick={seekFromPointer}
      onkeydown={seekFromKeyboard}
    >
      {#if pendingStartSeconds !== null}
        {@const pendingLeft = scale.timeToPixel(
          Math.min(pendingStartSeconds, currentSeconds),
        )}
        <span
          class="pending-range"
          style:left={`${pendingLeft}px`}
          style:width={`${Math.abs(scale.timeToPixel(currentSeconds) - scale.timeToPixel(pendingStartSeconds))}px`}
          aria-hidden="true"
        ></span>
      {/if}

      {#if rowResult.ok}
        {#each rowResult.rows as item (item.segment.id)}
          {@const duration =
            item.segment.endSeconds - item.segment.startSeconds}
          {@const durationStatus = segmentDurationStatus(duration)}
          <button
            class="segment-range"
            class:selected={item.segment.id === selectedSegmentId}
            type="button"
            aria-label={`Select ${durationStatus === 'expected' ? '' : `${durationStatus} `}segment from ${item.segment.startSeconds.toFixed(2)} to ${item.segment.endSeconds.toFixed(2)} seconds`}
            data-segment-focus-id={item.segment.id}
            data-duration-status={durationStatus}
            style:left={`${scale.timeToPixel(item.segment.startSeconds)}px`}
            style:width={`${Math.max(3, scale.timeToPixel(item.segment.endSeconds) - scale.timeToPixel(item.segment.startSeconds))}px`}
            style:top={`${0.4 + item.row * 1.75}rem`}
            onclick={(event) => {
              event.stopPropagation();
              onSelect(item.segment);
            }}
          ></button>
        {/each}
      {:else}
        <span class="timeline-layout-error" role="status"
          >{rowResult.message}</span
        >
      {/if}

      <span
        class="timeline-playhead"
        style:left={`${scale.timeToPixel(currentSeconds)}px`}
        aria-hidden="true"
      ></span>
    </div>
  </div>
</div>
