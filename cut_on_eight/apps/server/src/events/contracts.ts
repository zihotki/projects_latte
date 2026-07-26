export type EventAggregateType = 'fragment' | 'video';

export interface FragmentProjectionPayload {
  readonly projectionVersion: 1;
  readonly fragmentId: string;
  readonly videoId: string;
  readonly fragmentRevision: number;
  readonly startUs: number;
  readonly endUs: number;
  readonly fragmentTitle: string | null;
  readonly fragmentDescription: string | null;
  readonly fragmentTags: readonly string[];
  readonly sourceTitle: string;
  readonly sourceDescription: string | null;
  readonly sourceTags: readonly string[];
}

export interface FragmentDeletedPayload {
  readonly fragmentId: string;
}

export interface ThumbnailRequestPayload {
  readonly videoId: string;
  readonly sourceAssetId: string;
  readonly thumbnailProfileVersion: 'overview-webp-v2';
}

export interface IntegrationEvent<
  TType extends string = string,
  TPayload extends object = Record<string, unknown>,
> {
  readonly eventId: string;
  readonly position: number;
  readonly type: TType;
  readonly schemaVersion: 1;
  readonly aggregate: {
    readonly type: EventAggregateType;
    readonly id: string;
    readonly revision: number;
  };
  readonly occurredAt: string;
  readonly correlationId: string | null;
  readonly causationId: string | null;
  readonly payload: TPayload;
}

export type FragmentChangedEvent = IntegrationEvent<
  'fragment.changed.v1',
  FragmentProjectionPayload
>;
export type FragmentDeletedEvent = IntegrationEvent<
  'fragment.deleted.v1',
  FragmentDeletedPayload
>;
export type ThumbnailRequestedEvent = IntegrationEvent<
  'video.thumbnails.requested.v1',
  ThumbnailRequestPayload
>;

export type CatalogEvent =
  FragmentChangedEvent | FragmentDeletedEvent | ThumbnailRequestedEvent;

export type NewCatalogEvent = Omit<
  CatalogEvent,
  'eventId' | 'position' | 'occurredAt'
>;
