import { describe, expect, it } from 'vitest';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { getServerConfig } from '../src/config.js';

describe('getServerConfig', () => {
  it('uses a valid configured port', () => {
    expect(getServerConfig({ CUT_ON_EIGHT_PORT: '4320' })).toEqual({
      dataRoot: join(homedir(), 'cut-on-eight_data'),
      host: '127.0.0.1',
      port: 4320,
    });
  });

  it('accepts an absolute data-root override', () => {
    expect(
      getServerConfig({ CUT_ON_EIGHT_DATA_ROOT: '/tmp/cut-on-eight-test' }),
    ).toMatchObject({ dataRoot: '/tmp/cut-on-eight-test' });
  });

  it('rejects a relative data-root override', () => {
    expect(() =>
      getServerConfig({ CUT_ON_EIGHT_DATA_ROOT: './cut-on-eight-test' }),
    ).toThrow('CUT_ON_EIGHT_DATA_ROOT must be an absolute path');
  });

  it.each(['0', '65536', '4318garbage', ' 4318'])(
    'rejects invalid port %s',
    (port) => {
      expect(() => getServerConfig({ CUT_ON_EIGHT_PORT: port })).toThrow(
        'CUT_ON_EIGHT_PORT must be an integer from 1 to 65535',
      );
    },
  );
});
