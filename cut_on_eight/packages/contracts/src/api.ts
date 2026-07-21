import { z } from 'zod';
import { workspaceSnapshotSchema } from './workspace.js';

export const importSelectionResponseSchema = z.discriminatedUnion('outcome', [
  z.strictObject({
    outcome: z.literal('cancelled'),
    workspace: workspaceSnapshotSchema,
  }),
  z.strictObject({
    outcome: z.enum(['imported', 'reopened']),
    projectId: z.string().uuid(),
    workspace: workspaceSnapshotSchema,
  }),
]);

export type ImportSelectionResponse = z.infer<
  typeof importSelectionResponseSchema
>;
