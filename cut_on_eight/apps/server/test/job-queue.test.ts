import type { ProjectDocument } from '@cut-on-eight/contracts';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import type { ServerConfig } from '../src/config.js';
import type { ProbeResult, ProbeRunner } from '../src/jobs/ffprobe-runner.js';
import { ProbeError } from '../src/jobs/ffprobe-runner.js';
import { JobQueue } from '../src/jobs/job-queue.js';
import { JobRepository } from '../src/jobs/job-repository.js';
import {
  LibraryRepository,
  type LibraryEntry,
} from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';
import { WorkspaceRepository } from '../src/storage/workspace-repository.js';

const firstId = '10000000-0000-4000-8000-000000000001';
const secondId = '10000000-0000-4000-8000-000000000002';
const firstJobId = '20000000-0000-4000-8000-000000000001';
const secondJobId = '20000000-0000-4000-8000-000000000002';
const roots: string[] = [];
const metadata: ProbeResult = {
  durationSeconds: 18.5,
  width: 1280,
  height: 720,
  frameRateNumerator: 24_000,
  frameRateDenominator: 1_001,
  frameRateReliability: 'reliable',
  hasAudio: true,
};

function project(id: string, fileName: string): ProjectDocument {
  return {
    schemaVersion: 2,
    id,
    source: {
      fileName,
      durationSeconds: null,
      width: null,
      height: null,
      frameRateNumerator: null,
      frameRateDenominator: null,
      frameRateReliability: 'approximate',
      hasAudio: null,
      inspectedAt: null,
      inspectorVersion: null,
    },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
  };
}

async function fixture(ids = [firstJobId]): Promise<{
  entries: LibraryEntry[];
  jobs: JobRepository;
  layout: StorageLayout;
  projects: ProjectRepository;
}> {
  const root = await mkdtemp(join(tmpdir(), 'cut-on-eight-jobs-'));
  roots.push(root);
  const layout = new StorageLayout(root);
  const projects = new ProjectRepository(layout);
  const entries = [
    {
      id: firstId,
      managedSourcePath: layout.forProject(firstId, 'First.mp4').relativeSource,
      fingerprint: {
        realPath: '/source/First.mp4',
        size: 12,
        modifiedMilliseconds: 1,
      },
      importedAt: '2026-07-21T10:00:00.000Z',
    },
    {
      id: secondId,
      managedSourcePath: layout.forProject(secondId, 'Second.mp4')
        .relativeSource,
      fingerprint: {
        realPath: '/source/Second.mp4',
        size: 12,
        modifiedMilliseconds: 2,
      },
      importedAt: '2026-07-21T10:01:00.000Z',
    },
  ] satisfies LibraryEntry[];
  await new LibraryRepository(layout).save({ schemaVersion: 1, entries });
  await projects.save(
    firstId,
    entries[0]!.managedSourcePath,
    project(firstId, 'First.mp4'),
  );
  await projects.save(
    secondId,
    entries[1]!.managedSourcePath,
    project(secondId, 'Second.mp4'),
  );
  const availableIds = [...ids];
  const jobs = new JobRepository(
    layout,
    () => availableIds.shift() ?? secondJobId,
    (() => {
      let tick = 0;
      return () => new Date(Date.UTC(2026, 6, 21, 10, 0, tick++));
    })(),
  );
  return { entries, jobs, layout, projects };
}

function updater(
  projects: ProjectRepository,
  entries: readonly LibraryEntry[],
): (projectId: string, result: ProbeResult) => Promise<void> {
  return async (projectId, result) => {
    const entry = entries.find((candidate) => candidate.id === projectId)!;
    const current = await projects.readRequired(
      projectId,
      entry.managedSourcePath,
    );
    await projects.save(projectId, entry.managedSourcePath, {
      ...current,
      source: { ...current.source, ...result },
    });
  };
}

async function until(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 500; attempt += 1) {
    if (predicate()) return;
    await new Promise<void>((resolve) => setTimeout(resolve, 2));
  }
  throw new Error('Condition was not reached');
}

async function untilAsync(predicate: () => Promise<boolean>): Promise<void> {
  for (let attempt = 0; attempt < 500; attempt += 1) {
    if (await predicate()) return;
    await new Promise<void>((resolve) => setTimeout(resolve, 2));
  }
  throw new Error('Condition was not reached');
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

describe('durable inspection queue', () => {
  it('persists strictly increasing transition timestamps with a fixed clock', async () => {
    const { entries, layout } = await fixture();
    const fixedNow = new Date('2026-07-21T10:00:00.000Z');
    const repository = new JobRepository(
      layout,
      () => firstJobId,
      () => fixedNow,
    );
    const queued = await repository.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    const running = await repository.markRunning(entries, queued);
    const failed = await repository.markFailed(entries, running, {
      code: 'ffprobe_failed',
      message: 'Inspection failed.',
      retryable: true,
    });
    const retried = await repository.retry(entries, failed.id);
    const runningAgain = await repository.markRunning(entries, retried);
    const completed = await repository.markCompleted(entries, runningAgain);
    const timestamps = [
      queued,
      running,
      failed,
      retried,
      runningAgain,
      completed,
    ].map((job) => Date.parse(job.updatedAt));

    expect(queued.updatedAt).toBe(fixedNow.toISOString());
    for (let index = 1; index < timestamps.length; index += 1) {
      expect(timestamps[index]).toBeGreaterThan(timestamps[index - 1]!);
    }
  });

  it('reports corrupt job files without changing them or blocking other projects', async () => {
    const { entries, jobs, layout, projects } = await fixture();
    await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    const corruptFile = layout.jobFile(
      entries[1]!.managedSourcePath,
      secondJobId,
    );
    const corruptBytes = Buffer.from('{"schemaVersion":1,"broken":');
    await mkdir(layout.forProject(secondId, 'Second.mp4').jobsDirectory);
    await writeFile(corruptFile, corruptBytes);
    const queue = new JobQueue(
      layout,
      new LibraryRepository(layout),
      jobs,
      { isAvailable: async () => true, inspect: async () => metadata },
      updater(projects, entries),
    );

    await queue.recover();
    await queue.waitForIdle();

    expect(queue.snapshot()).toMatchObject({
      jobs: [{ projectId: firstId, state: 'completed' }],
      errors: [{ code: 'corrupt_job_record', projectId: secondId }],
    });
    expect(await readFile(corruptFile)).toEqual(corruptBytes);
  });

  it('recovers a persisted running job before processing it again', async () => {
    const { entries, jobs, layout, projects } = await fixture();
    const queued = await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    await jobs.markRunning(entries, queued);
    let resolveInspection!: (value: ProbeResult) => void;
    const queue = new JobQueue(
      layout,
      new LibraryRepository(layout),
      jobs,
      {
        isAvailable: async () => true,
        inspect: () =>
          new Promise((resolve) => {
            resolveInspection = resolve;
          }),
      },
      updater(projects, entries),
    );

    await queue.recover();
    await until(() => resolveInspection !== undefined);
    expect(queue.snapshot().jobs[0]).toMatchObject({
      state: 'running',
      attempts: 2,
    });
    resolveInspection(metadata);
    await queue.waitForIdle();
    expect(queue.snapshot().jobs[0]?.state).toBe('completed');
  });

  it('fails recovery at the attempt limit without starting another attempt', async () => {
    const { entries, jobs, layout, projects } = await fixture();
    const queued = await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    const firstRun = await jobs.markRunning(entries, queued);
    const firstFailure = await jobs.markFailed(entries, firstRun, {
      code: 'ffprobe_failed',
      message: 'Inspection failed.',
      retryable: true,
    });
    const secondRun = await jobs.markRunning(
      entries,
      await jobs.retry(entries, firstFailure.id),
    );
    const secondFailure = await jobs.markFailed(entries, secondRun, {
      code: 'ffprobe_failed',
      message: 'Inspection failed.',
      retryable: true,
    });
    await jobs.markRunning(
      entries,
      await jobs.retry(entries, secondFailure.id),
    );
    let inspections = 0;
    const queue = new JobQueue(
      layout,
      new LibraryRepository(layout),
      jobs,
      {
        isAvailable: async () => true,
        inspect: async () => {
          inspections += 1;
          return metadata;
        },
      },
      updater(projects, entries),
    );

    await queue.recover();
    await queue.waitForIdle();

    expect(inspections).toBe(0);
    expect(queue.snapshot().jobs[0]).toMatchObject({
      state: 'failed',
      attempts: 3,
      error: {
        code: 'job_attempts_exhausted',
        retryable: false,
      },
    });
  });

  it('processes jobs serially and updates project metadata', async () => {
    const { entries, jobs, layout, projects } = await fixture([
      firstJobId,
      secondJobId,
    ]);
    await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    await jobs.createQueuedInspection(
      secondId,
      layout.forProject(secondId, 'Second.mp4').directory,
    );
    const resolvers: Array<(value: ProbeResult) => void> = [];
    const calls: string[] = [];
    const probe: ProbeRunner = {
      isAvailable: async () => true,
      inspect: (source) => {
        calls.push(source);
        return new Promise((resolve) => resolvers.push(resolve));
      },
    };
    const queue = new JobQueue(
      layout,
      new LibraryRepository(layout),
      jobs,
      probe,
      updater(projects, entries),
    );

    await queue.recover();
    await until(() => calls.length === 1);
    expect(resolvers).toHaveLength(1);
    resolvers.shift()!(metadata);
    await until(() => calls.length === 2);
    expect(resolvers).toHaveLength(1);
    resolvers.shift()!(metadata);
    await queue.waitForIdle();

    expect(queue.snapshot().jobs.map((job) => job.state)).toEqual([
      'completed',
      'completed',
    ]);
    await expect(
      projects.readRequired(firstId, entries[0]!.managedSourcePath),
    ).resolves.toMatchObject({ source: metadata });
  });

  it('persists retryable failure and retries explicitly', async () => {
    const { entries, jobs, layout, projects } = await fixture();
    await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    let calls = 0;
    const probe: ProbeRunner = {
      isAvailable: async () => false,
      inspect: async () => {
        calls += 1;
        if (calls === 1) {
          throw new ProbeError(
            'ffprobe_missing',
            'FFprobe is unavailable.',
            true,
          );
        }
        return metadata;
      },
    };
    const queue = new JobQueue(
      layout,
      new LibraryRepository(layout),
      jobs,
      probe,
      updater(projects, entries),
    );
    const observedStates: string[] = [];
    queue.subscribe((snapshot) => {
      const state = snapshot.jobs[0]?.state;
      if (state !== undefined) observedStates.push(state);
    });

    await queue.recover();
    await queue.waitForIdle();
    expect(queue.snapshot().jobs[0]).toMatchObject({
      state: 'failed',
      attempts: 1,
      error: { code: 'ffprobe_missing', retryable: true },
    });
    await queue.retry(firstJobId);
    await queue.waitForIdle();
    expect(observedStates).toContain('queued');
    expect(queue.snapshot().jobs[0]).toMatchObject({
      state: 'completed',
      attempts: 2,
    });
  });

  it('makes the final failed attempt non-retryable', async () => {
    const { entries, jobs, layout, projects } = await fixture();
    await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    const queue = new JobQueue(
      layout,
      new LibraryRepository(layout),
      jobs,
      {
        isAvailable: async () => false,
        inspect: async () => {
          throw new ProbeError(
            'ffprobe_missing',
            'FFprobe is unavailable.',
            true,
          );
        },
      },
      updater(projects, entries),
    );

    await queue.recover();
    await queue.waitForIdle();
    await queue.retry(firstJobId);
    await queue.waitForIdle();
    await queue.retry(firstJobId);
    await queue.waitForIdle();

    expect(queue.snapshot().jobs[0]).toMatchObject({
      state: 'failed',
      attempts: 3,
      error: { code: 'ffprobe_missing', retryable: false },
    });
    await expect(queue.retry(firstJobId)).rejects.toThrow('job_not_retryable');
  });

  it('closes a project without waiting for a running inspection', async () => {
    const { entries, jobs, layout } = await fixture();
    await jobs.createQueuedInspection(
      firstId,
      layout.forProject(firstId, 'First.mp4').directory,
    );
    await new WorkspaceRepository(layout).save({
      schemaVersion: 1,
      openProjectIds: [firstId],
      activeProjectId: firstId,
    });
    let resolveProbe!: (value: ProbeResult) => void;
    const probe: ProbeRunner = {
      isAvailable: async () => true,
      inspect: () => new Promise((resolve) => (resolveProbe = resolve)),
    };
    const config: ServerConfig = {
      dataRoot: layout.dataRoot,
      host: '127.0.0.1',
      port: 4318,
    };
    const app = createApp({ config, probeRunner: probe });
    await app.recover();
    await until(() => resolveProbe !== undefined);

    const response = await app.inject({
      method: 'POST',
      url: `/api/projects/${firstId}/close`,
      payload: project(firstId, 'First.mp4'),
    });
    expect(response.statusCode).toBe(200);
    expect(
      (await app.inject({ method: 'GET', url: '/api/jobs' })).json(),
    ).toMatchObject({
      jobs: [{ state: 'running' }],
    });
    expect(
      (await app.inject({ method: 'GET', url: '/api/capabilities' })).json(),
    ).toEqual({
      backendAvailable: true,
      ffprobeAvailable: true,
    });

    resolveProbe(metadata);
    await untilAsync(async () => {
      const snapshot = await jobs.list(entries);
      return snapshot.jobs[0]?.state === 'completed';
    });
    await app.close();
    expect(entries[0]!.id).toBe(firstId);
  });
});
