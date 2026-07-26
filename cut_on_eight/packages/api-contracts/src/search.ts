import { z } from 'zod';
import {
  entityIdSchema,
  hasUniqueIds,
  microsecondsSchema,
  tagSchema,
} from './common.js';
import { fragmentPreviewSchema } from './fragments.js';

const filterIdsSchema = z.array(entityIdSchema).max(20);

export const fragmentSearchQuerySchema = z.object({
  q: z.string().trim().min(1).max(500),
  tagIds: filterIdsSchema.default([]),
  collectionIds: filterIdsSchema.default([]),
  videoIds: filterIdsSchema.default([]),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

export type FragmentSearchQuery = z.infer<typeof fragmentSearchQuerySchema>;

export const fragmentSearchCollectionSchema = z.strictObject({
  id: entityIdSchema,
  title: z.string().trim().min(1).max(240),
});

export const fragmentSearchResultSchema = z
  .strictObject({
    id: entityIdSchema,
    title: z.string().max(240).nullable(),
    description: z.string().max(4_000).nullable(),
    tags: z.array(tagSchema),
    startUs: microsecondsSchema,
    endUs: microsecondsSchema,
    videoId: entityIdSchema,
    sourceTitle: z.string().min(1).max(240),
    collections: z.array(fragmentSearchCollectionSchema),
    score: z.number().finite(),
    previewState: z.enum(['pending', 'ready', 'failed']),
    preview: fragmentPreviewSchema.nullable(),
  })
  .superRefine(({ startUs, endUs, tags, collections }, context) => {
    if (endUs <= startUs) {
      context.addIssue({
        code: 'custom',
        message: 'Fragment end must be after its start',
        path: ['endUs'],
      });
    }
    if (!hasUniqueIds(tags)) {
      context.addIssue({
        code: 'custom',
        message: 'Tag IDs must be unique',
        path: ['tags'],
      });
    }
    if (!hasUniqueIds(collections)) {
      context.addIssue({
        code: 'custom',
        message: 'Collection IDs must be unique',
        path: ['collections'],
      });
    }
  });

export type FragmentSearchResultDto = z.infer<
  typeof fragmentSearchResultSchema
>;

export const fragmentSearchResponseSchema = z.strictObject({
  mode: z.enum(['hybrid', 'lexical']),
  indexing: z.strictObject({ pending: z.number().int().nonnegative() }),
  results: z.array(fragmentSearchResultSchema),
});

export type FragmentSearchResponse = z.infer<
  typeof fragmentSearchResponseSchema
>;
