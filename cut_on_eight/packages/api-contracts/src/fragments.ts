import { z } from 'zod';
import {
  entityIdSchema,
  hasUniqueIds,
  hasUniqueStrings,
  microsecondsSchema,
  revisionSchema,
  tagSchema,
  timestampSchema,
} from './common.js';

export const fragmentPreviewSchema = z
  .strictObject({
    assetId: entityIdSchema,
    href: z.string().min(1),
    revision: revisionSchema,
    sampleUs: z.array(microsecondsSchema).max(5),
    columns: z.number().int().positive(),
    rows: z.number().int().positive(),
    frameWidth: z.number().int().positive(),
    frameHeight: z.number().int().positive(),
  })
  .refine(({ columns, rows, sampleUs }) => columns * rows >= sampleUs.length, {
    message: 'Preview grid must contain every sample',
    path: ['sampleUs'],
  });

export type FragmentPreviewDto = z.infer<typeof fragmentPreviewSchema>;

export const fragmentSchema = z
  .strictObject({
    id: entityIdSchema,
    videoId: entityIdSchema,
    startUs: microsecondsSchema,
    endUs: microsecondsSchema,
    title: z.string().max(240).nullable(),
    description: z.string().max(4_000).nullable(),
    exportSelected: z.boolean(),
    revision: revisionSchema,
    tags: z.array(tagSchema),
    previewState: z.enum(['pending', 'ready', 'failed']),
    preview: fragmentPreviewSchema.nullable(),
  })
  .superRefine(({ startUs, endUs, tags }, context) => {
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
  });

export type FragmentDto = z.infer<typeof fragmentSchema>;
export const fragmentListSchema = z.array(fragmentSchema);

const fragmentMutationFields = {
  startUs: microsecondsSchema,
  endUs: microsecondsSchema,
  title: z.string().trim().max(240).nullable(),
  description: z.string().trim().max(4_000).nullable(),
  exportSelected: z.boolean(),
  tagIds: z.array(entityIdSchema),
} as const;

export const editorFragmentSchema = z
  .strictObject({
    id: entityIdSchema,
    expectedRevision: revisionSchema.nullable(),
    ...fragmentMutationFields,
  })
  .superRefine(({ startUs, endUs, tagIds }, context) => {
    addMutationIssues(startUs, endUs, tagIds, context);
  });

export const fragmentPatchRequestSchema = z
  .strictObject({
    expectedRevision: revisionSchema,
    ...fragmentMutationFields,
  })
  .superRefine(({ startUs, endUs, tagIds }, context) => {
    addMutationIssues(startUs, endUs, tagIds, context);
  });

export type FragmentPatchRequest = z.infer<typeof fragmentPatchRequestSchema>;

export const deleteFragmentRequestSchema = z.strictObject({
  expectedRevision: revisionSchema,
});

export const deletedFragmentSchema = z.strictObject({
  fragment: fragmentSchema,
  undoToken: z.string().min(32),
  undoUntil: timestampSchema,
});

export type DeletedFragmentDto = z.infer<typeof deletedFragmentSchema>;

export const restoreFragmentRequestSchema = z.strictObject({
  undoToken: z.string().min(32),
});

function addMutationIssues(
  startUs: number,
  endUs: number,
  tagIds: readonly string[],
  context: z.RefinementCtx,
): void {
  if (endUs <= startUs) {
    context.addIssue({
      code: 'custom',
      message: 'Fragment end must be after its start',
      path: ['endUs'],
    });
  }
  if (!hasUniqueStrings(tagIds)) {
    context.addIssue({
      code: 'custom',
      message: 'Tag IDs must be unique',
      path: ['tagIds'],
    });
  }
}
