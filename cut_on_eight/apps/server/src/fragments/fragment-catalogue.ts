import {
  fragmentCatalogueSchema,
  type FragmentCatalogue,
  type FragmentPreview,
  type ProjectDocument,
  type Segment,
  type ThumbnailManifestV1,
} from '@cut-on-eight/legacy-contracts';

const targets = [0.1, 0.3, 0.5, 0.7, 0.9] as const;

export function selectFragmentPreviews(
  segment: Segment,
  manifest: ThumbnailManifestV1 | undefined,
): FragmentPreview[] {
  if (manifest === undefined) return [];
  const selected = new Map<number, FragmentPreview>();
  const identity = `${manifest.generatorVersion}:${manifest.sourceFingerprint}`;

  for (const ratio of targets) {
    const target =
      segment.startSeconds +
      (segment.endSeconds - segment.startSeconds) * ratio;
    let nearestIndex = 0;
    let distance = Infinity;
    for (const [index, sample] of manifest.samples.entries()) {
      const nextDistance = Math.abs(sample[0] - target);
      if (nextDistance < distance) {
        nearestIndex = index;
        distance = nextDistance;
      }
    }
    const sample = manifest.samples[nearestIndex];
    if (sample === undefined || selected.has(nearestIndex)) continue;
    const [sampleSeconds, pageIndex, x, y, width, height] = sample;
    const page = manifest.pages[pageIndex];
    if (page === undefined) continue;
    selected.set(nearestIndex, {
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

export function validateFragmentTiming(
  segments: readonly Segment[],
  candidate: Segment,
  durationSeconds: number | null,
): { code: string; message: string } | null {
  if (candidate.endSeconds <= candidate.startSeconds) {
    return {
      code: 'invalid_range',
      message: 'Fragment end must be after its start.',
    };
  }
  if (
    durationSeconds === null ||
    candidate.startSeconds < 0 ||
    candidate.endSeconds > durationSeconds
  ) {
    return {
      code: 'outside_source',
      message: 'Fragment must stay within the source video.',
    };
  }
  const events = [
    ...segments.filter((item) => item.id !== candidate.id),
    candidate,
  ]
    .flatMap((item) => [
      { seconds: item.startSeconds, delta: 1 },
      { seconds: item.endSeconds, delta: -1 },
    ])
    .sort(
      (left, right) => left.seconds - right.seconds || left.delta - right.delta,
    );
  let depth = 0;
  for (const event of events) {
    depth += event.delta;
    if (depth > 2)
      return {
        code: 'triple_overlap',
        message: 'At most two fragments can overlap.',
      };
  }
  return null;
}

export function catalogueResponse(value: FragmentCatalogue): FragmentCatalogue {
  return fragmentCatalogueSchema.parse(value);
}

export function orderedSegments(project: ProjectDocument): Segment[] {
  return [...project.segments].sort(
    (left, right) =>
      left.startSeconds - right.startSeconds ||
      left.endSeconds - right.endSeconds,
  );
}
