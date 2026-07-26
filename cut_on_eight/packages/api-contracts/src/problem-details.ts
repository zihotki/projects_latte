import { z } from 'zod';

export const problemDetailsSchema = z.strictObject({
  type: z.string().url(),
  title: z.string().min(1),
  status: z.number().int().min(400).max(599),
  detail: z.string().min(1),
  code: z.string().regex(/^[a-z][a-z0-9_]*$/),
  instance: z.string().min(1).optional(),
  errors: z.record(z.string(), z.array(z.string().min(1))).optional(),
});

export type ProblemDetails = z.infer<typeof problemDetailsSchema>;
