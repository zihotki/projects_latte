import { describe, expect, it } from 'vitest';
import { healthResponseSchema } from '../src/health.js';

describe('healthResponseSchema', () => {
  it('accepts the server health payload', () => {
    expect(
      healthResponseSchema.parse({
        status: 'ok',
        service: 'cut-on-eight-server',
      }),
    ).toEqual({
      status: 'ok',
      service: 'cut-on-eight-server',
    });
  });
});
