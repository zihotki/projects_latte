import { z } from 'zod';
import {
  entityIdSchema,
  hasUniqueIds,
  microsecondsSchema,
  revisionSchema,
  tagSchema,
} from './common.js';

export const videoStatusSchema = z.enum([
  'receiving',
  'queued',
  'processing',
  'ready',
  'failed',
  'deleting',
]);

export type VideoStatus = z.infer<typeof videoStatusSchema>;

export const videoSummarySchema = z
  .strictObject({
    id: entityIdSchema,
    title: z.string().min(1).max(240),
    description: z.string().max(4_000).nullable(),
    originalFileName: z.string().min(1),
    durationUs: microsecondsSchema.nullable(),
    width: z.number().int().positive().nullable(),
    height: z.number().int().positive().nullable(),
    frameRateNumerator: z.number().int().positive().nullable(),
    frameRateDenominator: z.number().int().positive().nullable(),
    frameRateReliability: z.enum(['reliable', 'approximate']),
    hasAudio: z.boolean().nullable(),
    status: videoStatusSchema,
    revision: revisionSchema,
    tags: z.array(tagSchema),
  })
  .superRefine((video, context) => {
    if (!hasUniqueIds(video.tags)) {
      context.addIssue({
        code: 'custom',
        message: 'Tag IDs must be unique',
        path: ['tags'],
      });
    }
    const hasNumerator = video.frameRateNumerator !== null;
    const hasDenominator = video.frameRateDenominator !== null;
    if (hasNumerator !== hasDenominator) {
      context.addIssue({
        code: 'custom',
        message: 'Frame-rate numerator and denominator must be paired',
        path: ['frameRateNumerator'],
      });
    }
    if (video.frameRateReliability === 'reliable' && !hasNumerator) {
      context.addIssue({
        code: 'custom',
        message: 'Reliable frame rate requires a rational value',
        path: ['frameRateReliability'],
      });
    }
  });

export type VideoSummaryDto = z.infer<typeof videoSummarySchema>;

export const deleteVideoRequestSchema = z.strictObject({
  expectedRevision: revisionSchema,
});

export const videoListSchema = z.array(videoSummarySchema);
