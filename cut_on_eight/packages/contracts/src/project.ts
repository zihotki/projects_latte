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

export const projectDocumentSchema = z
  .strictObject({
    schemaVersion: z.literal(1),
    id: z.string().uuid(),
    source: z.strictObject({
      fileName: z.string().min(1),
      durationSeconds: z.number().finite().positive().nullable(),
      width: z.number().int().positive().nullable(),
      height: z.number().int().positive().nullable(),
      frameRate: z.string().nullable(),
      hasAudio: z.boolean().nullable(),
    }),
    settings: z.strictObject({ pauseAfterCreation: z.boolean() }),
    playbackPositionSeconds: z.number().finite().nonnegative(),
    selectedSegmentId: z.string().uuid().nullable(),
    segments: z.array(segmentSchema),
    metadata: z.strictObject({
      title: z.string().nullable(),
      tags: z.array(z.string()),
      notes: z.string().nullable(),
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

export type Segment = z.infer<typeof segmentSchema>;
export type ProjectDocument = z.infer<typeof projectDocumentSchema>;
