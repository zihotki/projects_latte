import {
  healthLiveSchema,
  healthReadySchema,
} from '@cut-on-eight/api-contracts';
import { describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import { qdrantReadinessDeadlineMs } from '../src/api/health-routes.js';

const config = {
  dataRoot: '/tmp/cut-on-eight-health-test',
  databaseUrl: 'postgres://localhost/cut_on_eight_test',
  qdrantHttpUrl: null,
  qdrantApiKey: null,
  host: '127.0.0.1',
  port: 4318,
} as const;

describe('GET /api/health', () => {
  it('returns the shared health contract', async () => {
    const app = createApp({ config });

    const response = await app.inject({
      method: 'GET',
      url: '/api/health',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      status: 'ok',
      service: 'cut-on-eight-server',
    });

    await app.close();
  });

  it('reports process liveness without probing dependencies', async () => {
    const app = createApp({ config });

    const response = await app.inject({
      method: 'GET',
      url: '/api/health/live',
    });

    expect(response.statusCode).toBe(200);
    expect(healthLiveSchema.parse(response.json())).toEqual({
      status: 'live',
      service: 'cut-on-eight-server',
    });

    await app.close();
  });

  it('degrades promptly when a Qdrant probe never settles', async () => {
    const app = createApp({
      config,
      healthProbes: {
        postgres: async () => undefined,
        qdrant: async () => new Promise<void>(() => undefined),
        worker: async () => true,
      },
    });
    const startedAt = performance.now();

    const response = await app.inject({
      method: 'GET',
      url: '/api/health/ready',
    });
    const elapsedMs = performance.now() - startedAt;

    expect(response.statusCode).toBe(200);
    expect(healthReadySchema.parse(response.json())).toMatchObject({
      status: 'ready',
      dependencies: {
        postgres: 'ready',
        qdrant: 'degraded',
        worker: 'ready',
      },
    });
    expect(elapsedMs).toBeGreaterThanOrEqual(qdrantReadinessDeadlineMs - 50);
    expect(elapsedMs).toBeLessThan(qdrantReadinessDeadlineMs + 500);

    await app.close();
  });
});
