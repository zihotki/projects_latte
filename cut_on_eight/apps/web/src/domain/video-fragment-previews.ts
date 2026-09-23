import type { ThumbnailManifestV1 } from '@cut-on-eight/legacy-contracts';
import type { FragmentPreview } from './catalogue-model.js';

const targets = [0.1, 0.3, 0.5, 0.7, 0.9] as const;

export function selectVideoFragmentPreviews(
  manifest: ThumbnailManifestV1 | null,
  startSeconds: number,
  endSeconds: number,
): FragmentPreview[] {
  if (manifest === null || manifest.samples.length === 0) return [];
  const inRange = manifest.samples
    .map((sample, index) => ({ sample, index }))
    .filter(
      ({ sample }) => sample[0] >= startSeconds && sample[0] <= endSeconds,
    );
  const candidates =
    inRange.length > 0
      ? inRange
      : manifest.samples.map((sample, index) => ({ sample, index }));
  const selected = new Map<number, FragmentPreview>();
  const identity = `${manifest.generatorVersion}:${manifest.sourceFingerprint}`;
  for (const ratio of targets) {
    const target = startSeconds + (endSeconds - startSeconds) * ratio;
    const nearest = candidates.reduce((best, candidate) =>
      Math.abs(candidate.sample[0] - target) < Math.abs(best.sample[0] - target)
        ? candidate
        : best,
    );
    if (selected.has(nearest.index)) continue;
    const [sampleSeconds, pageIndex, x, y, width, height] = nearest.sample;
    const page = manifest.pages[pageIndex];
    if (page === undefined) continue;
    selected.set(nearest.index, {
      sampleSeconds,
      pageFileName: page[0],
      pageWidth: page[1],
      pageHeight: page[2],
      x,
      y,
      width,
      height,
      identity,
    });
  }
  return [...selected.values()].sort(
    (left, right) => left.sampleSeconds - right.sampleSeconds,
  );
}
