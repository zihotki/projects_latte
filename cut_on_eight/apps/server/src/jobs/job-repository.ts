import { randomUUID } from 'node:crypto';
import { lstat, mkdir, readdir } from 'node:fs/promises';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { jobRecordSchema, type JobRecord } from '@cut-on-eight/contracts';
import {
  CorruptPersistedDataError,
  readJsonValidated,
  syncDirectory,
  writeJsonAtomic,
} from '../storage/atomic-json.js';
import type { StorageLayout } from '../storage/layout.js';

type IdFactory = () => string;
type Clock = () => Date;

function isMissing(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}

export class JobRepository {
  constructor(
    private readonly layout: StorageLayout,
    private readonly createId: IdFactory = randomUUID,
    private readonly clock: Clock = () => new Date(),
  ) {}

  async createQueuedInspection(
    projectId: string,
    projectDirectory: string,
  ): Promise<JobRecord> {
    const { jobsDirectory, resolvedDirectory } =
      this.resolveProjectDirectories(projectDirectory);
    await this.layout.assertNoSymlinkComponents(jobsDirectory);
    const firstCreatedDirectory = await mkdir(jobsDirectory, {
      recursive: true,
    });

    if (firstCreatedDirectory !== undefined) {
      await syncDirectory(resolvedDirectory);
    }

    await this.layout.assertNoSymlinkComponents(jobsDirectory);

    for (let attempt = 0; attempt < 16; attempt += 1) {
      const job = this.newQueuedInspection(projectId);
      const jobFile = resolve(jobsDirectory, `${job.id}.json`);

      await this.layout.assertNoSymlinkComponents(jobFile);

      try {
        await lstat(jobFile);
        continue;
      } catch (error) {
        if (!isMissing(error)) {
          throw error;
        }
      }

      await writeJsonAtomic(jobFile, job);
      return job;
    }

    throw new Error('Unable to allocate a collision-safe inspection job');
  }

  async ensureInspectionJob(
    projectId: string,
    projectDirectory: string,
  ): Promise<JobRecord> {
    const { jobsDirectory } = this.resolveProjectDirectories(projectDirectory);
    await this.layout.assertNoSymlinkComponents(jobsDirectory);
    let entries;

    try {
      entries = await readdir(jobsDirectory, { withFileTypes: true });
    } catch (error) {
      if (isMissing(error)) {
        return this.createQueuedInspection(projectId, projectDirectory);
      }

      throw error;
    }

    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.json')) {
        continue;
      }

      const jobFile = resolve(jobsDirectory, entry.name);
      await this.layout.assertNoSymlinkComponents(jobFile);
      let job: JobRecord | undefined;

      try {
        job = await readJsonValidated(jobFile, (value) =>
          jobRecordSchema.parse(value),
        );
      } catch (error) {
        if (error instanceof CorruptPersistedDataError) {
          continue;
        }

        throw error;
      }

      if (
        job !== undefined &&
        job.projectId === projectId &&
        entry.name === `${job.id}.json`
      ) {
        return job;
      }
    }

    return this.createQueuedInspection(projectId, projectDirectory);
  }

  private newQueuedInspection(projectId: string): JobRecord {
    const timestamp = this.clock().toISOString();
    return jobRecordSchema.parse({
      schemaVersion: 1,
      id: this.createId(),
      projectId,
      type: 'inspect-source',
      state: 'queued',
      attempts: 0,
      maxAttempts: 3,
      createdAt: timestamp,
      updatedAt: timestamp,
      error: null,
    });
  }

  private resolveProjectDirectories(projectDirectory: string): {
    jobsDirectory: string;
    resolvedDirectory: string;
  } {
    const resolvedDirectory = resolve(projectDirectory);
    const relativeDirectory = relative(this.layout.dataRoot, resolvedDirectory);

    if (
      relativeDirectory.length === 0 ||
      relativeDirectory === '_system' ||
      relativeDirectory.includes(sep) ||
      relativeDirectory === '..' ||
      relativeDirectory.startsWith(`..${sep}`) ||
      isAbsolute(relativeDirectory)
    ) {
      throw new Error('Project directory must be directly below the data root');
    }

    return {
      resolvedDirectory,
      jobsDirectory: resolve(resolvedDirectory, 'jobs'),
    };
  }
}
