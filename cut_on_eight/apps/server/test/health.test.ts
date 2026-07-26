import { healthLiveSchema } from '@cut-on-eight/api-contracts';
import { describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';

describe('GET /api/health', () => {
  it('returns the shared health contract', async () => {
    const app = createApp({
      config: {
        dataRoot: '/tmp/cut-on-eight-health-test',
        databaseUrl: 'postgres://localhost/cut_on_eight_test',
        qdrantHttpUrl: null,
        qdrantApiKey: null,
        host: '127.0.0.1',
        port: 4318,
      },
    });

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
    const app = createApp({
      config: {
        dataRoot: '/tmp/cut-on-eight-health-test',
        databaseUrl: 'postgres://localhost/cut_on_eight_test',
        qdrantHttpUrl: null,
        qdrantApiKey: null,
        host: '127.0.0.1',
        port: 4318,
      },
    });

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
});
