import { z } from 'zod';

export const entityIdSchema = z.string().uuid();
export const microsecondsSchema = z
  .number()
  .int()
  .nonnegative()
  .max(Number.MAX_SAFE_INTEGER);
export const revisionSchema = z.number().int().nonnegative();
export const timestampSchema = z.iso.datetime({ offset: true });

export const tagSchema = z.strictObject({
  id: entityIdSchema,
  name: z
    .string()
    .trim()
    .min(1)
    .max(80)
    .refine((name) => name === name.toLowerCase(), 'Tag must be lowercase'),
});

export type TagDto = z.infer<typeof tagSchema>;

export const createTagRequestSchema = z.strictObject({
  name: z.string().trim().min(1).max(80),
});

export type CreateTagRequest = z.infer<typeof createTagRequestSchema>;

export function hasUniqueIds(values: readonly { id: string }[]): boolean {
  return new Set(values.map(({ id }) => id)).size === values.length;
}

export function hasUniqueStrings(values: readonly string[]): boolean {
  return new Set(values).size === values.length;
}
