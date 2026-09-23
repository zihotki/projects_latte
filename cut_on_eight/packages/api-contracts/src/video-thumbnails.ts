import { z } from 'zod';

const size = z.tuple([
  z.number().int().positive(),
  z.number().int().positive(),
]);
const sample = z.tuple([
  z.number().finite().nonnegative(),
  z.number().int().nonnegative(),
  z.number().int().nonnegative(),
  z.number().int().nonnegative(),
  z.number().int().positive(),
  z.number().int().positive(),
]);

export const videoThumbnailManifestSchema = z.strictObject({
  schemaVersion: z.literal(1),
  profileVersion: z.string().min(1),
  durationSeconds: z.number().finite().positive(),
  thumbnail: size,
  pages: z
    .array(
      z.tuple([
        z.string().regex(/^sprite-[a-f0-9]{24}-\d+\.webp$/),
        z.number().int().positive(),
        z.number().int().positive(),
      ]),
    )
    .min(1),
  samples: z.array(sample).min(1),
});

export type VideoThumbnailManifestDto = z.infer<
  typeof videoThumbnailManifestSchema
>;
