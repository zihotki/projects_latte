import type { EmbeddingProfile } from '../config.js';
import {
  createRemoteCallPolicy,
  RemoteCallError,
  type ResilientCall,
} from '../resilience/remote-call.js';

export interface EmbeddingClient {
  available(): boolean;
  embed(texts: readonly string[]): Promise<readonly number[][]>;
}

export class EmbeddingUnavailableError extends Error {
  readonly code = 'embedding_unavailable';

  constructor() {
    super('Embeddings are not configured.');
    this.name = 'EmbeddingUnavailableError';
  }
}

export function createEmbeddingClient(
  profile: EmbeddingProfile,
  resilientCall: ResilientCall = createRemoteCallPolicy(),
): EmbeddingClient {
  const baseUrl = profile.baseUrl;
  if (baseUrl === null) return new UnavailableEmbeddingClient();
  return new LmStudioEmbeddingClient(profile, baseUrl, resilientCall);
}

class UnavailableEmbeddingClient implements EmbeddingClient {
  available(): false {
    return false;
  }

  async embed(texts: readonly string[]): Promise<readonly number[][]> {
    void texts;
    throw new EmbeddingUnavailableError();
  }
}

class LmStudioEmbeddingClient implements EmbeddingClient {
  constructor(
    private readonly profile: EmbeddingProfile,
    private readonly baseUrl: string,
    private readonly resilientCall: ResilientCall,
  ) {}

  available(): true {
    return true;
  }

  async embed(texts: readonly string[]): Promise<readonly number[][]> {
    if (texts.length === 0) return [];

    return this.resilientCall.execute(async (signal) => {
      const response = await fetch(embeddingUrl(this.baseUrl), {
        method: 'POST',
        headers: {
          accept: 'application/json',
          'content-type': 'application/json',
        },
        body: JSON.stringify({ model: this.profile.model, input: texts }),
        signal,
      }).catch((error: unknown) => {
        throw remoteFailure(error);
      });
      if (!response.ok) {
        throw new RemoteCallError(response.status, 'Embedding request failed.');
      }

      let body: unknown;
      try {
        body = await response.json();
      } catch (error) {
        throw new RemoteCallError(
          null,
          `Embedding response was not valid JSON${error instanceof Error ? `: ${error.message}` : '.'}`,
        );
      }
      return parseEmbeddings(body, texts.length, this.profile.dimensions);
    });
  }
}

function embeddingUrl(baseUrl: string): URL {
  return new URL('embeddings', `${baseUrl}/`);
}

function parseEmbeddings(
  body: unknown,
  expectedCount: number,
  expectedDimensions: number,
): number[][] {
  if (!isRecord(body) || !Array.isArray(body.data)) {
    throw new RemoteCallError(null, 'Embedding response did not contain data.');
  }
  if (body.data.length !== expectedCount) {
    throw new RemoteCallError(
      null,
      `Embedding response returned ${body.data.length} vectors; expected ${expectedCount}.`,
    );
  }

  return body.data.map((item, position) => {
    if (
      !isRecord(item) ||
      item.index !== position ||
      !Array.isArray(item.embedding)
    ) {
      throw new RemoteCallError(
        null,
        `Embedding response vector at index ${position} was invalid or out of order.`,
      );
    }
    if (item.embedding.length !== expectedDimensions) {
      throw new RemoteCallError(
        null,
        `Embedding response vector has ${item.embedding.length} dimensions; expected ${expectedDimensions}.`,
      );
    }
    if (
      !item.embedding.every(
        (value) => typeof value === 'number' && Number.isFinite(value),
      )
    ) {
      throw new RemoteCallError(
        null,
        `Embedding response vector at index ${position} contains a non-finite value.`,
      );
    }
    return item.embedding;
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function remoteFailure(error: unknown): RemoteCallError {
  if (error instanceof RemoteCallError) return error;
  return new RemoteCallError(
    null,
    `Embedding request failed${error instanceof Error ? `: ${error.message}` : '.'}`,
  );
}
