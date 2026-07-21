import {
  MAX_TIMELINE_ZOOM,
  MIN_TIMELINE_ZOOM,
  TimeScale,
} from './timeline-geometry.js';

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function recreate(
  scale: TimeScale,
  zoom: number,
  offsetSeconds: number,
): TimeScale {
  return new TimeScale({
    durationSeconds: scale.durationSeconds,
    viewportWidth: scale.viewportWidth,
    zoom,
    offsetSeconds,
  });
}

export function zoomAt(
  scale: TimeScale,
  nextZoom: number,
  anchorPixel: number,
): TimeScale {
  const zoom = clamp(
    Number.isFinite(nextZoom) ? nextZoom : MAX_TIMELINE_ZOOM,
    MIN_TIMELINE_ZOOM,
    MAX_TIMELINE_ZOOM,
  );
  const pixel = clamp(
    Number.isFinite(anchorPixel) ? anchorPixel : 0,
    0,
    scale.viewportWidth,
  );
  const anchorSeconds = scale.pixelToTime(pixel);
  const secondsPerPixel =
    scale.viewportWidth > 0
      ? scale.durationSeconds / zoom / scale.viewportWidth
      : 0;

  return recreate(scale, zoom, anchorSeconds - pixel * secondsPerPixel);
}

export function panByPixels(scale: TimeScale, deltaPixels: number): TimeScale {
  const pixels = Number.isFinite(deltaPixels) ? deltaPixels : 0;
  return recreate(
    scale,
    scale.zoom,
    scale.offsetSeconds + pixels * scale.secondsPerPixel,
  );
}

export function fitSource(
  durationSeconds: number,
  viewportWidth: number,
): TimeScale {
  return new TimeScale({
    durationSeconds,
    viewportWidth,
    zoom: MIN_TIMELINE_ZOOM,
    offsetSeconds: 0,
  });
}

export function ensureRangeVisible(
  scale: TimeScale,
  startSeconds: number,
  endSeconds: number,
): TimeScale {
  const start = clamp(
    Math.min(startSeconds, endSeconds),
    0,
    scale.durationSeconds,
  );
  const end = clamp(
    Math.max(startSeconds, endSeconds),
    0,
    scale.durationSeconds,
  );
  const range = scale.visibleRange();

  if (start >= range.startSeconds && end <= range.endSeconds) return scale;

  const duration = end - start;
  if (duration > scale.visibleDurationSeconds && duration > 0) {
    return recreate(
      scale,
      clamp(scale.durationSeconds / duration, MIN_TIMELINE_ZOOM, scale.zoom),
      start,
    );
  }

  const offsetSeconds =
    start < range.startSeconds ? start : end - scale.visibleDurationSeconds;
  return recreate(scale, scale.zoom, offsetSeconds);
}
