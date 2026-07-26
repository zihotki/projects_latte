import type {
  ColumnType,
  Generated,
  Insertable,
  Selectable,
  Updateable,
} from 'kysely';

type Timestamp = ColumnType<Date, Date | string | undefined, Date | string>;
type NullableTimestamp = ColumnType<
  Date | null,
  Date | string | null | undefined,
  Date | string | null
>;
type BigIntText = ColumnType<string, string | number, string | number>;
type NullableColumn<T> = ColumnType<T | null, T | null | undefined, T | null>;
type JsonObject = Record<string, unknown>;

export interface AssetTable {
  id: string;
  storage_key: string;
  owner_kind: 'video' | 'fragment';
  owner_id: string;
  kind: 'source' | 'fragment_preview';
  mime_type: string;
  size_bytes: BigIntText;
  sha256: string;
  revision: Generated<number>;
  state: 'pending' | 'ready' | 'failed' | 'deleting';
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface VideoTable {
  id: string;
  source_asset_id: string | null;
  title: string;
  description: string | null;
  original_file_name: string;
  duration_us: BigIntText | null;
  width: number | null;
  height: number | null;
  frame_rate_numerator: NullableColumn<number>;
  frame_rate_denominator: NullableColumn<number>;
  frame_rate_reliability: Generated<'reliable' | 'approximate'>;
  has_audio: boolean | null;
  inspected_at: NullableTimestamp;
  inspector_version: NullableColumn<string>;
  processing_failure_code: NullableColumn<string>;
  processing_failure_retryable: NullableColumn<boolean>;
  processing_failure_at: NullableTimestamp;
  status:
    'receiving' | 'queued' | 'processing' | 'ready' | 'failed' | 'deleting';
  revision: Generated<number>;
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface FragmentTable {
  id: string;
  video_id: string;
  start_us: BigIntText;
  end_us: BigIntText;
  title: string | null;
  description: string | null;
  export_selected: boolean;
  revision: Generated<number>;
  deleted_at: NullableTimestamp;
  undo_token_hash: NullableColumn<string>;
  purge_after: NullableTimestamp;
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface TagTable {
  id: string;
  name: string;
  created_at: Timestamp;
}

export interface VideoTagTable {
  video_id: string;
  tag_id: string;
}

export interface FragmentTagTable {
  fragment_id: string;
  tag_id: string;
}

export interface FragmentPreviewTable {
  fragment_id: string;
  fragment_revision: number;
  asset_id: string | null;
  status: 'pending' | 'ready' | 'failed';
  sample_us: ColumnType<
    string[],
    Array<string | number>,
    Array<string | number>
  >;
  columns: number;
  rows: number;
  frame_width: number;
  frame_height: number;
  failure_code: string | null;
  updated_at: Timestamp;
}

export interface SearchProjectionStateTable {
  fragment_id: string;
  projection_revision: number;
  projection_version: number;
  status: 'pending' | 'ready' | 'failed';
  last_failure_code: string | null;
  last_event_id: string | null;
  last_aggregate_revision: number | null;
  last_source_position: BigIntText | null;
  updated_at: Timestamp;
}

export interface IntegrationEventTable {
  position: Generated<BigIntText>;
  event_id: string;
  event_type: string;
  schema_version: number;
  aggregate_type: 'fragment' | 'video';
  aggregate_id: string;
  aggregate_revision: number;
  occurred_at: Timestamp;
  correlation_id: string | null;
  causation_id: string | null;
  payload: ColumnType<JsonObject, JsonObject, JsonObject>;
}

export interface EventPublicationTable {
  event_id: string;
  destination: 'jetstream-primary';
  status: 'pending' | 'leased' | 'published' | 'failed';
  attempts: number;
  available_at: Timestamp;
  locked_until: NullableTimestamp;
  published_at: NullableTimestamp;
  broker_stream: string | null;
  broker_sequence: BigIntText | null;
  last_error: string | null;
}

export interface EventReplayRunTable {
  id: string;
  start_position: BigIntText;
  end_position: BigIntText;
  destination_stream: string;
  purpose: string;
  status: 'running' | 'completed' | 'failed';
  published_through_position: BigIntText | null;
  last_error: string | null;
  created_at: Timestamp;
  completed_at: NullableTimestamp;
}

export interface VideoThumbnailStateTable {
  video_id: string;
  source_asset_id: string;
  profile_version: string;
  storage_key: string | null;
  status: 'pending' | 'generating' | 'ready' | 'failed';
  manifest: NullableColumn<JsonObject>;
  failure_code: string | null;
  updated_at: Timestamp;
}

export interface SemanticSearchIndexStateTable {
  profile_id: string;
  fragment_id: string;
  collection_name: string;
  fragment_revision: number;
  text_hash: string;
  status: 'pending' | 'ready' | 'failed';
  last_event_id: string | null;
  last_source_position: BigIntText | null;
  failure_code: string | null;
  updated_at: Timestamp;
}

export interface SemanticSearchRebuildTable {
  id: string;
  profile_id: string;
  target_collection_name: string;
  snapshot_high_water_position: BigIntText;
  status: 'running' | 'ready' | 'failed';
  error_text: string | null;
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface WorkspaceStateTable {
  id: boolean;
  active_video_id: string | null;
  updated_at: Timestamp;
}

export interface WorkspaceVideoTable {
  video_id: string;
  position: number;
  playback_position_us: BigIntText;
  opened_at: Timestamp;
}

export interface EditorStateTable {
  video_id: string;
  selected_fragment_id: string | null;
  pause_after_creation: boolean;
  timeline_zoom: number;
  timeline_offset_us: BigIntText;
  updated_at: Timestamp;
}

export interface WorkerHeartbeatTable {
  worker_id: string;
  last_seen_at: Timestamp;
}

export interface CatalogDatabase {
  assets: AssetTable;
  videos: VideoTable;
  fragments: FragmentTable;
  tags: TagTable;
  video_tags: VideoTagTable;
  fragment_tags: FragmentTagTable;
  fragment_previews: FragmentPreviewTable;
  search_projection_state: SearchProjectionStateTable;
  integration_events: IntegrationEventTable;
  event_publications: EventPublicationTable;
  event_replay_runs: EventReplayRunTable;
  video_thumbnail_state: VideoThumbnailStateTable;
  semantic_search_index_state: SemanticSearchIndexStateTable;
  semantic_search_rebuilds: SemanticSearchRebuildTable;
  workspace_state: WorkspaceStateTable;
  workspace_videos: WorkspaceVideoTable;
  editor_state: EditorStateTable;
  worker_heartbeats: WorkerHeartbeatTable;
}

export type VideoRow = Selectable<VideoTable>;
export type NewVideoRow = Insertable<VideoTable>;
export type VideoUpdate = Updateable<VideoTable>;
export type FragmentRow = Selectable<FragmentTable>;
export type NewFragmentRow = Insertable<FragmentTable>;

export function safeMicroseconds(value: string): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error('Catalog contains an invalid microsecond value');
  }
  return parsed;
}
