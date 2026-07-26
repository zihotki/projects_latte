import type { VideoStatus } from '@cut-on-eight/api-contracts';
import type { BlobKey } from '../blobs/blob-key.js';

export class DomainConflict extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'DomainConflict';
  }
}

export class CatalogNotFound extends Error {
  readonly code = 'catalog_item_not_found';
}

export class StaleRevision extends DomainConflict {
  constructor() {
    super('stale_revision', 'The item changed since it was loaded.');
  }
}

export interface TagRecord {
  readonly id: string;
  readonly name: string;
}

export interface VideoRecord {
  readonly id: string;
  readonly title: string;
  readonly description: string | null;
  readonly originalFileName: string;
  readonly sourceAssetId: string | null;
  readonly durationUs: number | null;
  readonly width: number | null;
  readonly height: number | null;
  readonly frameRateNumerator: number | null;
  readonly frameRateDenominator: number | null;
  readonly frameRateReliability: 'reliable' | 'approximate';
  readonly hasAudio: boolean | null;
  readonly status: VideoStatus;
  readonly revision: number;
}

export interface AssetRecord {
  readonly id: string;
  readonly key: BlobKey;
  readonly kind: 'source' | 'fragment_preview';
  readonly mimeType: string;
  readonly size: number;
  readonly revision: number;
}

export interface FragmentRecord {
  readonly id: string;
  readonly videoId: string;
  readonly startUs: number;
  readonly endUs: number;
  readonly title: string | null;
  readonly description: string | null;
  readonly exportSelected: boolean;
  readonly revision: number;
}
