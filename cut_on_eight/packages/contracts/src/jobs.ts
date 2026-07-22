import { z } from 'zod';
import { sourceFingerprintSchema } from './thumbnails.js';

export const jobStateSchema = z.enum([
  'queued',
  'running',
  'completed',
  'failed',
]);
export const jobTypeSchema = z.enum(['inspect-source', 'generate-thumbnails']);

const jobRecordBaseShape = {
  schemaVersion: z.literal(1),
  id: z.string().uuid(),
  projectId: z.string().uuid(),
  attempts: z.number().int().nonnegative(),
  maxAttempts: z.number().int().positive(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
};

const jobFailureSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string().min(1),
  retryable: z.boolean(),
});

function jobRecordForType<T extends z.ZodRawShape>(typeShape: T) {
  const shape = { ...jobRecordBaseShape, ...typeShape };
  return z.discriminatedUnion('state', [
    z.strictObject({
      ...shape,
      state: z.literal('queued'),
      error: z.null(),
    }),
    z.strictObject({
      ...shape,
      state: z.literal('running'),
      error: z.null(),
    }),
    z.strictObject({
      ...shape,
      state: z.literal('completed'),
      error: z.null(),
    }),
    z.strictObject({
      ...shape,
      state: z.literal('failed'),
      error: jobFailureSchema,
    }),
  ]);
}

export const inspectionJobRecordSchema = jobRecordForType({
  type: z.literal('inspect-source'),
});

export const thumbnailJobRecordSchema = jobRecordForType({
  type: z.literal('generate-thumbnails'),
  generatorVersion: z.string().min(1).max(128),
  sourceFingerprint: sourceFingerprintSchema,
});

export const jobRecordSchema = z.union([
  inspectionJobRecordSchema,
  thumbnailJobRecordSchema,
]);

export const jobSnapshotSchema = z.strictObject({
  jobs: z.array(jobRecordSchema),
  errors: z
    .array(
      z.strictObject({
        code: z.string().min(1),
        message: z.string().min(1),
        projectId: z.string().uuid().nullable(),
      }),
    )
    .default([]),
});

export const capabilitiesSchema = z.strictObject({
  backendAvailable: z.literal(true),
  ffprobeAvailable: z.boolean(),
});

export type JobState = z.infer<typeof jobStateSchema>;
export type JobType = z.infer<typeof jobTypeSchema>;
export type JobRecord = z.infer<typeof jobRecordSchema>;
export type InspectionJobRecord = z.infer<typeof inspectionJobRecordSchema>;
export type ThumbnailJobRecord = z.infer<typeof thumbnailJobRecordSchema>;
export type JobSnapshot = z.infer<typeof jobSnapshotSchema>;
export type Capabilities = z.infer<typeof capabilitiesSchema>;
