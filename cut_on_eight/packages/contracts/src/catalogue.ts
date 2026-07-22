import { z } from 'zod';
import { segmentSchema } from './project.js';

export const tagDefinitionSchema = z.strictObject({
  id: z.string().uuid(),
  name: z
    .string()
    .trim()
    .min(1)
    .transform((value) => value.toLowerCase()),
});

export const tagDefinitionsSchema = z.array(tagDefinitionSchema);

export const catalogueMetadataSchema = z
  .strictObject({
    schemaVersion: z.literal(1),
    tags: z.array(tagDefinitionSchema),
  })
  .superRefine((value, context) => {
    const ids = new Set(value.tags.map((tag) => tag.id));
    const names = new Set(value.tags.map((tag) => tag.name));
    if (ids.size !== value.tags.length) {
      context.addIssue({
        code: 'custom',
        message: 'Tag IDs must be unique',
        path: ['tags'],
      });
    }
    if (names.size !== value.tags.length) {
      context.addIssue({
        code: 'custom',
        message: 'Tag names must be unique',
        path: ['tags'],
      });
    }
  });

export const fragmentPreviewSchema = z.strictObject({
  sampleSeconds: z.number().finite().nonnegative(),
  pageFileName: z.string().regex(/^sprite-\d{3}\.webp$/),
  pageWidth: z.number().int().positive(),
  pageHeight: z.number().int().positive(),
  x: z.number().int().nonnegative(),
  y: z.number().int().nonnegative(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  identity: z.string().min(1),
});

export const fragmentSummarySchema = z.strictObject({
  projectId: z.string().uuid(),
  sourceFileName: z.string().min(1),
  sourceDurationSeconds: z.number().finite().positive().nullable(),
  ordinal: z.number().int().positive(),
  segment: segmentSchema,
  previews: z.array(fragmentPreviewSchema).max(5),
  thumbnailState: z.enum(['ready', 'generating', 'failed', 'unavailable']),
  thumbnailJobId: z.string().uuid().nullable(),
  frameStepSeconds: z.number().finite().positive(),
  frameStepApproximate: z.boolean(),
});

export const fragmentCatalogueDiagnosticSchema = z.strictObject({
  projectId: z.string().uuid(),
  sourceFileName: z.string().min(1),
  message: z.string().min(1),
});

export const fragmentCatalogueSchema = z.strictObject({
  fragments: z.array(fragmentSummarySchema),
  tags: z.array(tagDefinitionSchema),
  diagnostics: z.array(fragmentCatalogueDiagnosticSchema),
});

export const fragmentMutationSchema = z.strictObject({
  startSeconds: z.number().finite().nonnegative(),
  endSeconds: z.number().finite().positive(),
  exportSelected: z.boolean(),
  title: z
    .string()
    .transform((value) => value.trim())
    .nullable()
    .transform((value) => value || null),
  tagIds: z.array(z.string().uuid()),
});

export const deletedFragmentSchema = z.strictObject({
  projectId: z.string().uuid(),
  index: z.number().int().nonnegative(),
  fragment: segmentSchema,
});

export const createTagRequestSchema = z.strictObject({
  name: z.string().trim().min(1),
});

export type CatalogueMetadata = z.infer<typeof catalogueMetadataSchema>;
export type CreateTagRequest = z.infer<typeof createTagRequestSchema>;
export type DeletedFragment = z.infer<typeof deletedFragmentSchema>;
export type FragmentCatalogue = z.infer<typeof fragmentCatalogueSchema>;
export type FragmentMutation = z.infer<typeof fragmentMutationSchema>;
export type FragmentPreview = z.infer<typeof fragmentPreviewSchema>;
export type FragmentSummary = z.infer<typeof fragmentSummarySchema>;
export type FragmentCatalogueDiagnostic = z.infer<
  typeof fragmentCatalogueDiagnosticSchema
>;
export type TagDefinition = z.infer<typeof tagDefinitionSchema>;
