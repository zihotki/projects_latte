import { describe, expect, it } from 'vitest';
import {
  fragmentSchema,
  videoSummarySchema,
  type FragmentDto,
  type VideoSummaryDto,
} from '../src/index.js';

const videoId = '0198-0000-7000-8000-000000000001'.replace(
  '0198-',
  '01980000-',
);
const fragmentId = '01980000-0000-7000-8000-000000000002';

const validVideo: VideoSummaryDto = {
  id: videoId,
  title: 'Example',
  description: null,
  originalFileName: 'example.mp4',
  durationUs: 10_000_000,
  width: 1920,
  height: 1080,
  frameRateNumerator: 30_000,
  frameRateDenominator: 1_001,
  frameRateReliability: 'reliable',
  hasAudio: true,
  status: 'ready',
  revision: 1,
  tags: [],
};

const validFragment: FragmentDto = {
  id: fragmentId,
  videoId,
  startUs: 1_000_000,
  endUs: 2_000_000,
  title: null,
  description: null,
  exportSelected: false,
  revision: 1,
  tags: [],
  previewState: 'pending',
  preview: null,
};

describe('public API contracts', () => {
  it('rejects private persistence fields from public video responses', () => {
    expect(
      videoSummarySchema.safeParse({
        ...validVideo,
        sourceBlobKey: 'videos/private/source.mp4',
      }).success,
    ).toBe(false);
  });

  it('carries a complete rational frame rate without private processing state', () => {
    expect(videoSummarySchema.parse(validVideo)).toMatchObject({
      frameRateNumerator: 30_000,
      frameRateDenominator: 1_001,
      frameRateReliability: 'reliable',
    });
    expect(
      videoSummarySchema.safeParse({
        ...validVideo,
        frameRateDenominator: null,
      }).success,
    ).toBe(false);
    expect(
      videoSummarySchema.safeParse({
        ...validVideo,
        processingFailureCode: 'ffprobe_failed',
      }).success,
    ).toBe(false);
  });

  it('rejects unsafe or inverted fragment timings', () => {
    expect(
      fragmentSchema.safeParse({ ...validFragment, endUs: 1 }).success,
    ).toBe(false);
    expect(
      fragmentSchema.safeParse({
        ...validFragment,
        startUs: Number.MAX_SAFE_INTEGER + 1,
      }).success,
    ).toBe(false);
  });

  it('rejects previews whose grid cannot contain their samples', () => {
    expect(
      fragmentSchema.safeParse({
        ...validFragment,
        previewState: 'ready',
        preview: {
          assetId: '01980000-0000-7000-8000-000000000003',
          href: '/api/assets/01980000-0000-7000-8000-000000000003',
          revision: 1,
          sampleUs: [1, 2, 3],
          columns: 2,
          rows: 1,
          frameWidth: 320,
          frameHeight: 180,
        },
      }).success,
    ).toBe(false);
  });
});
