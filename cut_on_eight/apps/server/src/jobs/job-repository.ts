import { randomUUID } from 'node:crypto';
import { mkdir } from 'node:fs/promises';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { jobRecordSchema, type JobRecord } from '@cut-on-eight/contracts';
import { writeJsonAtomic } from '../storage/atomic-json.js';
import type { StorageLayout } from '../storage/layout.js';

type IdFactory = () => string;
type Clock = () => Date;

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

    const id = this.createId();
    const timestamp = this.clock().toISOString();
    const job = jobRecordSchema.parse({
      schemaVersion: 1,
      id,
      projectId,
      type: 'inspect-source',
      state: 'queued',
      attempts: 0,
      maxAttempts: 3,
      createdAt: timestamp,
      updatedAt: timestamp,
      error: null,
    });
    const jobsDirectory = resolve(resolvedDirectory, 'jobs');
    const jobFile = resolve(jobsDirectory, `${id}.json`);

    await this.layout.assertNoSymlinkComponents(jobFile);
    await mkdir(jobsDirectory, { recursive: true });
    await this.layout.assertNoSymlinkComponents(jobFile);
    await writeJsonAtomic(jobFile, job);
    return job;
  }
}
