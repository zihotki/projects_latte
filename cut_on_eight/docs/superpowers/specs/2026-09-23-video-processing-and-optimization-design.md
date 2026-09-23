# Video processing view and optimization

## Intent

Show the work that uses video-processing resources without making the editor
busy. Keep the app single-user. Keep the existing basic search UI; search
indexing is not part of the processing view.

## Scope and sequence

1. Reuse frames from each video's thumbnail bundle for fragment cards. Remove
   the per-fragment preview job, asset, route, and storage code after the new
   display handles short fragments, end-of-video fragments, and missing bundles.
2. Add a compact processing control in the app bar and an expandable side
   panel. Show video import, inspection, and thumbnail generation only.
3. Batch workspace reads for fragment tags and preview data. Measure the query
   reduction with an integration test. Do not change the API result.
4. Review replay compatibility before shrinking new event payloads. This is a
   separate follow-up, not a prerequisite for the processing view.

## Rollout decision

The search API and historical data still refer to per-fragment preview assets.
The first cutover uses video bundles in fragment and search cards and stops
queuing new preview jobs. The old reader and worker remain temporarily so
existing assets and queued jobs still work. Remove those paths and derived
records in a separate compatibility cleanup after the new display is checked
with real media. This does not add new per-fragment generation work.

No multi-user model, per-job progress percentage, completed-job history,
search queue, or manual queue controls are part of this work.

## Processing read model

Add a read-only `GET /api/processing` endpoint. It derives state from the
catalog tables already used by the workers: `videos.status` for import and
inspection, and `video_thumbnail_state.status` for bundle generation. It does
not inspect NATS or present raw pg-boss messages. Each response item contains
the video ID and title, task type, state (`queued`, `running`, or `failed`),
last update time, and a safe failure label when available. An inspected video
without a thumbnail state is shown as waiting for thumbnails until the bundle
is ready or a failure is recorded. The endpoint returns active items and recent
failures, with a fixed server-side bound, plus summary counts. It does not
expose filesystem paths or raw exception text.

The API uses one query or a small fixed number of queries, independent of the
number of videos. It sorts active items by oldest update first and failures by
newest update first. Video deletion removes its items through the existing
foreign-key behavior.

## UI and refresh

The app bar shows a small `Processing` control with an active count; a failure
mark appears when needed. The panel opens on the side and lists the task,
video title, state, and failure label. It does not take space from the video
editor when closed. A row can open the related video, but it does not change
playback or focus until clicked. The client polls while the tab is visible and
shows the last known state plus a quiet stale-data message if refresh fails.
The view uses no invented progress percentage or time estimate.

## Failure handling and checks

The processing endpoint is observational: it neither changes job state nor
retries work. Existing retry flows remain where they are. Tests cover status
mapping, ordering, bounds, missing thumbnail state, failure redaction, and a
deleted video. UI tests cover the collapsed count, panel details, stale data,
and opening a video. Integration checks cover the preview cutover and batched
workspace reads. Run the repository check and test scripts, plus integration
tests when Docker is available.
