# Cleanup report — 2026-09-23

## Decision

Use mounted host directories for source media and thumbnail bundles on the
first single-server deployment. PostgreSQL owns catalog and job state. Keep
NATS and Qdrant private; Qdrant is a derived index. Do not add S3 yet: ffmpeg
still needs local paths, so an S3 adapter would also need a bounded staging
cache and failure recovery. See [homelab deployment](homelab-deployment.md).

## In this commit

- Add hybrid fragment search, a durable Qdrant indexer, and an index rebuild.
- Connect the editor timeline to the per-video thumbnail service.
- Stop editor-only saves from changing content revisions or emitting search
  events.
- Remove a source file and catalog row when import finalization fails.
- Use Problem Details for current API errors, with the legacy envelope kept
  for legacy routes.
- Add a single-host Compose layout and update dependencies. The production
  dependency audit reports no known advisories at this point in time.

## Next cleanup, in order

1. **Finish the preview cutover.** Fragment cards still use per-fragment
   preview jobs and assets. Reuse suitable frames from the video bundle, then
   remove the old job, asset, route, and storage paths. Test a short fragment,
   a fragment near the end, and a missing bundle before removal.
2. **Make search failures operable.** The indexer records a terminal failure,
   but there is no failed-count display or targeted retry command. Add both,
   reconcile existing JetStream consumer settings on startup, and retire the
   old `qdrant-projector-v1` durable consumer after upgrade. Keep the
   PostgreSQL event log as the replay source.
3. **Finish the catalog scope.** Collection filters exist in search, but the
   ordered, multi-membership collection tables and editor are not built.
   Either implement the approved collection design or hide the unused filter
   until it has real data.
4. **Reduce duplicate work.** Workspace snapshots fetch tags and previews per
   fragment, and the event log still carries full legacy projection payloads
   although the new indexer reloads catalog state. Batch reads and shrink new
   events only after replay compatibility is clear.
5. **Harden deployment.** Build and smoke-test the images on a host with Docker
   Hub access. Add authenticated remote access and tested, off-host backups
   before exposing the app. Verify PostgreSQL, media mounts, restore, and
   permissions on the target server. The Compose layout is not a live rollout.

## Verification at handoff

`./scripts/check.sh`, `./scripts/test.sh`, `./scripts/integration.sh`,
`docker compose config --quiet`, and `pnpm -C cut_on_eight audit --prod`
passed. The image build was attempted but could not fetch base-image metadata
because Docker Desktop could not resolve `registry-1.docker.io`. Image runtime
and the remote proxy remain unverified.
