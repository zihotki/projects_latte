import { homedir } from 'node:os';
import { isAbsolute, join } from 'node:path';

export interface ServerConfig {
  dataRoot: string;
  thumbnailRoot: string;
  thumbnailOriginUrl: string;
  thumbnailOriginPort: number;
  databaseUrl: string;
  natsUrl: string;
  qdrantHttpUrl: string | null;
  qdrantApiKey: string | null;
  embeddingProfile: EmbeddingProfile;
  maxUploadBytes: number;
  host: '127.0.0.1' | '0.0.0.0';
  publicOrigin?: string | null;
  port: number;
}

export interface EmbeddingProfile {
  readonly id: string;
  readonly model: string;
  readonly dimensions: number;
  readonly baseUrl: string | null;
}

export function getServerConfig(
  environment: NodeJS.ProcessEnv = process.env,
): ServerConfig {
  const portText = environment.CUT_ON_EIGHT_PORT ?? '4318';
  const port = Number(portText);

  if (
    !/^[1-9]\d*$/.test(portText) ||
    !Number.isInteger(port) ||
    port > 65_535
  ) {
    throw new Error('CUT_ON_EIGHT_PORT must be an integer from 1 to 65535');
  }

  const dataRoot =
    environment.CUT_ON_EIGHT_DATA_ROOT ?? join(homedir(), 'cut-on-eight_data');

  if (!isAbsolute(dataRoot)) {
    throw new Error('CUT_ON_EIGHT_DATA_ROOT must be an absolute path');
  }
  const thumbnailRoot =
    environment.CUT_ON_EIGHT_THUMBNAIL_ROOT ??
    join(homedir(), 'cut-on-eight_thumbnails');
  if (!isAbsolute(thumbnailRoot)) {
    throw new Error('CUT_ON_EIGHT_THUMBNAIL_ROOT must be an absolute path');
  }
  const thumbnailOriginPortText =
    environment.CUT_ON_EIGHT_THUMBNAIL_ORIGIN_PORT ?? '4320';
  const thumbnailOriginPort = Number(thumbnailOriginPortText);
  if (
    !/^[1-9]\d*$/.test(thumbnailOriginPortText) ||
    !Number.isInteger(thumbnailOriginPort) ||
    thumbnailOriginPort > 65_535
  ) {
    throw new Error(
      'CUT_ON_EIGHT_THUMBNAIL_ORIGIN_PORT must be an integer from 1 to 65535',
    );
  }
  const thumbnailOriginUrl =
    environment.CUT_ON_EIGHT_THUMBNAIL_ORIGIN_URL ??
    `http://127.0.0.1:${thumbnailOriginPort}`;
  assertUrl(thumbnailOriginUrl, ['http:', 'https:'], 'thumbnail origin URL');
  const publicOrigin = environment.CUT_ON_EIGHT_PUBLIC_ORIGIN ?? null;
  if (publicOrigin !== null) {
    assertUrl(publicOrigin, ['http:', 'https:'], 'public origin');
    const parsed = new URL(publicOrigin);
    if (
      parsed.origin !== publicOrigin ||
      parsed.username !== '' ||
      parsed.password !== ''
    ) {
      throw new Error('CUT_ON_EIGHT_PUBLIC_ORIGIN must be an exact origin');
    }
  }
  const host = environment.CUT_ON_EIGHT_HOST ?? '127.0.0.1';
  if (host !== '127.0.0.1' && host !== '0.0.0.0') {
    throw new Error('CUT_ON_EIGHT_HOST must be 127.0.0.1 or 0.0.0.0');
  }
  if (host === '0.0.0.0' && publicOrigin === null) {
    throw new Error(
      'CUT_ON_EIGHT_PUBLIC_ORIGIN is required for a network listener',
    );
  }
  const natsUrl = environment.NATS_URL ?? 'nats://127.0.0.1:4222';
  assertUrl(natsUrl, ['nats:', 'tls:'], 'NATS URL');

  const databaseUrl =
    environment.ConnectionStrings__catalog ?? environment.DATABASE_URL;
  if (databaseUrl === undefined || databaseUrl.trim() === '') {
    throw new Error(
      'ConnectionStrings__catalog or DATABASE_URL must be configured',
    );
  }
  assertUrl(databaseUrl, ['postgres:', 'postgresql:'], 'database URL');

  const qdrantHttpUrl =
    environment.QDRANT_HTTPURI ?? environment.QDRANT_HTTP_URL ?? null;
  if (qdrantHttpUrl !== null) {
    assertUrl(qdrantHttpUrl, ['http:', 'https:'], 'Qdrant URL');
  }
  const embeddingProfile = getEmbeddingProfile(environment);
  const maxUploadBytes = Number(
    environment.CUT_ON_EIGHT_MAX_UPLOAD_BYTES ?? 20 * 1024 ** 3,
  );
  if (!Number.isSafeInteger(maxUploadBytes) || maxUploadBytes <= 0) {
    throw new Error('CUT_ON_EIGHT_MAX_UPLOAD_BYTES must be a positive integer');
  }

  return {
    dataRoot,
    thumbnailRoot,
    thumbnailOriginUrl,
    thumbnailOriginPort,
    databaseUrl,
    natsUrl,
    qdrantHttpUrl,
    qdrantApiKey: environment.QDRANT_APIKEY ?? null,
    embeddingProfile,
    maxUploadBytes,
    host,
    publicOrigin,
    port,
  };
}

function getEmbeddingProfile(environment: NodeJS.ProcessEnv): EmbeddingProfile {
  const id = environment.CUT_ON_EIGHT_EMBEDDING_PROFILE ?? 'embeddinggemma-v1';
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(id)) {
    throw new Error(
      'CUT_ON_EIGHT_EMBEDDING_PROFILE must be a lowercase identifier up to 64 characters',
    );
  }

  const model = (
    environment.CUT_ON_EIGHT_EMBEDDING_MODEL ?? 'google/embeddinggemma-300M'
  ).trim();
  if (model === '') {
    throw new Error('CUT_ON_EIGHT_EMBEDDING_MODEL must not be empty');
  }

  const dimensionsText = environment.CUT_ON_EIGHT_EMBEDDING_DIMENSIONS ?? '768';
  const dimensions = Number(dimensionsText);
  if (
    !/^[1-9]\d*$/.test(dimensionsText) ||
    !Number.isSafeInteger(dimensions) ||
    dimensions > 8_192
  ) {
    throw new Error(
      'CUT_ON_EIGHT_EMBEDDING_DIMENSIONS must be an integer from 1 to 8192',
    );
  }

  const baseUrl = environment.CUT_ON_EIGHT_EMBEDDINGS_URL ?? null;
  if (baseUrl !== null) {
    assertUrl(baseUrl, ['http:', 'https:'], 'embedding URL');
    const url = new URL(baseUrl);
    if (!url.pathname.endsWith('/v1') || url.search !== '' || url.hash !== '') {
      throw new Error('Configured embedding URL must end in /v1');
    }
  }

  return { id, model, dimensions, baseUrl };
}

function assertUrl(value: string, protocols: string[], label: string): void {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`Configured ${label} is not a valid URL`);
  }
  if (!protocols.includes(url.protocol)) {
    throw new Error(`Configured ${label} uses an unsupported protocol`);
  }
}
