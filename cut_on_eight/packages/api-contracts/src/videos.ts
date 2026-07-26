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
    hasAudio: z.boolean().nullable(),
    status: videoStatusSchema,
    revision: revisionSchema,
    tags: z.array(tagSchema),
  })
  .refine(({ tags }) => hasUniqueIds(tags), {
    message: 'Tag IDs must be unique',
    path: ['tags'],
  });

export type VideoSummaryDto = z.infer<typeof videoSummarySchema>;
