# Single-host deployment

This is a first deployment path for one Linux server. It uses the same Fastify
API, workers, and Svelte build as local development. PostgreSQL is an existing
server service. Compose starts NATS and Qdrant on a private network. It does
not publish their ports. The web port is published on host loopback only.

## Storage choice

Use two persistent host directories: one for imported video sources and legacy
previews, and one for reusable video thumbnail bundles. Mount the same media
directory into API, worker, and thumbnails-service. PostgreSQL holds the
catalog, jobs, and outbox. NATS holds delivery state. Qdrant is a derived
index and can be rebuilt from PostgreSQL. A single disk is not a backup.

This layout is deliberate for the first host. The current `BlobStore` contract
supports byte ranges and atomic publish, but media workers also use
`LocalMediaFiles.withLocalPath` for ffmpeg. Moving the source store to S3
therefore needs a bounded local staging cache, not only a new URL or SDK.

If a shared object API becomes useful, test [Garage](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)
first. Its compatibility table lists GetObject and multipart upload support.
It does not give a single server redundancy
by itself. [Ceph Object Gateway](https://docs.ceph.com/en/latest/radosgw/index.html)
is better suited to an existing Ceph cluster, not this first deployment.
Do not put an S3 adapter into production until upload, range playback, local
ffmpeg staging, delete, and restore have integration tests against the chosen
store.

## Prepare

1. Create a PostgreSQL database and a password-protected app user. The
   containers must be able to reach its hostname. Apply normal PostgreSQL
   network and backup controls.
2. Create persistent media and thumbnail directories on the host. Set their
   owner to the UID and GID used by the app containers.
3. Copy `deploy/.env.homelab.example` to `deploy/.env.homelab`. Set the
   database URL, two absolute host paths, UID/GID, and exact browser origin.
   Do not commit this file.
4. From `deploy/`, run:

   ```sh
   docker compose --env-file .env.homelab config --quiet
   docker compose --env-file .env.homelab up -d --build
   ```

The local UI is at `http://127.0.0.1:8080` on the server. Check `api`,
`worker`, `outbox-relay`, `search-indexer`, and `thumbnails-service` logs after
start. The one-shot `migrate` service must finish before the app starts.

## Remote access

The app does not yet have user accounts. Do not publish port 8080 directly to
the LAN or internet. Put an authenticated HTTPS reverse proxy, VPN, or both in
front of the loopback web port. Set `CUT_ON_EIGHT_PUBLIC_ORIGIN` to the exact
browser origin, such as `https://cuts.example.net`. The API rejects other
browser origins. The reverse proxy must also limit access; the origin check is
not authentication.

Keep the API, PostgreSQL, Qdrant, and NATS private. The container API listens
on its bridge network only. The default non-container API still binds to
`127.0.0.1`.

## Recovery and limits

Back up PostgreSQL and the media directory together while writes are paused,
or use coordinated snapshots. Also back up the thumbnail directory if fast
restore matters. Keep encrypted copies off this host and test restore. Qdrant
can be rebuilt with the search rebuild command; do not treat it as the source
of truth. NATS is not the permanent event archive; PostgreSQL is.

This Compose file is a first single-host layout, not high availability. It
does not deploy PostgreSQL, add automatic off-host backups, supply proxy
authentication, or implement an S3 blob store. Those need host-specific
choices before they can be safe defaults.
