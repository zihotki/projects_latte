import type { ThumbnailManifestV1 } from '@cut-on-eight/contracts';

export interface ThumbnailScale {
  timeToPixel(seconds: number): number;
  visibleRange(): {
    readonly endSeconds: number;
    readonly startSeconds: number;
  };
}

export interface ThumbnailCanvasSize {
  readonly height: number;
  readonly width: number;
}

export interface ThumbnailDrawingContext<Image> {
  drawImage(
    image: Image,
    sourceX: number,
    sourceY: number,
    sourceWidth: number,
    sourceHeight: number,
    destinationX: number,
    destinationY: number,
    destinationWidth: number,
    destinationHeight: number,
  ): void;
}

export interface ThumbnailDrawResult {
  readonly drawn: number;
  readonly skipped: number;
}

export interface ThumbnailLoadResult<Image> {
  readonly failed: number;
  readonly images: ReadonlyMap<number, Image>;
}

export function visibleThumbnailPageIndexes(
  manifest: ThumbnailManifestV1,
  scale: ThumbnailScale,
): readonly number[] {
  const visible = scale.visibleRange();
  const pages = new Set<number>();

  for (const [index, sample] of manifest.samples.entries()) {
    const start = sample[0];
    const end = manifest.samples[index + 1]?.[0] ?? manifest.durationSeconds;
    if (end <= visible.startSeconds || start >= visible.endSeconds) continue;
    pages.add(sample[1]);
  }

  return [...pages];
}

export function drawVisibleThumbnails<Image>(
  context: ThumbnailDrawingContext<Image>,
  manifest: ThumbnailManifestV1,
  images: ReadonlyMap<number, Image>,
  scale: ThumbnailScale,
  canvasSize: ThumbnailCanvasSize,
): ThumbnailDrawResult {
  const visible = scale.visibleRange();
  let drawn = 0;
  let skipped = 0;

  for (const [index, sample] of manifest.samples.entries()) {
    const [time, pageIndex, x, y, width, height] = sample;
    const end = manifest.samples[index + 1]?.[0] ?? manifest.durationSeconds;
    const image = images.get(pageIndex);

    if (
      end <= visible.startSeconds ||
      time >= visible.endSeconds ||
      image === undefined ||
      canvasSize.width <= 0 ||
      canvasSize.height <= 0
    ) {
      skipped += 1;
      continue;
    }

    const destinationX = scale.timeToPixel(time);
    const destinationWidth = Math.max(1, scale.timeToPixel(end) - destinationX);
    context.drawImage(
      image,
      x,
      y,
      width,
      height,
      destinationX,
      0,
      destinationWidth,
      canvasSize.height,
    );
    drawn += 1;
  }

  return { drawn, skipped };
}

type ImageFactory<Image> = (url: string) => Promise<Image>;

function manifestKey(projectId: string, manifest: ThumbnailManifestV1): string {
  return [
    projectId,
    manifest.schemaVersion,
    manifest.generatorVersion,
    manifest.sourceFingerprint,
  ].join('\u0000');
}

export class ThumbnailImageCache<Image> {
  private activeKey: string | null = null;
  private readonly cache = new Map<string, Promise<Image>>();
  private readonly projectKeys = new Map<string, string>();

  constructor(private readonly createImage: ImageFactory<Image>) {}

  async loadVisible(
    projectId: string,
    manifest: ThumbnailManifestV1,
    pageIndexes: readonly number[],
    pageUrl: (fileName: string) => string,
  ): Promise<ThumbnailLoadResult<Image> | null> {
    const key = manifestKey(projectId, manifest);
    this.invalidateChangedManifest(projectId, key);
    this.activeKey = key;

    const entries = await Promise.all(
      pageIndexes.map(async (pageIndex) => {
        const page = manifest.pages[pageIndex];
        if (page === undefined) return null;
        const cacheKey = `${key}\u0000${pageIndex}`;
        let loaded = this.cache.get(cacheKey);
        if (loaded === undefined) {
          loaded = this.createImage(pageUrl(page[0])).catch((error) => {
            this.cache.delete(cacheKey);
            throw error;
          });
          this.cache.set(cacheKey, loaded);
        }
        try {
          return [pageIndex, await loaded] as const;
        } catch {
          return null;
        }
      }),
    );

    if (this.activeKey !== key) return null;
    return {
      failed: entries.filter((entry) => entry === null).length,
      images: new Map(entries.filter((entry) => entry !== null)),
    };
  }

  deactivate(): void {
    this.activeKey = null;
  }

  private invalidateChangedManifest(projectId: string, nextKey: string): void {
    const previousKey = this.projectKeys.get(projectId);
    if (previousKey !== undefined && previousKey !== nextKey) {
      for (const key of this.cache.keys()) {
        if (key.startsWith(`${previousKey}\u0000`)) this.cache.delete(key);
      }
    }
    this.projectKeys.set(projectId, nextKey);
  }
}

export function loadBrowserImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () =>
      reject(new Error('Thumbnail sprite could not be loaded'));
    image.src = url;
  });
}
