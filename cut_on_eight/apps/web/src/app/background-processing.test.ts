import type {
  JobRecord,
  ThumbnailManifestV1,
} from '@cut-on-eight/legacy-contracts';
import { describe, expect, it, vi } from 'vitest';
import {
  BackgroundProcessing,
  type BackgroundApi,
} from './background-processing.svelte.js';

const projectId = '11111111-1111-4111-8111-111111111111';

function job(state: JobRecord['state'] = 'completed'): JobRecord {
  const base = {
    schemaVersion: 1 as const,
    id: '22222222-2222-4222-8222-222222222222',
    projectId,
    type: 'inspect-source' as const,
    attempts: 1,
    maxAttempts: 3,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:01.000Z',
  };
  return state === 'failed'
    ? {
        ...base,
        state,
        error: { code: 'failed', message: 'failed', retryable: true },
      }
    : { ...base, state, error: null };
}

function manifest(identity: string): ThumbnailManifestV1 {
  return {
    schemaVersion: 1,
    generatorVersion: 'test',
    sourceFingerprint: identity,
    durationSeconds: 10,
    thumbnail: [160, 90],
    pages: [['sprite-001.webp', 160, 90]],
    samples: [[0, 0, 0, 0, 160, 90]],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

function api(overrides: Partial<BackgroundApi> = {}): BackgroundApi {
  return {
    loadCapabilities: vi.fn().mockResolvedValue({
      backendAvailable: true,
      ffprobeAvailable: true,
    }),
    loadThumbnailManifest: vi.fn().mockResolvedValue(manifest('default')),
    retryJob: vi.fn().mockResolvedValue(job()),
    connectJobEvents: vi.fn().mockReturnValue(() => undefined),
    ...overrides,
  };
}

describe('BackgroundProcessing', () => {
  it('loads tool capabilities', async () => {
    const model = new BackgroundProcessing(api(), () => null);
    await model.loadToolCapabilities();
    expect(model.ffprobeState).toBe('ready');
  });

  it('merges event snapshots and disposes the connection', () => {
    const captured: {
      handlers: Parameters<BackgroundApi['connectJobEvents']>[0] | null;
    } = { handlers: null };
    const close = vi.fn();
    const model = new BackgroundProcessing(
      api({
        connectJobEvents: (value) => {
          captured.handlers = value;
          return close;
        },
      }),
      () => null,
    );
    model.start();
    captured.handlers?.onSnapshot({ jobs: [job()], errors: [] });
    expect(model.jobs?.jobs).toHaveLength(1);
    model.dispose();
    expect(close).toHaveBeenCalledOnce();
  });

  it('ignores a thumbnail response superseded by a newer request', async () => {
    const first = deferred<ThumbnailManifestV1>();
    const second = deferred<ThumbnailManifestV1>();
    const load = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const model = new BackgroundProcessing(
      api({ loadThumbnailManifest: load }),
      () => null,
    );
    const stale = model.refreshThumbnailManifest(projectId, 'job:1');
    const current = model.refreshThumbnailManifest(projectId, 'job:2');
    first.resolve(manifest('old'));
    second.resolve(manifest('new'));
    await Promise.all([stale, current]);
    expect(model.thumbnailManifestFor(projectId)?.sourceFingerprint).toBe(
      'new',
    );
  });

  it('records sprite load failures', () => {
    const model = new BackgroundProcessing(api(), () => null);
    model.thumbnailPageLoadFailed(projectId);
    expect(model.thumbnailStateFor(projectId)).toBe('failed');
  });

  it('does not reconnect after disposal', () => {
    const connectJobEvents = vi.fn().mockReturnValue(() => undefined);
    const model = new BackgroundProcessing(
      api({ connectJobEvents }),
      () => null,
    );
    model.dispose();
    model.start();
    expect(connectJobEvents).not.toHaveBeenCalled();
  });
});
