import { z } from 'zod';
import {
  entityIdSchema,
  hasUniqueIds,
  microsecondsSchema,
  revisionSchema,
} from './common.js';
import { editorFragmentSchema, fragmentSchema } from './fragments.js';
import { videoSummarySchema } from './videos.js';

export const editorStateSchema = z.strictObject({
  selectedFragmentId: entityIdSchema.nullable(),
  pauseAfterCreation: z.boolean(),
  timelineZoom: z.number().finite().min(1),
  timelineOffsetUs: microsecondsSchema,
});

export type EditorStateDto = z.infer<typeof editorStateSchema>;

export const editorVideoSchema = z
  .strictObject({
    video: videoSummarySchema,
    source: z
      .strictObject({
        assetId: entityIdSchema,
        href: z.string().min(1),
      })
      .nullable(),
    fragments: z.array(fragmentSchema),
    playbackPositionUs: microsecondsSchema,
    editor: editorStateSchema,
  })
  .refine(
    ({ video, fragments }) =>
      fragments.every((fragment) => fragment.videoId === video.id),
    {
      message: 'Fragments must belong to the editor video',
      path: ['fragments'],
    },
  );

export type EditorVideoDto = z.infer<typeof editorVideoSchema>;

export const workspaceSchema = z
  .strictObject({
    activeVideoId: entityIdSchema.nullable(),
    openVideos: z.array(editorVideoSchema),
    library: z.array(videoSummarySchema),
  })
  .superRefine(({ activeVideoId, openVideos, library }, context) => {
    if (!hasUniqueIds(openVideos.map(({ video }) => video))) {
      context.addIssue({
        code: 'custom',
        message: 'Open video IDs must be unique',
        path: ['openVideos'],
      });
    }
    if (!hasUniqueIds(library)) {
      context.addIssue({
        code: 'custom',
        message: 'Library video IDs must be unique',
        path: ['library'],
      });
    }
    if (
      activeVideoId !== null &&
      !openVideos.some(({ video }) => video.id === activeVideoId)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'Active video must be open',
        path: ['activeVideoId'],
      });
    }
  });

export type WorkspaceDto = z.infer<typeof workspaceSchema>;

export const editorSaveRequestSchema = z.strictObject({
  expectedVideoRevision: revisionSchema,
  title: z.string().trim().min(1).max(240),
  description: z.string().trim().max(4_000).nullable(),
  tagIds: z.array(entityIdSchema),
  playbackPositionUs: microsecondsSchema,
  editor: editorStateSchema,
  fragments: z.array(editorFragmentSchema),
});

export type EditorSaveRequest = z.infer<typeof editorSaveRequestSchema>;

export const closeVideoRequestSchema = z.strictObject({
  expectedVideoRevision: revisionSchema,
  playbackPositionUs: microsecondsSchema,
  editor: editorStateSchema,
});

export const uploadAcceptedSchema = z.strictObject({
  video: videoSummarySchema,
  workspace: workspaceSchema,
});

export type UploadAcceptedDto = z.infer<typeof uploadAcceptedSchema>;
