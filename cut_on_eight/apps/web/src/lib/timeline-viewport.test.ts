import { describe, expect, it } from 'vitest';
import { MAX_TIMELINE_ZOOM, TimeScale } from './timeline-geometry.js';
import {
  ensureRangeVisible,
  fitSource,
  panByPixels,
  zoomAt,
} from './timeline-viewport.js';

function scale(): TimeScale {
  return new TimeScale({
    durationSeconds: 100,
    offsetSeconds: 10,
    viewportWidth: 1_000,
    zoom: 2,
  });
}

describe('timeline viewport commands', () => {
  it('keeps the pointer timestamp fixed while zooming', () => {
    const initial = scale();
    const anchorPixel = 250;
    const anchorTime = initial.pixelToTime(anchorPixel);
    const zoomed = zoomAt(initial, 4, anchorPixel);

    expect(zoomed.pixelToTime(anchorPixel)).toBeCloseTo(anchorTime);
    expect(zoomed.zoom).toBe(4);
  });

  it('uses the same anchor rule for playhead-centred button zoom', () => {
    const initial = scale();
    const playheadSeconds = 35;
    const playheadPixel = initial.timeToPixel(playheadSeconds);
    const zoomed = zoomAt(initial, 8, playheadPixel);

    expect(zoomed.pixelToTime(playheadPixel)).toBeCloseTo(playheadSeconds);
  });

  it('bounds zoom and horizontal panning', () => {
    const initial = scale();

    expect(zoomAt(initial, Infinity, 500).zoom).toBe(MAX_TIMELINE_ZOOM);
    expect(panByPixels(initial, 100).offsetSeconds).toBeCloseTo(15);
    expect(panByPixels(initial, -10_000).offsetSeconds).toBe(0);
    expect(panByPixels(initial, 10_000).visibleRange().endSeconds).toBe(100);
  });

  it('resets to a complete-source fit', () => {
    const fitted = fitSource(3_600, 1_200);

    expect(fitted.zoom).toBe(1);
    expect(fitted.offsetSeconds).toBe(0);
    expect(fitted.visibleRange()).toEqual({
      startSeconds: 0,
      endSeconds: 3_600,
    });
  });

  it('pans only when a fitting range is outside the viewport', () => {
    const initial = new TimeScale({
      durationSeconds: 100,
      offsetSeconds: 25,
      viewportWidth: 1_000,
      zoom: 4,
    });

    expect(ensureRangeVisible(initial, 30, 40)).toBe(initial);
    expect(ensureRangeVisible(initial, 60, 65)).toMatchObject({
      zoom: 4,
      offsetSeconds: 40,
    });
    expect(ensureRangeVisible(initial, 5, 10)).toMatchObject({
      zoom: 4,
      offsetSeconds: 5,
    });
  });

  it('zooms out just enough when the selected range cannot fit', () => {
    const initial = new TimeScale({
      durationSeconds: 100,
      offsetSeconds: 50,
      viewportWidth: 1_000,
      zoom: 8,
    });
    const visible = ensureRangeVisible(initial, 10, 50);

    expect(visible.zoom).toBeCloseTo(2.5);
    expect(visible.visibleRange()).toEqual({
      startSeconds: 10,
      endSeconds: 50,
    });
  });
});
