import type {
  Capabilities,
  JobRecord,
  JobSnapshot,
  ProjectDocument,
  WorkspaceSnapshot,
} from '@cut-on-eight/legacy-contracts';
import { describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import type { ManagedSource, AppServices } from '../src/services.js';

const emptyJobs: JobSnapshot = { jobs: [], errors: [] };

function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
} {
  let resolve!: (value: T) => void;
  return {
    promise: new Promise<T>((complete) => {
      resolve = complete;
    }),
    resolve,
  };
}

async function until(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 500; attempt += 1) {
    if (predicate()) return;
    await new Promise<void>((resolve) => setTimeout(resolve, 2));
  }
  throw new Error('Condition was not reached');
}

function services(getJobs: () => Promise<JobSnapshot>): {
  service: AppServices;
  subscriptions: { active: number; removed: number };
} {
  const subscriptions = { active: 0, removed: 0 };
  const unused = async (): Promise<never> => {
    throw new Error('Unexpected service call');
  };
  return {
    subscriptions,
    service: {
      activateProject: unused as (id: string) => Promise<WorkspaceSnapshot>,
      closeProject: unused as (
        id: string,
        document: ProjectDocument,
      ) => Promise<WorkspaceSnapshot>,
      getCapabilities: async (): Promise<Capabilities> => ({
        backendAvailable: true,
        ffprobeAvailable: false,
      }),
      getJobs,
      getThumbnailManifest: unused,
      getWorkspace: unused as () => Promise<WorkspaceSnapshot>,
      openProject: unused as (id: string) => Promise<WorkspaceSnapshot>,
      openSource: unused as (id: string) => Promise<ManagedSource>,
      openThumbnailPage: unused,
      recover: async () => undefined,
      retryJob: unused as (id: string) => Promise<JobRecord>,
      saveProject: unused as (
        id: string,
        document: ProjectDocument,
      ) => Promise<ProjectDocument>,
      selectImport: unused,
      subscribeToJobs: () => {
        subscriptions.active += 1;
        let subscribed = true;
        return () => {
          if (!subscribed) return;
          subscribed = false;
          subscriptions.active -= 1;
          subscriptions.removed += 1;
        };
      },
    },
  };
}

describe('job event route lifecycle', () => {
  it('ends active SSE responses during app shutdown', async () => {
    const fixture = services(async () => emptyJobs);
    const app = createApp({ services: fixture.service });
    const responsePromise = app.inject({ method: 'GET', url: '/api/events' });
    await until(() => fixture.subscriptions.active === 1);

    await app.close();
    const response = await responsePromise;

    expect(response.statusCode).toBe(200);
    expect(response.body).toContain('event: jobs');
    expect(fixture.subscriptions).toEqual({ active: 0, removed: 1 });
  });

  it('does not establish an SSE stream after shutdown starts', async () => {
    const jobs = deferred<JobSnapshot>();
    const fixture = services(() => jobs.promise);
    const app = createApp({ services: fixture.service });
    const responsePromise = app.inject({ method: 'GET', url: '/api/events' });
    await until(() => fixture.subscriptions.active === 1);

    const closePromise = app.close();
    await until(() => fixture.subscriptions.active === 0);
    jobs.resolve(emptyJobs);
    await closePromise;
    const response = await responsePromise;

    expect(response.statusCode).toBe(200);
    expect(fixture.subscriptions).toEqual({ active: 0, removed: 1 });
  });

  it('removes the listener when the client disconnects during initial load', async () => {
    const jobs = deferred<JobSnapshot>();
    const fixture = services(() => jobs.promise);
    const app = createApp({ services: fixture.service });
    const controller = new AbortController();
    const responsePromise = app
      .inject({ method: 'GET', url: '/api/events', signal: controller.signal })
      .catch(() => undefined);
    await until(() => fixture.subscriptions.active === 1);

    controller.abort();
    await until(() => fixture.subscriptions.active === 0);
    jobs.resolve(emptyJobs);
    await responsePromise;
    await app.close();

    expect(fixture.subscriptions.removed).toBe(1);
  });
});
