export const MIN_TIMELINE_ZOOM = 1;
export const MAX_TIMELINE_ZOOM = 256;

export interface TimelineViewport {
  readonly durationSeconds: number;
  readonly offsetSeconds: number;
  readonly viewportWidth: number;
  readonly zoom: number;
}

export interface VisibleTimeRange {
  readonly startSeconds: number;
  readonly endSeconds: number;
}

function finiteNonnegative(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export class TimeScale implements TimelineViewport {
  readonly durationSeconds: number;
  readonly offsetSeconds: number;
  readonly viewportWidth: number;
  readonly zoom: number;

  constructor(viewport: TimelineViewport) {
    this.durationSeconds = finiteNonnegative(viewport.durationSeconds);
    this.viewportWidth = finiteNonnegative(viewport.viewportWidth);
    this.zoom = clamp(
      Number.isFinite(viewport.zoom) ? viewport.zoom : MAX_TIMELINE_ZOOM,
      MIN_TIMELINE_ZOOM,
      MAX_TIMELINE_ZOOM,
    );
    this.offsetSeconds = this.clampOffset(viewport.offsetSeconds);
  }

  get visibleDurationSeconds(): number {
    return this.durationSeconds / this.zoom;
  }

  get secondsPerPixel(): number {
    return this.viewportWidth > 0
      ? this.visibleDurationSeconds / this.viewportWidth
      : 0;
  }

  timeToPixel(seconds: number): number {
    if (this.secondsPerPixel === 0 || !Number.isFinite(seconds)) return 0;
    return (seconds - this.offsetSeconds) / this.secondsPerPixel;
  }

  pixelToTime(pixel: number): number {
    if (this.durationSeconds === 0 || this.viewportWidth === 0) return 0;
    const safePixel = clamp(
      Number.isFinite(pixel) ? pixel : 0,
      0,
      this.viewportWidth,
    );
    return clamp(
      this.offsetSeconds + safePixel * this.secondsPerPixel,
      0,
      this.durationSeconds,
    );
  }

  clampOffset(offsetSeconds: number): number {
    const maximum = Math.max(
      0,
      this.durationSeconds - this.visibleDurationSeconds,
    );
    return clamp(finiteNonnegative(offsetSeconds), 0, maximum);
  }

  visibleRange(): VisibleTimeRange {
    return {
      startSeconds: this.offsetSeconds,
      endSeconds: Math.min(
        this.durationSeconds,
        this.offsetSeconds + this.visibleDurationSeconds,
      ),
    };
  }
}
