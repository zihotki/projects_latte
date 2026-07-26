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
      databaseUrl: 'postgres://localhost/catalog',
      qdrantHttpUrl: null,
      qdrantApiKey: null,
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
});
