import { describe, expect, it } from 'vitest';
import { MAX_TIMELINE_ZOOM, TimeScale } from './timeline-geometry.js';

describe('timeline geometry', () => {
  it('round trips timestamps inside a one-hour viewport', () => {
    const scale = new TimeScale({
      durationSeconds: 3_600,
      offsetSeconds: 600,
      viewportWidth: 1_200,
      zoom: 4,
    });

    expect(scale.visibleRange()).toEqual({
      startSeconds: 600,
      endSeconds: 1_500,
    });
    expect(scale.timeToPixel(1_050)).toBeCloseTo(600);
    expect(scale.pixelToTime(600)).toBeCloseTo(1_050);
  });

  it('handles empty sources and viewports without invalid numbers', () => {
    const scale = new TimeScale({
      durationSeconds: 0,
      offsetSeconds: 10,
      viewportWidth: 0,
      zoom: 4,
    });

    expect(scale.visibleRange()).toEqual({
      startSeconds: 0,
      endSeconds: 0,
    });
    expect(scale.timeToPixel(10)).toBe(0);
    expect(scale.pixelToTime(10)).toBe(0);
    expect(scale.offsetSeconds).toBe(0);
  });

  it('clamps zoom and horizontal offsets', () => {
    const fit = new TimeScale({
      durationSeconds: 100,
      offsetSeconds: 50,
      viewportWidth: 1_000,
      zoom: 0,
    });
    const maximum = new TimeScale({
      durationSeconds: 100,
      offsetSeconds: 100,
      viewportWidth: 1_000,
      zoom: MAX_TIMELINE_ZOOM * 2,
    });

    expect(fit.zoom).toBe(1);
    expect(fit.offsetSeconds).toBe(0);
    expect(maximum.zoom).toBe(MAX_TIMELINE_ZOOM);
    expect(maximum.offsetSeconds).toBeCloseTo(100 - 100 / MAX_TIMELINE_ZOOM);
    expect(maximum.clampOffset(-1)).toBe(0);
  });
});
