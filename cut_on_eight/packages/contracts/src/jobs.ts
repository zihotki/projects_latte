import { z } from 'zod';

export const jobStateSchema = z.enum([
  'queued',
  'running',
  'completed',
  'failed',
]);
export const jobTypeSchema = z.literal('inspect-source');

const jobRecordBaseShape = {
  schemaVersion: z.literal(1),
  id: z.string().uuid(),
  projectId: z.string().uuid(),
  type: jobTypeSchema,
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

export const jobRecordSchema = z.discriminatedUnion('state', [
  z.strictObject({
    ...jobRecordBaseShape,
    state: z.literal('queued'),
    error: z.null(),
  }),
  z.strictObject({
    ...jobRecordBaseShape,
    state: z.literal('running'),
    error: z.null(),
  }),
  z.strictObject({
    ...jobRecordBaseShape,
    state: z.literal('completed'),
    error: z.null(),
  }),
  z.strictObject({
    ...jobRecordBaseShape,
    state: z.literal('failed'),
    error: jobFailureSchema,
  }),
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
export type JobSnapshot = z.infer<typeof jobSnapshotSchema>;
export type Capabilities = z.infer<typeof capabilitiesSchema>;
