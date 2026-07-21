import { z } from 'zod';
import { projectDocumentSchema } from './project.js';

export const projectSummarySchema = z.strictObject({
  id: z.string().uuid(),
  fileName: z.string().min(1),
  durationSeconds: z.number().finite().positive().nullable(),
});

export const workspaceSnapshotSchema = z
  .strictObject({
    activeProjectId: z.string().uuid().nullable(),
    openProjects: z.array(projectDocumentSchema),
    library: z.array(projectSummarySchema),
  })
  .superRefine((workspace, context) => {
    const openProjectIds = new Set(
      workspace.openProjects.map((project) => project.id),
    );
    const libraryProjectIds = new Set(
      workspace.library.map((project) => project.id),
    );

    if (openProjectIds.size !== workspace.openProjects.length) {
      context.addIssue({
        code: 'custom',
        message: 'Open project IDs must be unique',
        path: ['openProjects'],
      });
    }

    if (libraryProjectIds.size !== workspace.library.length) {
      context.addIssue({
        code: 'custom',
        message: 'Library project IDs must be unique',
        path: ['library'],
      });
    }

    if (
      workspace.activeProjectId !== null &&
      !openProjectIds.has(workspace.activeProjectId)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'Active project must be open',
        path: ['activeProjectId'],
      });
    }

    if (
      workspace.openProjects.length > 0 &&
      workspace.activeProjectId === null
    ) {
      context.addIssue({
        code: 'custom',
        message: 'A non-empty workspace must have an active project',
        path: ['activeProjectId'],
      });
    }
  });

export type ProjectSummary = z.infer<typeof projectSummarySchema>;
export type WorkspaceSnapshot = z.infer<typeof workspaceSnapshotSchema>;
