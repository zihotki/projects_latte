import { describe, expect, test } from 'vitest';
import { validateFragmentSet } from '../src/domain/fragment-timing.js';

describe('validateFragmentSet', () => {
  test('allows touching boundaries and two overlaps', () => {
    expect(() =>
      validateFragmentSet(
        [
          { id: 'a', startUs: 0, endUs: 2_000_000 },
          { id: 'b', startUs: 1_000_000, endUs: 3_000_000 },
          { id: 'c', startUs: 2_000_000, endUs: 4_000_000 },
        ],
        4_000_000,
      ),
    ).not.toThrow();
  });

  test('rejects a third simultaneous fragment', () => {
    expect(() =>
      validateFragmentSet(
        [
          { id: 'a', startUs: 0, endUs: 3_000_000 },
          { id: 'b', startUs: 1_000_000, endUs: 4_000_000 },
          { id: 'c', startUs: 2_000_000, endUs: 5_000_000 },
        ],
        6_000_000,
      ),
    ).toThrow(/two fragments/);
  });
});
