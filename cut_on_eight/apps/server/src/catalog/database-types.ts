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
  has_audio: boolean | null;
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
