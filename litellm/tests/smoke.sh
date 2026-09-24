#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root_dir="$(cd "$project_dir/.." && pwd)"
command="$project_dir/bin/litellm"
test_dir="$root_dir/.local/litellm-smoke-$$"
mkdir -p "$test_dir/bin" "$test_dir/backups" "$test_dir/other-backups" "$test_dir/public" "$test_dir/unwritable"
chmod 700 "$test_dir/backups"
chmod 700 "$test_dir/other-backups"
chmod 755 "$test_dir/public"
chmod 500 "$test_dir/unwritable"
export LITELLM_BACKUP_DIR="$test_dir/backups"
export COMPOSE_PROJECT_NAME="litellmsmoke$$"
export DOCKER_REAL="$(command -v docker)"
export PATH="$test_dir/bin:$PATH"

cat > "$test_dir/bin/security" <<'MOCK'
#!/usr/bin/env bash
if [[ "${LITELLM_SMOKE_KEYCHAIN:-}" == missing ]]; then exit 44; fi
case "$*" in
  *projectslatte.litellm.master*) printf 'sk-local-smoke-master-1234567890\n' ;;
  *projectslatte.litellm.salt*) printf 'local-smoke-salt-1234567890\n' ;;
  *projectslatte.litellm.postgres*) printf 'local-smoke-postgres-password\n' ;;
  *projectslatte.litellm.openrouter*) printf 'sk-local-smoke-openrouter\n' ;;
  *) exit 44 ;;
esac
MOCK
chmod +x "$test_dir/bin/security"

cat > "$test_dir/bin/docker" <<'MOCK'
#!/usr/bin/env bash
if [[ -n "${LITELLM_SMOKE_BLOCK_BACKUP:-}" && "$*" == *'--type=incr backup'* ]]; then
  touch "$LITELLM_SMOKE_BLOCK_BACKUP.entered"
  until [[ -f "$LITELLM_SMOKE_BLOCK_BACKUP.release" ]]; do sleep 0.1; done
fi
if [[ "${LITELLM_SMOKE_FAIL_BACKUP:-}" == yes && "$*" == *'--type=incr backup'* ]]; then
  printf 'Injected backup failure.\n' >&2
  exit 45
fi
exec "$DOCKER_REAL" "$@"
MOCK
chmod +x "$test_dir/bin/docker"

compose() { "$DOCKER_REAL" compose -f "$project_dir/compose.yaml" "$@"; }
count_backups() {
  "$DOCKER_REAL" run --rm --volume "$LITELLM_BACKUP_DIR:/var/lib/pgbackrest:ro" \
    --entrypoint pgbackrest projectslatte/litellm-postgres:18.6-trixie-pgbackrest-2.55.1 \
    --stanza=litellm info --output=json \
    | python3 -c 'import json,sys; print(len(json.load(sys.stdin)[0]["backup"]))'
}
assert_stopped() {
  [[ -z "$(compose ps --status running -q proxy)" ]]
  [[ -z "$(compose ps --status running -q postgres)" ]]
}
cleanup() {
  local result=$?
  if (( result != 0 )); then
    for log in "$test_dir"/{first,second,third,mismatched-backup,mismatched-status,manual,restore,restart}.log; do
      if [[ -f "$log" ]]; then
        printf '%s:\n' "$(basename "$log")" >&2
        tail -n 10 "$log" >&2
      fi
    done
  fi
  unset LITELLM_SMOKE_FAIL_BACKUP
  compose down --remove-orphans >/dev/null 2>&1 || true
  "$DOCKER_REAL" volume rm "${COMPOSE_PROJECT_NAME}_postgres-data" >/dev/null 2>&1 || true
  rm -rf "$test_dir"
}
trap cleanup EXIT

compose build postgres >/dev/null
"$command" status > "$test_dir/empty-status.log" 2>&1
grep -q 'Latest backup: none none' "$test_dir/empty-status.log"

if LITELLM_SMOKE_KEYCHAIN=missing "$command" start > "$test_dir/missing.log" 2>&1; then
  printf 'Missing Keychain item did not stop startup.\n' >&2; exit 1
fi
assert_stopped
if LITELLM_BACKUP_DIR="$test_dir/public" "$command" start > "$test_dir/public.log" 2>&1; then
  printf 'Public backup directory did not stop startup.\n' >&2; exit 1
fi
assert_stopped
if LITELLM_BACKUP_DIR="$test_dir/unwritable" "$command" start > "$test_dir/unwritable.log" 2>&1; then
  printf 'Unwritable backup directory did not stop startup.\n' >&2; exit 1
fi
assert_stopped

"$command" start > "$test_dir/first.log" 2>&1 || { cat "$test_dir/first.log" >&2; exit 1; }
grep -q 'Starting full backup.' "$test_dir/first.log"
grep -q 'LiteLLM is ready' "$test_dir/first.log"
python3 - "$test_dir/first.log" <<'PY'
import pathlib
import sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
assert next(i for i, line in enumerate(lines) if "Starting full backup." in line) < next(
    i for i, line in enumerate(lines) if "LiteLLM is ready" in line
)
PY
[[ "$(compose ps --status running -q proxy)" != '' ]]
[[ "$(count_backups)" == 1 ]]
first_type="$(compose exec -T --user postgres postgres pgbackrest --stanza=litellm info --output=json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["backup"][-1]["type"])')"
[[ "$first_type" == full ]]

proxy_id="$(compose ps -q proxy)"
postgres_id="$(compose ps -q postgres)"
for value in 'sk-local-smoke-master-1234567890' 'local-smoke-salt-1234567890' 'local-smoke-postgres-password' 'sk-local-smoke-openrouter'; do
  if "$DOCKER_REAL" inspect "$proxy_id" "$postgres_id" | grep -Fq "$value"; then
    printf 'A secret value appeared in docker inspect.\n' >&2; exit 1
  fi
done

LITELLM_SMOKE_KEYCHAIN=missing "$command" stop > "$test_dir/stop.log" 2>&1
assert_stopped
"$DOCKER_REAL" volume inspect "${COMPOSE_PROJECT_NAME}_postgres-data" >/dev/null
LITELLM_SMOKE_KEYCHAIN=missing "$command" status > "$test_dir/status.log" 2>&1
grep -q 'Latest backup: full' "$test_dir/status.log"

"$command" start > "$test_dir/second.log" 2>&1 || { cat "$test_dir/second.log" >&2; exit 1; }
grep -q 'Starting incr backup.' "$test_dir/second.log"
[[ "$(count_backups)" == 2 ]]
second_type="$(compose exec -T --user postgres postgres pgbackrest --stanza=litellm info --output=json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["backup"][-1]["type"])')"
[[ "$second_type" == incr ]]
"$command" start > "$test_dir/third.log" 2>&1
grep -q 'already running' "$test_dir/third.log"
[[ "$(count_backups)" == 2 ]]
if LITELLM_BACKUP_DIR="$test_dir/other-backups" "$command" backup > "$test_dir/mismatched-backup.log" 2>&1; then
  printf 'Backup accepted a path different from the running PostgreSQL mount.\n' >&2; exit 1
fi
grep -q 'Backup directory differs from the running PostgreSQL mount' "$test_dir/mismatched-backup.log"
[[ "$(count_backups)" == 2 ]]
if LITELLM_BACKUP_DIR="$test_dir/absent-backups" "$command" backup > "$test_dir/absent-backup.log" 2>&1; then
  printf 'Backup accepted a missing repository directory.\n' >&2; exit 1
fi
[[ ! -e "$test_dir/absent-backups" ]]
LITELLM_BACKUP_DIR="$test_dir/other-backups" "$command" status > "$test_dir/mismatched-status.log" 2>&1
grep -Fxq "Backup directory: $test_dir/backups" "$test_dir/mismatched-status.log"
if grep -Fxq "Backup directory: $test_dir/other-backups" "$test_dir/mismatched-status.log"; then
  printf 'Status reported the requested path instead of the live mount.\n' >&2; exit 1
fi
key_alias="litellm-smoke-$$"
key_response="$(curl --silent --show-error --fail \
  -X POST http://127.0.0.1:4000/key/generate \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer sk-local-smoke-master-1234567890' \
  -d "{\"key_alias\":\"$key_alias\",\"models\":[\"agent-cheap\"]}")"
printf '%s' "$key_response" | python3 -c 'import json,sys; assert json.load(sys.stdin).get("key")'
unset key_response
has_key_alias() {
  local count
  count="$(printf '%s\n' \
    'SELECT count(*) FROM "LiteLLM_VerificationToken" WHERE key_alias = :'"'"'alias'"'"';' \
    | compose exec -T --user postgres postgres \
      psql -X -v ON_ERROR_STOP=1 -v "alias=$key_alias" -U litellm -d litellm -At)"
  [[ "$count" =~ ^[0-9]+$ && "$count" -gt 0 ]]
}
has_key_alias
"$command" backup > "$test_dir/manual.log" 2>&1
grep -q 'Starting incr backup.' "$test_dir/manual.log"
[[ "$(count_backups)" == 3 ]]

for value in 'sk-local-smoke-master-1234567890' 'local-smoke-salt-1234567890' 'local-smoke-postgres-password' 'sk-local-smoke-openrouter'; do
  if grep -Fq "$value" "$test_dir"/*.log; then
    printf 'A secret value appeared in command output.\n' >&2; exit 1
  fi
  if compose logs --no-color | grep -Fq "$value"; then
    printf 'A secret value appeared in container logs.\n' >&2; exit 1
  fi
done

source "$project_dir/lib/backup.sh"
summary="$(printf '%s' '[{"name":"litellm","backup":[{"type":"full","timestamp":{"stop":1600000000}}]}]' | backup_summary 1600604800)"
[[ "$summary" == *'|full' ]]
summary="$(printf '%s' '[{"name":"litellm","backup":[{"type":"full","timestamp":{"stop":1600000000}}]}]' | backup_summary 1600604799)"
[[ "$summary" == *'|incr' ]]

live_volume="${COMPOSE_PROJECT_NAME}_postgres-data"
volume_identity="$("$DOCKER_REAL" volume inspect --format '{{.Name}}:{{.CreatedAt}}' "$live_volume")"
"$command" stop > "$test_dir/stop2.log" 2>&1
"$command" restore-check --expect-key-alias "$key_alias" > "$test_dir/restore.log" 2>&1 || {
  cat "$test_dir/restore.log" >&2; exit 1
}
grep -q 'Isolated restore passed' "$test_dir/restore.log"
[[ "$("$DOCKER_REAL" volume inspect --format '{{.Name}}:{{.CreatedAt}}' "$live_volume")" == "$volume_identity" ]]
if "$DOCKER_REAL" volume ls --format '{{.Name}}' | grep -Fq "${COMPOSE_PROJECT_NAME}-restore-"; then
  printf 'A temporary restore volume remains.\n' >&2; exit 1
fi
"$command" start > "$test_dir/restart.log" 2>&1 || { cat "$test_dir/restart.log" >&2; exit 1; }
has_key_alias
[[ "$("$DOCKER_REAL" volume inspect --format '{{.Name}}:{{.CreatedAt}}' "$live_volume")" == "$volume_identity" ]]
"$command" stop > "$test_dir/stop3.log" 2>&1
if LITELLM_SMOKE_FAIL_BACKUP=yes "$command" start > "$test_dir/failure.log" 2>&1; then
  printf 'Injected backup failure did not stop startup.\n' >&2; exit 1
fi
assert_stopped
[[ "$(count_backups)" == 4 ]]
mv "$test_dir/backups" "$test_dir/preserved-backups"
if "$command" status > "$test_dir/lost-status.log" 2>&1; then
  printf 'Status accepted a missing established repository.\n' >&2; exit 1
fi
[[ ! -e "$test_dir/backups" ]]
if "$command" start > "$test_dir/lost-start.log" 2>&1; then
  printf 'Start accepted a missing established repository.\n' >&2; exit 1
fi
assert_stopped
[[ ! -e "$test_dir/backups" ]]
"$command" start --reinitialize-backup-repo > "$test_dir/reinit.log" 2>&1 || {
  cat "$test_dir/reinit.log" >&2; exit 1
}
grep -q 'Starting full backup.' "$test_dir/reinit.log"
[[ "$(count_backups)" == 1 ]]
"$command" stop > "$test_dir/reinit-stop.log" 2>&1

block="$test_dir/blocked-backup"
LITELLM_SMOKE_FAIL_BACKUP=yes LITELLM_SMOKE_BLOCK_BACKUP="$block" "$command" start > "$test_dir/locked-failure.log" 2>&1 &
first_pid=$!
for (( i=0; i<100; i++ )); do
  [[ -f "$block.entered" ]] && break
  sleep 0.1
done
[[ -f "$block.entered" ]] || { printf 'Timed out waiting for blocked backup.\n' >&2; exit 1; }
"$command" start > "$test_dir/locked-retry.log" 2>&1 &
second_pid=$!
sleep 1
kill -0 "$second_pid" || { printf 'Concurrent start did not wait for the lock.\n' >&2; exit 1; }
touch "$block.release"
if wait "$first_pid"; then
  printf 'Injected backup failure did not stop the first start.\n' >&2; exit 1
fi
wait "$second_pid" || { cat "$test_dir/locked-retry.log" >&2; exit 1; }
grep -q 'LiteLLM is ready' "$test_dir/locked-retry.log"
[[ -n "$(compose ps --status running -q proxy)" ]]
block="$test_dir/blocked-manual-backup"
LITELLM_SMOKE_BLOCK_BACKUP="$block" "$command" backup > "$test_dir/locked-backup.log" 2>&1 &
backup_pid=$!
for (( i=0; i<100; i++ )); do
  [[ -f "$block.entered" ]] && break
  sleep 0.1
done
[[ -f "$block.entered" ]] || { printf 'Timed out waiting for blocked manual backup.\n' >&2; exit 1; }
cp -R "$project_dir" "$test_dir/other-checkout"
"$test_dir/other-checkout/bin/litellm" status > "$test_dir/other-checkout-status.log" 2>&1 &
status_pid=$!
"$command" stop > "$test_dir/locked-stop.log" 2>&1 &
stop_pid=$!
sleep 1
kill -0 "$status_pid" || { printf 'Status in another checkout did not wait for the lock.\n' >&2; exit 1; }
kill -0 "$stop_pid" || { printf 'Stop did not wait for the running backup.\n' >&2; exit 1; }
touch "$block.release"
wait "$backup_pid" || { cat "$test_dir/locked-backup.log" >&2; exit 1; }
wait "$status_pid" || { cat "$test_dir/other-checkout-status.log" >&2; exit 1; }
wait "$stop_pid" || { cat "$test_dir/locked-stop.log" >&2; exit 1; }
grep -q 'Latest backup: incr' "$test_dir/other-checkout-status.log"
assert_stopped
printf 'LiteLLM smoke passed: full/incremental backups, virtual key restore, live volume identity, failure cleanup, missing repository guard, cross-checkout lock, live mount check, private backup, and secret boundary.\n'
