import { z } from 'zod';

const maximumWebpDimension = 16_383;

export const sourceFingerprintSchema = z.string().min(1).max(128);

const thumbnailSizeSchema = z.tuple([
  z.number().int().positive().max(maximumWebpDimension),
  z.number().int().positive().max(maximumWebpDimension),
]);

const spritePageSchema = z.tuple([
  z.string().regex(/^sprite-\d{3}\.webp$/),
  z.number().int().positive().max(maximumWebpDimension),
  z.number().int().positive().max(maximumWebpDimension),
]);

const thumbnailSampleSchema = z.tuple([
  z.number().finite().nonnegative(),
  z.number().int().nonnegative(),
  z.number().int().nonnegative(),
  z.number().int().nonnegative(),
  z.number().int().positive(),
  z.number().int().positive(),
]);

export const thumbnailManifestV1Schema = z
  .strictObject({
    schemaVersion: z.literal(1),
    generatorVersion: z.string().min(1).max(128),
    sourceFingerprint: sourceFingerprintSchema,
    durationSeconds: z.number().finite().positive(),
    thumbnail: thumbnailSizeSchema,
    pages: z.array(spritePageSchema).min(1),
    samples: z.array(thumbnailSampleSchema).min(1),
  })
  .superRefine((manifest, context) => {
    const pageNames = new Set(manifest.pages.map(([fileName]) => fileName));
    if (pageNames.size !== manifest.pages.length) {
      context.addIssue({
        code: 'custom',
        message: 'Sprite page names must be unique',
        path: ['pages'],
      });
    }

    let previousTime = -1;
    for (const [index, sample] of manifest.samples.entries()) {
      const [time, pageIndex, x, y, width, height] = sample;
      if (time <= previousTime) {
        context.addIssue({
          code: 'custom',
          message: 'Thumbnail sample times must be strictly ascending',
          path: ['samples', index, 0],
        });
      }
      previousTime = time;

      if (time > manifest.durationSeconds) {
        context.addIssue({
          code: 'custom',
          message: 'Thumbnail sample time exceeds the source duration',
          path: ['samples', index, 0],
        });
      }

      const page = manifest.pages[pageIndex];
      if (page === undefined) {
        context.addIssue({
          code: 'custom',
          message: 'Thumbnail sample references an unknown sprite page',
          path: ['samples', index, 1],
        });
        continue;
      }

      if (width > manifest.thumbnail[0] || height > manifest.thumbnail[1]) {
        context.addIssue({
          code: 'custom',
          message: 'Thumbnail sample exceeds the configured cell size',
          path: ['samples', index],
        });
      }

      if (x + width > page[1] || y + height > page[2]) {
        context.addIssue({
          code: 'custom',
          message: 'Thumbnail sample rectangle exceeds its sprite page',
          path: ['samples', index],
        });
      }
    }
  });

export type ThumbnailManifestV1 = z.infer<typeof thumbnailManifestV1Schema>;
