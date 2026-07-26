import type { JobRecord, JobSnapshot } from '@cut-on-eight/legacy-contracts';
import { describe, expect, it } from 'vitest';
import {
  countJobs,
  mergeJobRecord,
  mergeJobSnapshot,
  newestInspectionJob,
  parseJobSnapshot,
} from './job-events.js';

const projectId = '11111111-1111-4111-8111-111111111111';

function job(
  id: string,
  state: JobRecord['state'],
  updatedAt: string,
  createdAt = '2026-07-21T10:00:00.000Z',
): JobRecord {
  const base = {
    schemaVersion: 1 as const,
    id,
    projectId,
    type: 'inspect-source' as const,
    attempts: state === 'queued' ? 0 : 1,
    maxAttempts: 3,
    createdAt,
    updatedAt,
  };
  return state === 'failed'
    ? {
        ...base,
        state,
        error: { code: 'ffprobe_missing', message: 'Missing', retryable: true },
      }
    : { ...base, state, error: null };
}

describe('job event state', () => {
  it('accepts valid snapshots and rejects malformed event data', () => {
    const snapshot = { jobs: [], errors: [] };
    expect(parseJobSnapshot(JSON.stringify(snapshot))).toEqual(snapshot);
    expect(parseJobSnapshot('{')).toBeNull();
    expect(
      parseJobSnapshot(JSON.stringify({ jobs: [{ state: 'wat' }] })),
    ).toBeNull();
  });

  it('counts every durable state', () => {
    const jobs = [
      job(
        '11111111-1111-4111-8111-111111111112',
        'queued',
        '2026-07-21T10:01:00.000Z',
      ),
      job(
        '11111111-1111-4111-8111-111111111113',
        'running',
        '2026-07-21T10:02:00.000Z',
      ),
      job(
        '11111111-1111-4111-8111-111111111114',
        'completed',
        '2026-07-21T10:03:00.000Z',
      ),
      job(
        '11111111-1111-4111-8111-111111111115',
        'failed',
        '2026-07-21T10:04:00.000Z',
      ),
    ];
    expect(countJobs({ jobs, errors: [] })).toEqual({
      queued: 1,
      running: 1,
      completed: 1,
      failed: 1,
    });
  });

  it('selects the newest inspection job for a project', () => {
    const older = job(
      '11111111-1111-4111-8111-111111111112',
      'failed',
      '2026-07-21T10:04:00.000Z',
      '2026-07-21T10:00:00.000Z',
    );
    const newer = job(
      '11111111-1111-4111-8111-111111111113',
      'completed',
      '2026-07-21T10:02:00.000Z',
      '2026-07-21T10:01:00.000Z',
    );
    expect(
      newestInspectionJob({ jobs: [newer, older], errors: [] }, projectId),
    ).toEqual(newer);
  });

  it('does not replace a newer live update with an older retry response', () => {
    const running = job(
      '11111111-1111-4111-8111-111111111112',
      'running',
      '2026-07-21T10:03:00.000Z',
    );
    const queued = job(running.id, 'queued', '2026-07-21T10:02:00.000Z');
    const snapshot: JobSnapshot = { jobs: [running], errors: [] };
    expect(mergeJobRecord(snapshot, queued)).toBe(snapshot);
  });

  it('does not regress a retried job when a delayed failed snapshot arrives', () => {
    const id = '11111111-1111-4111-8111-111111111112';
    const queued = job(id, 'queued', '2026-07-21T10:04:00.000Z');
    const running = job(id, 'running', '2026-07-21T10:05:00.000Z');
    const delayedFailure = job(id, 'failed', '2026-07-21T10:03:00.000Z');
    const unrelated = job(
      '11111111-1111-4111-8111-111111111113',
      'completed',
      '2026-07-21T10:02:00.000Z',
    );

    const afterQueued = mergeJobSnapshot(
      { jobs: [queued, unrelated], errors: [] },
      { jobs: [delayedFailure], errors: [] },
    );
    expect(afterQueued.jobs).toEqual([queued, unrelated]);

    const afterRunning = mergeJobSnapshot(
      { jobs: [running, unrelated], errors: [] },
      { jobs: [delayedFailure], errors: [] },
    );
    expect(afterRunning.jobs).toEqual([running, unrelated]);
  });

  it('orders equal-millisecond legacy transitions by attempt and state progress', () => {
    const id = '11111111-1111-4111-8111-111111111112';
    const timestamp = '2026-07-21T10:04:00.000Z';
    const queued = { ...job(id, 'queued', timestamp), attempts: 1 };
    const running = job(id, 'running', timestamp);
    const completed = job(id, 'completed', timestamp);
    const failed = job(id, 'failed', timestamp);

    expect(
      mergeJobSnapshot(
        { jobs: [queued], errors: [] },
        { jobs: [running], errors: [] },
      ).jobs,
    ).toEqual([running]);
    expect(
      mergeJobSnapshot(
        { jobs: [running], errors: [] },
        { jobs: [completed], errors: [] },
      ).jobs,
    ).toEqual([completed]);
    expect(
      mergeJobSnapshot(
        { jobs: [running], errors: [] },
        { jobs: [failed], errors: [] },
      ).jobs,
    ).toEqual([failed]);
    expect(
      mergeJobSnapshot(
        { jobs: [completed], errors: [] },
        { jobs: [running], errors: [] },
      ).jobs,
    ).toEqual([completed]);
  });
});
