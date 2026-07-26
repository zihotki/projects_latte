import type { PgBoss } from 'pg-boss';
import type { Kysely } from 'kysely';
import { LocalBlobStore } from './blobs/local-blob-store.js';
import type { BlobStore, LocalMediaFiles } from './blobs/blob-store.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from './catalog/database.js';
import type { CatalogDatabase } from './catalog/database-types.js';
import type { ServerConfig } from './config.js';
import { FragmentService } from './fragments/fragment-service.js';
import { createBoss, createPhase4Queues } from './jobs/boss.js';
import { VideoService } from './videos/video-service.js';
import { WorkspaceService } from './workspace/workspace-service.js';

export interface ApiRuntime {
  readonly db: Kysely<CatalogDatabase>;
  readonly boss: PgBoss;
  readonly blobs: BlobStore & LocalMediaFiles;
  readonly videos: VideoService;
  readonly fragments: FragmentService;
  readonly workspace: WorkspaceService;
  close(): Promise<void>;
}

export async function createRuntime(config: ServerConfig): Promise<ApiRuntime> {
  const db = createCatalogDatabase(config);
  const boss = createBoss(config);
  await boss.start();
  await createPhase4Queues(boss);
  const blobs = new LocalBlobStore(config.dataRoot);
  const workspace = new WorkspaceService(db);
  const fragments = new FragmentService(db, boss, workspace);
  const videos = new VideoService(db, boss, blobs, workspace);
  let closed = false;
  return {
    db,
    boss,
    blobs,
    videos,
    fragments,
    workspace,
    async close() {
      if (closed) return;
      closed = true;
      await boss.stop({ graceful: true, timeout: 30_000 });
      await closeCatalogDatabase(db);
    },
  };
}
