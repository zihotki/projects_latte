#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
container_name="projectslatte-postgres-test-$$"
database_name="cut_on_eight_test"
database_user="cut_on_eight_test"
database_password="cut_on_eight_test"

cleanup() {
  docker rm --force "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

command -v docker >/dev/null || {
  echo 'Docker is required for integration tests.' >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo 'Docker is installed but its daemon is not running.' >&2
  exit 1
}
command -v ffmpeg >/dev/null || {
  echo 'ffmpeg is required for Cut on Eight media integration tests.' >&2
  exit 1
}

docker run --detach --rm --name "$container_name" \
  --env "POSTGRES_DB=$database_name" \
  --env "POSTGRES_PASSWORD=$database_password" \
  --env "POSTGRES_USER=$database_user" \
  --publish 127.0.0.1::5432 \
  postgres:18.4 >/dev/null

for _ in {1..60}; do
  if docker exec "$container_name" pg_isready -U "$database_user" -d "$database_name" >/dev/null 2>&1; then
    host_port="$(docker port "$container_name" 5432/tcp | sed -E 's/.*:([0-9]+)$/\1/' | head -n 1)"
    CUT_ON_EIGHT_TEST_DATABASE_URL="postgresql://$database_user:$database_password@127.0.0.1:$host_port/$database_name" \
      PNPM_CONFIG_VERIFY_DEPS_BEFORE_RUN=false \
      pnpm -C "$root_dir/cut_on_eight" run test:integration
    exit 0
  fi
  sleep 1
done

docker logs "$container_name" >&2 || true
echo 'Timed out waiting for PostgreSQL integration database.' >&2
exit 1
