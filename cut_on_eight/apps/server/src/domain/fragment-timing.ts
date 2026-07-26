import { DomainConflict } from './models.js';

export interface FragmentTiming {
  readonly id: string;
  readonly startUs: number;
  readonly endUs: number;
}

export function validateFragmentSet(
  fragments: readonly FragmentTiming[],
  durationUs: number | null,
): void {
  const ids = new Set<string>();
  const events: Array<{ time: number; delta: -1 | 1 }> = [];
  for (const fragment of fragments) {
    if (
      ids.has(fragment.id) ||
      !Number.isSafeInteger(fragment.startUs) ||
      !Number.isSafeInteger(fragment.endUs) ||
      fragment.startUs < 0 ||
      fragment.endUs <= fragment.startUs ||
      (durationUs !== null && fragment.endUs > durationUs)
    ) {
      throw new DomainConflict(
        'fragment_timing_conflict',
        'Fragment timing is invalid.',
      );
    }
    ids.add(fragment.id);
    events.push(
      { time: fragment.startUs, delta: 1 },
      { time: fragment.endUs, delta: -1 },
    );
  }
  events.sort(
    (left, right) => left.time - right.time || left.delta - right.delta,
  );
  let active = 0;
  for (const event of events) {
    active += event.delta;
    if (active > 2) {
      throw new DomainConflict(
        'fragment_timing_conflict',
        'At most two fragments may overlap.',
      );
    }
  }
}
