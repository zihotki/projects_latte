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
import type { LibraryEntry } from '../storage/library-repository.js';

type IdFactory = () => string;
type Clock = () => Date;

export interface JobReadError {
  readonly code: 'corrupt_job_record';
  readonly message: string;
  readonly projectId: string;
}

export interface JobListResult {
  readonly errors: JobReadError[];
  readonly jobs: JobRecord[];
}

function isMissing(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}

export class JobRepository {
  private operationQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly layout: StorageLayout,
    private readonly createId: IdFactory = randomUUID,
    private readonly clock: Clock = () => new Date(),
  ) {}

  createQueuedInspection(
    projectId: string,
    projectDirectory: string,
  ): Promise<JobRecord> {
    return this.exclusive(() =>
      this.createQueuedInspectionDirect(projectId, projectDirectory),
    );
  }

  ensureInspectionJob(
    projectId: string,
    projectDirectory: string,
  ): Promise<JobRecord> {
    return this.exclusive(async () => {
      const jobs = await this.readProjectJobs(projectId, projectDirectory);
      return (
        jobs.jobs[0] ??
        this.createQueuedInspectionDirect(projectId, projectDirectory)
      );
    });
  }

  async list(entries: readonly LibraryEntry[]): Promise<JobListResult> {
    const results = await Promise.all(
      entries.map((entry) =>
        this.readProjectJobs(
          entry.id,
          resolve(
            this.layout.resolveManagedRelativePath(entry.managedSourcePath),
            '..',
          ),
        ),
      ),
    );
    return {
      jobs: results
        .flatMap((result) => result.jobs)
        .sort((left, right) => left.createdAt.localeCompare(right.createdAt)),
      errors: results.flatMap((result) => result.errors),
    };
  }

  recoverRunning(entries: readonly LibraryEntry[]): Promise<JobListResult> {
    return this.exclusive(async () => {
      const result = await this.list(entries);
      const recovered: JobRecord[] = [];

      for (const job of result.jobs) {
        if (job.state !== 'running') {
          recovered.push(job);
          continue;
        }
        if (job.attempts >= job.maxAttempts) {
          recovered.push(
            await this.writeTransition(entries, job, {
              ...job,
              state: 'failed',
              updatedAt: this.clock().toISOString(),
              error: {
                code: 'job_attempts_exhausted',
                message: 'The inspection job exhausted its allowed attempts.',
                retryable: false,
              },
            }),
          );
          continue;
        }
        recovered.push(
          await this.writeTransition(entries, job, {
            ...job,
            state: 'queued',
            updatedAt: this.clock().toISOString(),
            error: null,
          }),
        );
      }
      return { jobs: recovered, errors: result.errors };
    });
  }

  markRunning(
    entries: readonly LibraryEntry[],
    job: JobRecord,
  ): Promise<JobRecord> {
    if (job.state !== 'queued') throw new Error('Only queued jobs can start');
    if (job.attempts >= job.maxAttempts) {
      throw new Error('job_attempts_exhausted');
    }
    return this.exclusive(() =>
      this.writeTransition(entries, job, {
        ...job,
        state: 'running',
        attempts: job.attempts + 1,
        updatedAt: this.clock().toISOString(),
        error: null,
      }),
    );
  }

  markCompleted(
    entries: readonly LibraryEntry[],
    job: JobRecord,
  ): Promise<JobRecord> {
    if (job.state !== 'running')
      throw new Error('Only running jobs can finish');
    return this.exclusive(() =>
      this.writeTransition(entries, job, {
        ...job,
        state: 'completed',
        updatedAt: this.clock().toISOString(),
        error: null,
      }),
    );
  }

  markFailed(
    entries: readonly LibraryEntry[],
    job: JobRecord,
    failure: { code: string; message: string; retryable: boolean },
  ): Promise<JobRecord> {
    if (job.state !== 'running') throw new Error('Only running jobs can fail');
    return this.exclusive(() =>
      this.writeTransition(entries, job, {
        ...job,
        state: 'failed',
        updatedAt: this.clock().toISOString(),
        error: {
          ...failure,
          retryable: job.attempts < job.maxAttempts && failure.retryable,
        },
      }),
    );
  }

  retry(entries: readonly LibraryEntry[], jobId: string): Promise<JobRecord> {
    return this.exclusive(async () => {
      const result = await this.list(entries);
      const job = result.jobs.find((candidate) => candidate.id === jobId);
      if (job === undefined) throw new Error('job_not_found');
      if (job.state !== 'failed' || !job.error.retryable) {
        throw new Error('job_not_retryable');
      }
      if (job.attempts >= job.maxAttempts) {
        throw new Error('job_attempts_exhausted');
      }
      return this.writeTransition(entries, job, {
        ...job,
        state: 'queued',
        updatedAt: this.clock().toISOString(),
        error: null,
      });
    });
  }

  private async createQueuedInspectionDirect(
    projectId: string,
    projectDirectory: string,
  ): Promise<JobRecord> {
    const { jobsDirectory, resolvedDirectory } =
      this.resolveProjectDirectories(projectDirectory);
    await this.layout.assertNoSymlinkComponents(jobsDirectory);
    const firstCreatedDirectory = await mkdir(jobsDirectory, {
      recursive: true,
    });
    if (firstCreatedDirectory !== undefined)
      await syncDirectory(resolvedDirectory);
    await this.layout.assertNoSymlinkComponents(jobsDirectory);

    for (let attempt = 0; attempt < 16; attempt += 1) {
      const job = this.newQueuedInspection(projectId);
      const jobFile = resolve(jobsDirectory, `${job.id}.json`);
      await this.layout.assertNoSymlinkComponents(jobFile);
      try {
        await lstat(jobFile);
        continue;
      } catch (error) {
        if (!isMissing(error)) throw error;
      }
      await writeJsonAtomic(jobFile, job);
      return job;
    }
    throw new Error('Unable to allocate a collision-safe inspection job');
  }

  private async readProjectJobs(
    projectId: string,
    projectDirectory: string,
  ): Promise<JobListResult> {
    const { jobsDirectory } = this.resolveProjectDirectories(projectDirectory);
    await this.layout.assertNoSymlinkComponents(jobsDirectory);
    let entries;
    try {
      entries = await readdir(jobsDirectory, { withFileTypes: true });
    } catch (error) {
      if (isMissing(error)) return { jobs: [], errors: [] };
      throw error;
    }

    const jobs: JobRecord[] = [];
    const errors: JobReadError[] = [];
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.json')) continue;
      const jobFile = resolve(jobsDirectory, entry.name);
      await this.layout.assertNoSymlinkComponents(jobFile);
      try {
        const job = await readJsonValidated(jobFile, (value) =>
          jobRecordSchema.parse(value),
        );
        if (
          job === undefined ||
          job.projectId !== projectId ||
          entry.name !== `${job.id}.json`
        ) {
          throw new CorruptPersistedDataError(
            jobFile,
            new Error('Job does not match its managed project or filename'),
          );
        }
        jobs.push(job);
      } catch (error) {
        if (!(error instanceof CorruptPersistedDataError)) throw error;
        errors.push({
          code: 'corrupt_job_record',
          message:
            'A managed inspection job is corrupt and was left unchanged.',
          projectId,
        });
      }
    }
    return { jobs, errors };
  }

  private async writeTransition(
    entries: readonly LibraryEntry[],
    previous: JobRecord,
    next: JobRecord,
  ): Promise<JobRecord> {
    const entry = entries.find(
      (candidate) => candidate.id === previous.projectId,
    );
    if (entry === undefined) throw new Error('job_project_not_found');
    const target = this.layout.jobFile(entry.managedSourcePath, previous.id);
    await this.layout.assertNoSymlinkComponents(target);
    const current = await readJsonValidated(target, (value) =>
      jobRecordSchema.parse(value),
    );
    if (
      current === undefined ||
      JSON.stringify(current) !== JSON.stringify(previous)
    ) {
      throw new Error('job_changed_concurrently');
    }
    const validated = jobRecordSchema.parse(next);
    await writeJsonAtomic(target, validated);
    return validated;
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

  private exclusive<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.operationQueue.then(operation);
    this.operationQueue = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}
