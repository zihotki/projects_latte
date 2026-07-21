import { z } from 'zod';

export const segmentSchema = z
  .strictObject({
    id: z.string().uuid(),
    startSeconds: z.number().finite().nonnegative(),
    endSeconds: z.number().finite().positive(),
    exportSelected: z.boolean(),
  })
  .refine((segment) => segment.endSeconds > segment.startSeconds, {
    message: 'Segment end must be after its start',
    path: ['endSeconds'],
  });

const commonProjectFields = {
  id: z.string().uuid(),
  settings: z.strictObject({ pauseAfterCreation: z.boolean() }),
  playbackPositionSeconds: z.number().finite().nonnegative(),
  selectedSegmentId: z.string().uuid().nullable(),
  segments: z.array(segmentSchema),
  metadata: z.strictObject({
    title: z.string().nullable(),
    tags: z.array(z.string()),
    notes: z.string().nullable(),
  }),
} as const;

const legacyProjectDocumentSchema = z.strictObject({
  schemaVersion: z.literal(1),
  ...commonProjectFields,
  source: z.strictObject({
    fileName: z.string().min(1),
    durationSeconds: z.number().finite().positive().nullable(),
    width: z.number().int().positive().nullable(),
    height: z.number().int().positive().nullable(),
    frameRate: z.string().nullable(),
    hasAudio: z.boolean().nullable(),
  }),
});

export const frameRateReliabilitySchema = z.enum(['reliable', 'approximate']);

const sourceSchema = z
  .strictObject({
    fileName: z.string().min(1),
    durationSeconds: z.number().finite().positive().nullable(),
    width: z.number().int().positive().nullable(),
    height: z.number().int().positive().nullable(),
    frameRateNumerator: z.number().int().positive().nullable(),
    frameRateDenominator: z.number().int().positive().nullable(),
    frameRateReliability: frameRateReliabilitySchema,
    hasAudio: z.boolean().nullable(),
    inspectedAt: z.iso.datetime({ offset: true }).nullable(),
    inspectorVersion: z.string().min(1).nullable(),
  })
  .superRefine((source, context) => {
    const hasNumerator = source.frameRateNumerator !== null;
    const hasDenominator = source.frameRateDenominator !== null;

    if (hasNumerator !== hasDenominator) {
      context.addIssue({
        code: 'custom',
        message: 'Frame-rate numerator and denominator must be set together',
        path: ['frameRateNumerator'],
      });
    }
    if (source.frameRateReliability === 'reliable' && !hasNumerator) {
      context.addIssue({
        code: 'custom',
        message: 'Reliable frame rate requires a fraction',
        path: ['frameRateReliability'],
      });
    }
    if ((source.inspectedAt === null) !== (source.inspectorVersion === null)) {
      context.addIssue({
        code: 'custom',
        message: 'Inspection timestamp and version must be set together',
        path: ['inspectedAt'],
      });
    }
  });

export const projectDocumentSchema = z
  .strictObject({
    schemaVersion: z.literal(2),
    ...commonProjectFields,
    source: sourceSchema,
    editor: z.strictObject({
      timelineZoom: z.number().finite().min(1),
      timelineOffsetSeconds: z.number().finite().nonnegative(),
    }),
  })
  .superRefine((project, context) => {
    const segmentIds = new Set(project.segments.map((segment) => segment.id));

    if (segmentIds.size !== project.segments.length) {
      context.addIssue({
        code: 'custom',
        message: 'Segment IDs must be unique',
        path: ['segments'],
      });
    }

    if (
      project.selectedSegmentId !== null &&
      !segmentIds.has(project.selectedSegmentId)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'Selected segment must exist in the project',
        path: ['selectedSegmentId'],
      });
    }
  });

export type FrameRateReliability = z.infer<typeof frameRateReliabilitySchema>;
export interface FrameStep {
  readonly approximate: boolean;
  readonly seconds: number;
}
export type Segment = z.infer<typeof segmentSchema>;
export type ProjectDocument = z.infer<typeof projectDocumentSchema>;

function parseLegacyFrameRate(
  value: string | null,
): { denominator: number; numerator: number } | null {
  const match = /^(\d+)\/(\d+)$/.exec(value ?? '');
  if (match === null) return null;

  const numerator = Number(match[1]);
  const denominator = Number(match[2]);
  return Number.isSafeInteger(numerator) &&
    numerator > 0 &&
    Number.isSafeInteger(denominator) &&
    denominator > 0
    ? { numerator, denominator }
    : null;
}

export function migrateProjectDocument(value: unknown): ProjectDocument {
  const current = projectDocumentSchema.safeParse(value);
  if (current.success) return current.data;

  const legacy = legacyProjectDocumentSchema.parse(value);
  const frameRate = parseLegacyFrameRate(legacy.source.frameRate);
  return projectDocumentSchema.parse({
    ...legacy,
    schemaVersion: 2,
    source: {
      fileName: legacy.source.fileName,
      durationSeconds: legacy.source.durationSeconds,
      width: legacy.source.width,
      height: legacy.source.height,
      frameRateNumerator: frameRate?.numerator ?? null,
      frameRateDenominator: frameRate?.denominator ?? null,
      frameRateReliability: 'approximate',
      hasAudio: legacy.source.hasAudio,
      inspectedAt: null,
      inspectorVersion: null,
    },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
  });
}

export function frameStepSeconds(source: ProjectDocument['source']): FrameStep {
  if (
    source.frameRateReliability === 'reliable' &&
    source.frameRateNumerator !== null &&
    source.frameRateDenominator !== null
  ) {
    return {
      approximate: false,
      seconds: source.frameRateDenominator / source.frameRateNumerator,
    };
  }

  return { approximate: true, seconds: 1 / 30 };
}
