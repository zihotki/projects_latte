import type { AppServices } from '../src/services.js';
import { describe, expect, it, vi } from 'vitest';
import { createApp } from '../src/app.js';

function services(overrides: Partial<AppServices> = {}): AppServices {
  const unused = async (): Promise<never> => {
    throw new Error('Unexpected service call');
  };

  return {
    activateProject: unused,
    closeProject: unused,
    getCapabilities: unused,
    getJobs: unused,
    getThumbnailManifest: unused,
    getWorkspace: unused,
    openProject: unused,
    openSource: unused,
    openThumbnailPage: unused,
    recover: async () => undefined,
    retryJob: unused,
    saveProject: unused,
    selectImport: unused,
    subscribeToJobs: () => () => undefined,
    ...overrides,
  };
}

describe('API request protection', () => {
  it.each([
    ['existing injected requests', undefined],
    ['Vite proxy requests', { host: '127.0.0.1:4318' }],
    [
      'Vite requests from localhost',
      {
        host: '127.0.0.1:4318',
        origin: 'http://localhost:5173',
        'sec-fetch-site': 'cross-site',
      },
    ],
    [
      'Vite requests from 127.0.0.1',
      {
        host: 'localhost:4318',
        origin: 'http://127.0.0.1:5173',
        'sec-fetch-site': 'same-site',
      },
    ],
    [
      'direct same-host requests',
      {
        host: '[::1]:4318',
        origin: 'http://[::1]:4318',
        'sec-fetch-site': 'same-origin',
      },
    ],
  ])('permits %s', async (_name, headers) => {
    const app = createApp({ services: services() });
    const response = await app.inject({
      method: 'GET',
      url: '/api/health',
      headers,
    });

    expect(response.statusCode).toBe(200);
    await app.close();
  });

  it.each([
    ['evil.example', 403, 'forbidden_request_host'],
    ['localhost:99999', 403, 'forbidden_request_host'],
    ['[::1', 403, 'forbidden_request_host'],
  ])('rejects unsafe Host %s', async (host, status, code) => {
    const app = createApp({ services: services() });
    const response = await app.inject({
      method: 'GET',
      url: '/api/health',
      headers: { host },
    });

    expect(response.statusCode).toBe(status);
    expect(response.json()).toEqual({
      error: {
        code,
        message: 'The request Host is not allowed.',
        retryable: false,
      },
    });
    expect(response.body).not.toContain(host);
    await app.close();
  });

  it('rejects a cross-origin picker request before opening the picker', async () => {
    const selectImport = vi.fn();
    const app = createApp({ services: services({ selectImport }) });
    const response = await app.inject({
      method: 'POST',
      url: '/api/imports/select',
      headers: {
        origin: 'http://evil.example',
        'sec-fetch-site': 'cross-site',
      },
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toEqual({
      error: {
        code: 'forbidden_request_origin',
        message: 'The request Origin is not allowed.',
        retryable: false,
      },
    });
    expect(selectImport).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects a cross-site source request before opening the source', async () => {
    const openSource = vi.fn();
    const app = createApp({ services: services({ openSource }) });
    const response = await app.inject({
      method: 'GET',
      url: '/api/sources/20000000-0000-4000-8000-000000000001/content',
      headers: { 'sec-fetch-site': 'cross-site' },
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toEqual({
      error: {
        code: 'forbidden_request_origin',
        message: 'Cross-site browser requests are not allowed.',
        retryable: false,
      },
    });
    expect(openSource).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects a malformed Origin without reflecting it', async () => {
    const origin = 'http://localhost:5173/private/source.mp4';
    const app = createApp({ services: services() });
    const response = await app.inject({
      method: 'GET',
      url: '/api/health',
      headers: { origin },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toEqual({
      error: {
        code: 'invalid_request_origin',
        message: 'The request Origin header is invalid.',
        retryable: false,
      },
    });
    expect(response.body).not.toContain(origin);
    expect(response.body).not.toContain('/private/source.mp4');
    await app.close();
  });
});
