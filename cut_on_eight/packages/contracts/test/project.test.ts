import { describe, expect, it } from 'vitest';
import {
  apiErrorSchema,
  frameStepSeconds,
  importSelectionResponseSchema,
  jobRecordSchema,
  migrateProjectDocument,
  projectDocumentSchema,
  projectSummarySchema,
  workspaceSnapshotSchema,
} from '../src/index.js';

const projectId = '10000000-0000-4000-8000-000000000001';
const segmentId = '20000000-0000-4000-8000-000000000001';

const validProject = {
  schemaVersion: 3,
  id: projectId,
  source: {
    fileName: 'cross-body-lead.mp4',
    durationSeconds: 42.5,
    width: 1920,
    height: 1080,
    frameRateNumerator: 30_000,
    frameRateDenominator: 1_001,
    frameRateReliability: 'reliable',
    hasAudio: true,
    inspectedAt: '2026-07-21T10:00:00.000Z',
    inspectorVersion: 'ffprobe-v1',
  },
  editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
  settings: { pauseAfterCreation: false },
  playbackPositionSeconds: 12.25,
  selectedSegmentId: segmentId,
  segments: [
    {
      id: segmentId,
      startSeconds: 10,
      endSeconds: 13,
      exportSelected: true,
      title: null,
      tagIds: [],
    },
  ],
  metadata: { title: null, tags: [], notes: null },
} as const;

const validWorkspace = {
  activeProjectId: projectId,
  openProjects: [validProject],
  library: [
    {
      id: projectId,
      fileName: validProject.source.fileName,
      durationSeconds: validProject.source.durationSeconds,
    },
  ],
} as const;

function legacyProject(frameRate: string | null) {
  const segments = validProject.segments.map((segment) => ({
    id: segment.id,
    startSeconds: segment.startSeconds,
    endSeconds: segment.endSeconds,
    exportSelected: segment.exportSelected,
  }));
  return {
    schemaVersion: 1,
    id: validProject.id,
    source: {
      fileName: validProject.source.fileName,
      durationSeconds: validProject.source.durationSeconds,
      width: validProject.source.width,
      height: validProject.source.height,
      frameRate,
      hasAudio: validProject.source.hasAudio,
    },
    settings: validProject.settings,
    playbackPositionSeconds: validProject.playbackPositionSeconds,
    selectedSegmentId: validProject.selectedSegmentId,
    segments,
    metadata: validProject.metadata,
  };
}

describe('project contracts', () => {
  it('round-trips valid persisted and API payloads', () => {
    const project = projectDocumentSchema.parse(
      JSON.parse(JSON.stringify(validProject)),
    );
    const workspace = workspaceSnapshotSchema.parse(
      JSON.parse(JSON.stringify(validWorkspace)),
    );
    const job = jobRecordSchema.parse({
      schemaVersion: 1,
      id: '30000000-0000-4000-8000-000000000001',
      projectId,
      type: 'inspect-source',
      state: 'queued',
      attempts: 0,
      maxAttempts: 3,
      createdAt: '2026-07-21T10:00:00.000Z',
      updatedAt: '2026-07-21T10:00:00.000Z',
      error: null,
    });

    expect(project).toEqual(validProject);
    expect(workspace).toEqual(validWorkspace);
    expect(job.type).toBe('inspect-source');
    expect(
      importSelectionResponseSchema.parse({
        outcome: 'imported',
        projectId,
        workspace,
      }).outcome,
    ).toBe('imported');
    expect(
      apiErrorSchema.parse({
        error: {
          code: 'import_failed',
          message: 'The video could not be imported.',
          retryable: true,
        },
      }).error.code,
    ).toBe('import_failed');
  });

  it('migrates version 1 without changing segment timestamps', () => {
    const migrated = migrateProjectDocument(legacyProject('30000/1001'));

    expect(migrated).toMatchObject({
      schemaVersion: 3,
      source: {
        frameRateNumerator: 30_000,
        frameRateDenominator: 1_001,
        frameRateReliability: 'approximate',
        inspectedAt: null,
        inspectorVersion: null,
      },
      editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
      segments: [{ startSeconds: 10, endSeconds: 13 }],
    });
    expect(projectDocumentSchema.safeParse(migrated).success).toBe(true);
  });

  it.each([null, 'unknown', '30/0', '0/1'])(
    'falls back safely for absent or invalid legacy frame rate %s',
    (frameRate) => {
      const migrated = migrateProjectDocument(legacyProject(frameRate));

      expect(migrated.source).toMatchObject({
        frameRateNumerator: null,
        frameRateDenominator: null,
        frameRateReliability: 'approximate',
      });
      expect(frameStepSeconds(migrated.source)).toEqual({
        approximate: true,
        seconds: 1 / 30,
      });
    },
  );

  it('uses reliable rational frame rates for frame stepping', () => {
    expect(frameStepSeconds(validProject.source)).toEqual({
      approximate: false,
      seconds: 1_001 / 30_000,
    });
    expect(
      frameStepSeconds({
        ...validProject.source,
        frameRateReliability: 'approximate',
      }),
    ).toEqual({ approximate: true, seconds: 1 / 30 });
  });

  it.each([
    { startSeconds: 10, endSeconds: 10 },
    { startSeconds: 10, endSeconds: 9 },
  ])(
    'rejects invalid segment boundaries: %o',
    ({ startSeconds, endSeconds }) => {
      expect(
        projectDocumentSchema.safeParse({
          ...validProject,
          segments: [
            {
              ...validProject.segments[0],
              startSeconds,
              endSeconds,
            },
          ],
        }).success,
      ).toBe(false);
    },
  );

  it('accepts persisted triple overlap for recoverable UI validation', () => {
    expect(
      projectDocumentSchema.safeParse({
        ...validProject,
        selectedSegmentId: null,
        segments: [
          { ...validProject.segments[0], id: segmentId },
          {
            ...validProject.segments[0],
            id: '20000000-0000-4000-8000-000000000002',
          },
          {
            ...validProject.segments[0],
            id: '20000000-0000-4000-8000-000000000003',
          },
        ],
      }).success,
    ).toBe(true);
  });

  it('rejects a selected segment ID that is not present', () => {
    expect(
      projectDocumentSchema.safeParse({
        ...validProject,
        selectedSegmentId: '20000000-0000-4000-8000-000000000099',
      }).success,
    ).toBe(false);
  });

  it('rejects duplicate segment IDs', () => {
    expect(
      projectDocumentSchema.safeParse({
        ...validProject,
        segments: [validProject.segments[0], validProject.segments[0]],
      }).success,
    ).toBe(false);
  });

  it('rejects duplicate open-project and library IDs', () => {
    expect(
      workspaceSnapshotSchema.safeParse({
        ...validWorkspace,
        openProjects: [validProject, validProject],
      }).success,
    ).toBe(false);
    expect(
      workspaceSnapshotSchema.safeParse({
        ...validWorkspace,
        library: [validWorkspace.library[0], validWorkspace.library[0]],
      }).success,
    ).toBe(false);
  });

  it('accepts only version 3 in the persisted project schema', () => {
    expect(
      projectDocumentSchema.safeParse({ ...validProject, schemaVersion: 2 })
        .success,
    ).toBe(false);
    expect(
      jobRecordSchema.safeParse({
        schemaVersion: 2,
        id: '30000000-0000-4000-8000-000000000001',
        projectId,
        type: 'inspect-source',
        state: 'queued',
        attempts: 0,
        maxAttempts: 3,
        createdAt: '2026-07-21T10:00:00.000Z',
        updatedAt: '2026-07-21T10:00:00.000Z',
        error: null,
      }).success,
    ).toBe(false);
  });

  it.each(['managedPath', 'externalPath'])(
    'rejects browser-facing summary field %s',
    (pathField) => {
      expect(
        projectSummarySchema.safeParse({
          ...validWorkspace.library[0],
          [pathField]: '/Users/example/private/video.mp4',
        }).success,
      ).toBe(false);
    },
  );

  it('rejects job records whose state contradicts their error', () => {
    const baseJob = {
      schemaVersion: 1,
      id: '30000000-0000-4000-8000-000000000001',
      projectId,
      type: 'inspect-source',
      attempts: 1,
      maxAttempts: 3,
      createdAt: '2026-07-21T10:00:00.000Z',
      updatedAt: '2026-07-21T10:01:00.000Z',
    } as const;

    expect(
      jobRecordSchema.safeParse({ ...baseJob, state: 'failed', error: null })
        .success,
    ).toBe(false);
    expect(
      jobRecordSchema.safeParse({
        ...baseJob,
        state: 'completed',
        error: {
          code: 'ffprobe_failed',
          message: 'FFprobe failed.',
          retryable: true,
        },
      }).success,
    ).toBe(false);
  });
});
