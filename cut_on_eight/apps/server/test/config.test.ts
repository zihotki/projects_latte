import { describe, expect, it } from 'vitest';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { getServerConfig } from '../src/config.js';

describe('getServerConfig', () => {
  it('uses a valid configured port', () => {
    expect(
      getServerConfig({
        CUT_ON_EIGHT_PORT: '4320',
        DATABASE_URL: 'postgres://localhost/catalog',
      }),
    ).toEqual({
      dataRoot: join(homedir(), 'cut-on-eight_data'),
      thumbnailRoot: join(homedir(), 'cut-on-eight_thumbnails'),
      thumbnailOriginUrl: 'http://127.0.0.1:4320',
      thumbnailOriginPort: 4320,
      databaseUrl: 'postgres://localhost/catalog',
      natsUrl: 'nats://127.0.0.1:4222',
      qdrantHttpUrl: null,
      qdrantApiKey: null,
      embeddingProfile: {
        id: 'embeddinggemma-v1',
        model: 'google/embeddinggemma-300M',
        dimensions: 768,
        baseUrl: null,
      },
      maxUploadBytes: 20 * 1024 ** 3,
      host: '127.0.0.1',
      port: 4320,
    });
  });

  it('accepts an absolute data-root override', () => {
    expect(
      getServerConfig({
        CUT_ON_EIGHT_DATA_ROOT: '/tmp/cut-on-eight-test',
        DATABASE_URL: 'postgres://localhost/catalog',
      }),
    ).toMatchObject({ dataRoot: '/tmp/cut-on-eight-test' });
  });

  it('rejects a relative data-root override', () => {
    expect(() =>
      getServerConfig({
        CUT_ON_EIGHT_DATA_ROOT: './cut-on-eight-test',
        DATABASE_URL: 'postgres://localhost/catalog',
      }),
    ).toThrow('CUT_ON_EIGHT_DATA_ROOT must be an absolute path');
  });

  it.each(['0', '65536', '4318garbage', ' 4318'])(
    'rejects invalid port %s',
    (port) => {
      expect(() =>
        getServerConfig({
          CUT_ON_EIGHT_PORT: port,
          DATABASE_URL: 'postgres://localhost/catalog',
        }),
      ).toThrow('CUT_ON_EIGHT_PORT must be an integer from 1 to 65535');
    },
  );

  it('prefers Aspire connection and Qdrant variables', () => {
    expect(
      getServerConfig({
        ConnectionStrings__catalog: 'postgres://aspire/catalog',
        DATABASE_URL: 'postgres://fallback/catalog',
        QDRANT_HTTPURI: 'http://qdrant:6333',
        QDRANT_APIKEY: 'secret',
      }),
    ).toMatchObject({
      databaseUrl: 'postgres://aspire/catalog',
      qdrantHttpUrl: 'http://qdrant:6333',
      qdrantApiKey: 'secret',
    });
  });

  it('requires a database URL without exposing credentials', () => {
    expect(() => getServerConfig({})).toThrow(
      'ConnectionStrings__catalog or DATABASE_URL must be configured',
    );
    expect(() =>
      getServerConfig({ DATABASE_URL: 'not a url:with-secret' }),
    ).toThrow('Configured database URL is not a valid URL');
  });

  it('uses the default EmbeddingGemma profile without an endpoint', () => {
    expect(
      getServerConfig({ DATABASE_URL: 'postgres://catalog' }).embeddingProfile,
    ).toEqual({
      id: 'embeddinggemma-v1',
      model: 'google/embeddinggemma-300M',
      dimensions: 768,
      baseUrl: null,
    });
  });

  it('rejects embedding URLs with unsupported protocols', () => {
    expect(() =>
      getServerConfig({
        DATABASE_URL: 'postgres://catalog',
        CUT_ON_EIGHT_EMBEDDINGS_URL: 'ftp://localhost/v1',
      }),
    ).toThrow('embedding URL uses an unsupported protocol');
  });
});
