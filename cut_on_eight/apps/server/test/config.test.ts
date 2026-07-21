import { describe, expect, it } from 'vitest';
import { getServerConfig } from '../src/config.js';

describe('getServerConfig', () => {
  it('uses a valid configured port', () => {
    expect(getServerConfig({ CUT_ON_EIGHT_PORT: '4320' })).toEqual({
      host: '127.0.0.1',
      port: 4320,
    });
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
