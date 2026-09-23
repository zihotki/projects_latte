import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterAll, beforeAll, describe, expect, test } from 'vitest';
import type { EmbeddingProfile } from '../src/config.js';
import {
  createEmbeddingClient,
  EmbeddingUnavailableError,
} from '../src/search/embedding-client.js';
import type { ResilientCall } from '../src/resilience/remote-call.js';

const profile: EmbeddingProfile = {
  id: 'test-v1',
  model: 'test-embedding-model',
  dimensions: 3,
  baseUrl: null,
};

const directCall: ResilientCall = {
  execute: (operation) => operation(new AbortController().signal),
};

describe('LM Studio embedding client', () => {
  let server: Server;
  let baseUrl: string;
  let respond: (request: RecordedRequest) => FakeResponse;

  beforeAll(async () => {
    respond = () => ({
      status: 200,
      body: { data: [{ index: 0, embedding: [0.1, 0.2, 0.3] }] },
    });
    server = createServer(async (request, response) => {
      const body = await readBody(request);
      const result = respond({
        method: request.method,
        url: request.url,
        body: JSON.parse(body) as unknown,
      });
      response.statusCode = result.status;
      response.setHeader(
        'content-type',
        result.contentType ?? 'application/json',
      );
      response.end(
        typeof result.body === 'string'
          ? result.body
          : JSON.stringify(result.body),
      );
    });
    await new Promise<void>((resolve) =>
      server.listen(0, '127.0.0.1', resolve),
    );
    const address = server.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${address.port}/v1`;
  });

  afterAll(async () => {
    if (!server.listening) return;
    await new Promise<void>((resolve, reject) =>
      server.close((error) =>
        error === undefined ? resolve() : reject(error),
      ),
    );
  });

  test('posts OpenAI-compatible requests and returns validated vectors', async () => {
    let received: RecordedRequest | undefined;
    respond = (request) => {
      received = request;
      return {
        status: 200,
        body: { data: [{ index: 0, embedding: [0.1, 0.2, 0.3] }] },
      };
    };

    const client = createEmbeddingClient({ ...profile, baseUrl }, directCall);

    await expect(client.embed(['a fragment'])).resolves.toEqual([
      [0.1, 0.2, 0.3],
    ]);
    expect(received).toEqual({
      method: 'POST',
      url: '/v1/embeddings',
      body: { model: 'test-embedding-model', input: ['a fragment'] },
    });
  });

  test('rejects vectors with the wrong configured dimensions', async () => {
    respond = () => ({
      status: 200,
      body: { data: [{ index: 0, embedding: [0.1, 0.2] }] },
    });
    const client = createEmbeddingClient({ ...profile, baseUrl }, directCall);

    await expect(client.embed(['a fragment'])).rejects.toThrow(
      'Embedding response vector has 2 dimensions; expected 3.',
    );
  });

  test('rejects out-of-order and non-finite vectors', async () => {
    respond = () => ({
      status: 200,
      body: { data: [{ index: 1, embedding: [0.1, 0.2, 0.3] }] },
    });
    const client = createEmbeddingClient({ ...profile, baseUrl }, directCall);
    await expect(client.embed(['a fragment'])).rejects.toThrow('out of order');

    respond = () => ({
      status: 200,
      body: { data: [{ index: 0, embedding: [0.1, null, 0.3] }] },
    });
    await expect(client.embed(['a fragment'])).rejects.toThrow('non-finite');
  });

  test('treats failed and malformed remote responses as retryable failures', async () => {
    respond = () => ({ status: 502, body: { error: 'offline' } });
    const client = createEmbeddingClient({ ...profile, baseUrl }, directCall);
    await expect(client.embed(['a fragment'])).rejects.toMatchObject({
      name: 'RemoteCallError',
      status: 502,
    });

    respond = () => ({
      status: 200,
      body: 'not json',
      contentType: 'text/plain',
    });
    await expect(client.embed(['a fragment'])).rejects.toMatchObject({
      name: 'RemoteCallError',
      status: null,
    });
  });

  test('is explicitly unavailable without a configured endpoint', async () => {
    const client = createEmbeddingClient(profile, directCall);

    expect(client.available()).toBe(false);
    await expect(client.embed(['a fragment'])).rejects.toBeInstanceOf(
      EmbeddingUnavailableError,
    );
  });
});

interface RecordedRequest {
  readonly method: string | undefined;
  readonly url: string | undefined;
  readonly body: unknown;
}

interface FakeResponse {
  readonly status: number;
  readonly body: unknown;
  readonly contentType?: string;
}

async function readBody(
  request: Parameters<typeof createServer>[0] extends (
    request: infer Request,
    ...args: never[]
  ) => unknown
    ? Request
    : never,
): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString('utf8');
}
