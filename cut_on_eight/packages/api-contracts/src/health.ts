import { z } from 'zod';

export const healthLiveSchema = z.strictObject({
  status: z.literal('live'),
  service: z.literal('cut-on-eight-server'),
});

export type HealthLiveDto = z.infer<typeof healthLiveSchema>;

export const dependencyHealthSchema = z.strictObject({
  postgres: z.enum(['ready', 'unavailable']),
  qdrant: z.enum(['ready', 'degraded', 'not-configured']),
  worker: z.enum(['ready', 'unavailable']),
});

export const healthReadySchema = z.strictObject({
  status: z.enum(['ready', 'unavailable']),
  dependencies: dependencyHealthSchema,
});

export type HealthReadyDto = z.infer<typeof healthReadySchema>;
