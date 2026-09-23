import { z } from 'zod';
import { entityIdSchema, timestampSchema } from './common.js';

export const processingItemSchema = z.strictObject({
  videoId: entityIdSchema,
  videoTitle: z.string().min(1),
  task: z.enum(['import', 'inspect', 'thumbnails']),
  state: z.enum(['queued', 'running', 'failed']),
  updatedAt: timestampSchema,
  failureCode: z
    .string()
    .regex(/^[a-z][a-z0-9_]*$/)
    .nullable(),
});

export const processingSnapshotSchema = z.strictObject({
  activeCount: z.number().int().nonnegative(),
  failedCount: z.number().int().nonnegative(),
  observedAt: timestampSchema,
  items: z.array(processingItemSchema).max(100),
});

export type ProcessingSnapshotDto = z.infer<typeof processingSnapshotSchema>;
